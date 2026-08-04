# From OWL Ontology to Profile Specification

An OWL ontology and a metaseed profile look similar enough that turning one into the other seems like a format conversion. It is not. OWL is a logic evaluated under the open world assumption, and a reasoner draws conclusions from it. A profile is a schema for records. This page states what survives that translation, what does not, and what metaseed does about it.

## In plain terms

An ontology describes what exists in a field of science and how it hangs together. A profile is a set of forms people fill in. Turning the first into the second means deciding, for everything the ontology mentions, whether it becomes a form, a box on a form, or an option in a drop-down list. Some things are none of those, and that is where the loss happens.

Three points carry most of the argument.

**A blank box is not the same as a box nobody printed.** A blank box says "fill me in", and metaseed reports it as missing. A box that was never printed says nothing at all, and the reader never learns the fact could have been recorded. If an ontology describes instrument settings and the profile has no field for them, those terms are not empty — they are invisible.

**Some things a form cannot hold.** An ontology may say that a DOI, a PubMed identifier and a repository accession are all kinds of identifier, and that an enzyme is a kind of protein. On a form these are unrelated boxes and unrelated forms. An ontology can also work things out: if A is part of B and B is part of C, it concludes A is part of C. A form only holds what was typed into it.

**One thing the form does better.** An ontology has to state explicitly that a gene is not a protein, because otherwise nothing prevents something being both. A form gets this free: a record is one kind of thing, and a controlled field holds one value.

The practical answer is not to make the form equal to the ontology, which is impossible, but to label every form and box with the ontology term it stands for. Then whatever the shape cannot carry can still be looked up, and two profiles can be compared by what their boxes mean rather than by what shape they happen to have.

## The question is usually asked the wrong way round

The question is normally posed as "OWL is open world, YAML is closed world, so how do you translate without losing information?". For metaseed the framing misleads on both halves.

**Metaseed is not closed world about completeness.** A missing value is reported, not rejected. Validation tells the author what is still absent so it can be filled in later, and an empty required field is a smaller problem than an invented one. That is the open world reading of absence: unasserted means *not yet known*, not *false*.

The practical consequence is that `required` maps almost exactly onto an OWL existential restriction. An axiom saying every asset has a persistent identifier, and a field marked `required: true`, carry the same content and differ only in enforcement style. Translating such an axiom to an optional field loses information for no benefit, so the rule is simple: a field is required exactly when the ontology states an existential for that property on the entity's class or one of its ancestors.

**The loss is not open-to-closed, it is logic-to-tree.** Almost everything that cannot be carried across is lost to the difference between a formalism a reasoner operates on and a shape that holds records, not to the treatment of absence.

## What the translation preserves

**Existential constraints**, as `required: true` on a field, or `min_items: 1` on a nesting list. See the open issues below on where list cardinality is actually enforced.

**The vocabulary**, in one of three ways, and the choice matters:

- `constraints.enum` — the allowed values written into the spec. Self-contained and enforced offline, but frozen at one ontology version.
- `options` — the same list, driving dropdowns and pre-import checks. Falls back to `constraints.enum` when unset.
- `type: ontology_term`, optionally with `ontologies` — a live OLS4 lookup, scoped to whole ontologies by their OLS id. Stays current as the ontology evolves, but requires the ontology to be published in OLS.

A field's own `ontology_term` is a fourth thing and easy to confuse with the third: it records **what the column means**, and places no constraint on its values.

```yaml
Assay:
  fields:
    - name: technology_type
      type: ontology_term
      ontologies: [efo]         # search scope: whole ontologies, not a subtree
      ontology_term: EFO:0000269 # what this column means; not a value constraint
```

Note the limitation: scoping is per ontology, not per branch. There is no way to say "any term beneath *this* class", so a profile cannot restrict a column to one subtree of a large ontology. Where the source ontology is not in OLS at all, the lookup resolves nothing and the column is effectively unconstrained unless its terms are inlined with `options`.

**Domains and ranges**, implicitly: a property's domain becomes the entity the field sits on, and its range becomes the `items` or `reference` target.

## What the closed shape enforces for free

Disjointness. Ontologies routinely state that two classes cannot overlap — a gene is not a protein, an assay is not a study — because in an open world nothing otherwise prevents an individual being both. A profile gets these constraints from its shape:

- Classes that became separate entities cannot overlap, because a record belongs to one entity type.
- Classes that became terms in the same single-valued `ontology_term` field cannot overlap, because the field holds one value.
- Classes that became distinct fields rooted at distinct branches cannot overlap either.

This is a case where the target is stronger than the source, and it is worth knowing before assuming the translation is loss in every direction.

## What the translation loses

| Axiom type | Carried across |
|---|---|
| SubClassOf with `SomeValuesFrom` | Yes — nesting, references, `required`, `min_items` |
| SubClassOf, plain subsumption | Partly — drives entity, abstract and vocabulary decisions |
| ObjectPropertyDomain and Range | Implicitly, in field placement |
| DisjointClasses | Enforced by shape |
| InverseObjectProperties | Partly — nesting plus back-reference |
| SubPropertyOf | No |
| TransitiveObjectProperty | No |
| SymmetricObjectProperty | No |
| EquivalentClasses | No |

The entries marked "no" are worth spelling out, because each removes a question the profile can no longer answer.

**Property hierarchies.** An ontology may declare several identifier properties as sub-properties of a general `identifier`. In a profile these become unrelated string fields. "Give me every identifier for this publication" is answerable against the ontology and unanswerable against the profile.

**Subsumption between record types.** If an ontology says an enzyme is a kind of protein, and both become entities, the profile holds two sibling entities with no stated relationship. Metaseed does not support entity inheritance — see [Entity Relationships](entity-relationships.md#why-not-inheritance) for why — so a superclass either disappears with its fields copied onto each subclass, or becomes a discriminator field on a single entity.

**Transitivity and symmetry.** Part-of relations are typically transitive, so a file belonging to an assay belonging to a study is part of that study. Association relations are often symmetric. Nesting and references record the direct link and license no inference from it.

**Inference itself.** This underlies all of the above. A profile that somehow encoded every axiom would still derive nothing from them, because there is no reasoner in the pipeline.

**Cardinality above one.** A reference field holds one value, so an axiom permitting many related individuals becomes either a nesting list or a single-valued reference, and the second silently narrows it.

**Disjunction.** An axiom requiring at least one of several kinds of related thing cannot be expressed by `required`, which says "this particular field must be filled" rather than "one of these fields must be".

## Translation choices, and why comparing profiles is harder than it looks

Several decisions are forced on whoever does the translation, and the ontology does not determine them:

- Which classes become entities, which become abstract superclasses whose fields are copied down, and which become vocabulary terms.
- Which containment relation becomes the nesting parent when a class is contained by more than one other. Every remaining containment becomes a reference.
- Whether a set of subclasses becomes several entities or one entity with a discriminator field. The deciding factor is usually how far the subclasses' fields diverge: subclasses with no distinct fields suit a discriminator, while subclasses with genuinely different fields suit separate entities, because one entity covering all of them would leave most fields empty on most records.

Two competent people translating the same ontology will answer these differently and produce structurally different profiles holding identical content. A structural diff between profiles therefore measures normalisation choices rather than modelling differences.

This is the argument for comparing profiles by the ontology terms on their entities and fields rather than by their shape: two profiles annotating a field with the same term describe the same thing wherever that field sits. It works only as far as both profiles annotate against overlapping vocabularies, which is a reason to annotate thoroughly rather than a guarantee that comparison will succeed.

## Practical guidance

**Keep the source ontology normative.** A profile is a view over an ontology, not a replacement for it. What the tree cannot carry stays recoverable by consulting the source — but only if every entity and field records which term it stands for. Annotation discipline is what makes a translation auditable rather than merely lossy.

**Record why each field exists.** A field justified by an axiom, a field placed by judgement because the ontology states no domain for the property, and a field invented to make an otherwise unreachable branch usable are three different things, and a reader cannot tell them apart from the field alone.

**Watch for classes the ontology never connects.** An open world tolerates a declared class that no axiom relates to anything: it means nobody has yet said what has them. A profile cannot. A branch with no field rooted at it is not merely undocumented, it is unenterable, and nothing reports it missing because the profile has no notion the statement was possible. Making such a branch usable means inventing the missing relation, which is a decision to record rather than to hide.

**Annotation properties carry no logic.** Identifier annotations such as `dc:identifier` are ignored by a reasoner, so an ontology can give the same accession to two unrelated classes without being inconsistent. That is harmless in OWL and becomes a defect only when a profile treats the accession as a key — which is exactly what term-level comparison does.

## Open issues

**Value-dependent conditions are not yet expressible.** Axioms attached to a subclass become conditional once that subclass is collapsed into a discriminator field: "if the assay class is a modelling analysis, then the model field is non-empty". Conditional rules currently test presence rather than value, so these constraints cannot be written. [ADR 003](../architecture/decisions/003-value-dependent-validation-rules.md) proposes the predicate form that would express them; until then such axioms live in field descriptions only.

**Where list cardinality is enforced is unsettled.** ADR 003 records that a cardinality rule over a child collection does not fire on the facade path, because children are stored as separate nodes linked by `parent_id` and the parent record holds no list to count. Field-level `min_items` on a nesting list is checked only when the field is present and non-null, so the same representation question applies to it. Until this is settled, `min_items: 1` derived from an existential axiom should not be assumed to be enforced on every path.

**Disjunctive existentials have no expression.** Neither a field flag nor any current rule type can state that at least one of several fields must be non-empty.
