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
| `get_term_sync(term_id)` | The term, or `None` when this source does not have it. Raise to say it could not be asked — `None` is an answer about the term, not about the service |
| `has_ontology_sync(ontology_id)` | Whether this source carries that ontology; `None` when it cannot say |
| `search_sync(query, ontology, limit)` | Matching terms, for a picker. Optional |
| `is_within_sync(term_id, ancestor)` | Whether the term sits beneath that one. Optional |
| `capabilities()` | What the source says about itself, before it is asked. Optional |

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
2. Being authoritative applies to an answer, not to a failure. A claimant that could not be reached has not spoken, so the remaining sources are asked.
3. Otherwise every source is asked in order, and the first answer wins.
4. When no source answered and at least one could not be asked, the router raises `TermSourceUnavailableError`. It does not return `None`: `None` means *asked, and it is not there*, and acting on that reports the user's value as wrong because a service was down. The check turns the exception into *not checked* — never invalid.

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

`within` constrains validation as well as the picker. A rule that narrows what a
column may hold, enforced only where values are *offered*, is a rule anyone can
walk around by typing or importing — so the check asks the same question the
picker does:

| Method | Answers |
| --- | --- |
| `is_within_sync(term_id, ancestor)` | Whether the term sits beneath that one; `None` when this source cannot say |

The third answer is what keeps this honest. A flat vocabulary has no parents to
walk and a service that did not respond has not said no; both report **not
checked**, and only a source that can see the hierarchy and looked may call a
value wrong. A term is within itself: "within this branch" reads inclusively.

`OntologyService` answers from OLS4's `hierarchicalAncestors` endpoint — the
same relation `childrenOf` scopes the picker by, so the two cannot disagree
about what the branch contains. Two readings of an OLS answer matter:

- **200 with no ancestors is not proof of anything.** OLS returns exactly that
  both for a term it does not carry — every `CO_715` value, since it does not
  host that ontology — and for one genuinely at the top of its tree. The two are
  indistinguishable from here, so neither is called wrong.
- **A truncated page is not an answer either.** If the ancestor list runs past
  one page and the branch root was not on it, the result is *not checked*, not
  "not beneath".

The measured effect on shipped data was nothing: two fields declare `within` —
`Event.event_accession_number` in miappe 1.1 and 1.2 — and no shipped example
populates either. When one is populated with a Crop Ontology term, the answer is
*not checked* rather than a pass, because OLS does not carry CO_715 and no local
vocabulary for it ships. That is the honest report, and it is what a local
`co_715` vocabulary would change.

## What a source says about itself

`capabilities()` returns a `SourceCapabilities`: a name, whether the source can serve *interactive* lookup, how expensive it is to materialise, and a note.

**Latency is a correctness property here, not a quality of service.** A picker is a person waiting at a keyboard; plan07 measured OLS answering PO in 51 seconds and PATO in 32, against 20-55 ms from a local store. At that speed the feature is not slow, it is unusable — while looking fully implemented, because nothing in the system could tell the difference. So a source declares it, and `search_sync(..., interactive=True)` leaves out the ones that cannot serve a picker. Validation asks with it off: a slow source is still exactly the right thing to ask whether a term exists.

**Silence means "as good as it has always been".** An adapter that implements nothing here is read as interactive with its cost unstated. A default that disabled the picker for every existing installation would be a worse answer than the problem.

**A skip is reported.** `TermRouter.not_interactive()` names the sources a picker left out, and `/api/ontology/search` returns them as `not_asked` for the dialog to show. A shorter list of results is otherwise indistinguishable from there being less to find, which is the same silent-degradation failure the router's three-outcome checking exists to prevent.

**Cost is declared, not acted on here.** `Materialisation` is `none` (a remote service holds nothing), `cheap`, `large`, or `unknown`. metaseed materialises nothing, so it skips nothing on this basis and no code here branches on it; the declaration exists so a consumer that *does* import ontologies — GAZ is around 180 MB, ChEBI and NCBITaxon the same class — reads one interface instead of inventing its own. `TermRouter.capabilities()` reports the worst case it holds, because a consumer deciding whether to materialise needs that rather than an average.

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
