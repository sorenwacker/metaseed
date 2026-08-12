# Term sources

Where an ontology term is looked up is a question with more than one answer. OLS4 is the default and covers most of what the shipped profiles name, but it is not complete and it is not always reachable:

- OLS4 hosts `to` but not `co_321`, which MIAPPE names beside it. Asked about a Crop Ontology term, OLS answers "no such term" — about a vocabulary it does not carry.
- A consortium's own list exists nowhere public.
- A SEEK instance's controlled vocabularies are local to that instance by construction.
- A laptop in a glasshouse has no network, and work must continue.

So OLS is one adapter. A term source is anything that can answer the same questions, and the application asks a router rather than a service.

## The port

`metaseed.services.term_check.TermSource` is the interface an adapter implements:

| Method | Answers |
| --- | --- |
| `get_term_sync(term_id)` | The term, or `None` when this source does not have it |
| `has_ontology_sync(ontology_id)` | Whether this source carries that ontology; `None` when it cannot say |
| `search_sync(query, ontology, limit)` | Matching terms, for a picker. Optional |

`has_ontology_sync` is what makes a missing term interpretable. Without it, "not found" and "not carried" are the same answer, and every Crop Ontology term reads as invalid.

## Adapters in the box

| Adapter | Module | Carries |
| --- | --- | --- |
| `OntologyService` | `services.ontology` | OLS4, cached and rate limited |
| `LocalVocabulary` | `services.local_terms` | One vocabulary as a JSON file |
| `VocabularyStore` | `services.local_terms` | A directory of them, layered |

An adapter is not required to live in metaseed. Anything with those methods can be registered — an AgroPortal client, a SEEK instance's vocabularies, a lab's internal service.

## The router

`metaseed.services.terms.get_term_source()` returns the `TermRouter` the application asks. Its rule:

1. If a source claims the ontology a term id names (`has_ontology_sync` returns `True`), that source is **authoritative** for it. A term missing there is missing, and no other source is asked — otherwise a local vocabulary that deliberately narrows a public ontology would be silently widened again by the public one.
2. Otherwise every source is asked in order, and the first answer wins.
3. When nobody can say, the answer is `None`, which the check reports as *not checked* — never as invalid.

Order is composition, not preference given at each call: local vocabularies are registered ahead of OLS, so offline work resolves without a network round trip.

```python
from metaseed.services.terms import get_term_source, register_term_source

register_term_source(my_adapter, first=True)   # asked before the defaults
source = get_term_source()
```

Registration is context-scoped, like the ontology service it composes, so a test or a request can install its own sources without touching global state.

## Scoping to a branch

`ontologies:` says which ontologies a field takes. It cannot say *which part* of
one, so a column meant for a technology type accepts any term in the ontology —
and a profile built from a single domain ontology cannot distinguish its columns
at all (#229).

`within` names the term whose descendants are the valid values:

```yaml
- name: technology_type
  type: ontology_term
  ontologies: [jerm]
  within: JERM:00025        # only terms beneath Technology type
  ontology_term: JERM:00025 # unchanged: what the column means
```

The two keys are different questions. `ontology_term` says what the column
*means*; `within` says what may go in it.

A source that cannot restrict to a subtree is **skipped** for that query rather
than allowed to answer unrestricted — handing a whole ontology to a column that
asked for one branch is precisely what the restriction exists to prevent. A flat
local vocabulary has no hierarchy, so it does not serve branch-scoped queries.

`within` narrows the picker. It does not currently constrain validation: a
dataset already holding a term from outside the branch keeps validating, because
turning that check on is a data-affecting change that needs its own measurement.

## Local vocabularies

A vocabulary is a JSON file, kept apart from the specifications that use it:

```json
{
  "ontology": "co_321",
  "terms": {"CO_321:0000123": "plant height", "CO_321:0000456": "grain yield"}
}
```

A specification names an ontology and says nothing about where its terms come from:

```yaml
- name: trait_accession_number
  type: ontology_term
  ontologies: ["to", "co_321"]
```

That separation is deliberate. One vocabulary serves many specifications, it is versioned on its own, and updating it does not mean editing every profile that uses it.

### Extending one

Several files may declare the same ontology. They layer in filename order, later terms winning, and each term remembers which file supplied it:

```
vocabularies/
  co_321.10-snapshot.json     # the public snapshot
  co_321.20-consortium.json   # terms this project adds
```

Neither file has to be edited to accommodate the other, which is the point: a project extends a vocabulary someone else maintains without forking it, and `VocabularyStore.source_of(term_id)` says which file an answer came from.

`METASEED_VOCABULARIES` names the directory to load at startup. Unset, or pointing nowhere, means no local vocabularies and OLS alone — which is the behaviour that existed before this.

## The gate

`tests/test_term_sources_are_adapters.py` fails when a module reaches for OLS directly instead of asking the router — importing `get_ontology_service`, or calling OLS4's HTTP API — outside the adapter boundary. The rule is that OLS is one mechanism; the gate is what keeps it one.
