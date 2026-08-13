# ADR 003: Value-Dependent Validation Rules (Predicates on Rules)

**Date:** 2026-08-02
**Status:** Accepted and implemented (all three slices)
**Context:** [Issue #211](https://github.com/sorenwacker/metaseed/issues/211) — validation rules cannot depend on field values

## Decision

Add an optional predicate to validation rules: `where` on `cardinality` and `uniqueness` (selecting the subset a rule counts), and `when` plus `require` on `conditional` (making a requirement depend on a value). Represent the predicate as a **structured value** — a small nested mapping — rather than as an expression string, evaluate it by walking that structure with a fixed operator table and no parser, and confine what it can see to the record being examined.

This differs from the proposal in issue #211, which specifies a string mini-language. Section 1 states the reason and what it costs.

## Problem

Two shapes of constraint are inexpressible today.

**A conditional rule tests presence, not value.** `ConditionalRule._extract_fields` (`src/metaseed/validators/rules.py:446-453`) removes parentheses, splits on whitespace, discards the tokens `AND`, `OR`, `NOT`, and treats every remaining token as a field name. `_evaluate` (`rules.py:455-500`) then substitutes `TRUE`/`FALSE` for each name according to `has_value` (`src/metaseed/validators/base.py:11-27`) and reduces the resulting string. The rule therefore has no access to values at all: "required when another field equals X" cannot be written.

**Cardinality and uniqueness apply to every child.** `ListCardinalityRule` (`rules.py:523-609`) compares `len(data[field])` against `min_items`/`max_items`. `UniquenessRule` (`rules.py:676-770`) accumulates every value of a field. Neither takes a predicate, so a constraint over *some* of a collection has no expression.

The reporting case is a profile modelling the SEEK template format, whose four remaining constraints had to stay in an external Python checker. That checker found a template with zero display columns that metaseed reported as valid.

## Findings that qualify the issue's description

Three facts from the code change what "done" means and are recorded here so the implementation is not planned against the issue text alone.

1. **`validate_extracted` runs no validation rules whatsoever.** It calls `ExtractionContext.validate_instance` (`src/metaseed/agent/core.py:376-407`), which iterates the entity spec's own fields and applies field-level constraints via `_validate_field` (`core.py:409-479`). It never reads `ProfileSpec.validation_rules` and never builds a `ValidationEngine`. The issue attributes the missed display-column defect to the absence of predicates; the more immediate cause is that *no* rule of any kind — predicated or not — runs on that path. Wiring the engine into `ExtractionContext` is a prerequisite for the issue's definition-of-done item "predicated rules run in both `validate_dataset` and `validate_extracted`", and it is a separate change from this one. *(Since resolved as its own change: `validate_instance` now runs the profile's rules through `create_engine_for_extracted_record`, which excludes the rule types a single flat record cannot answer — see `docs/api/validators.md`. Findings 2 and 3 below are why that exclusion list exists.)*

2. **Uniqueness is enforced twice, and the engine's copy is inert.** `UniquenessRule` is stateful across calls to one instance, but `create_engine_for_entity` builds a fresh engine (and therefore a fresh rule) per record, so it never sees a second value and never fires — its own docstring says so (`rules.py:677-697`). Cross-record uniqueness is enforced instead by `DatasetValidator._load_uniqueness_rules` (`src/metaseed/validators/dataset.py:159-195`) and `_validate_uniqueness` (`dataset.py:358-416`), which read `unique_within` off the rule spec directly. A `where` on `uniqueness` must therefore be implemented in the dataset validator; implementing it only on `UniquenessRule` would produce a rule that still never fires. *(Since resolved: `UniquenessRule` has been deleted, together with `EntityReferenceRule`, which no engine ever added either. `uniqueness` and `reference` remain valid rule types and are enforced only by `DatasetValidator`, so there is now one enforcement site per rule type rather than two.)*

3. **The facade path cannot see a child collection.** `DatasetValidator._traverse_entity_tree` (`dataset.py:262-290`) walks nested dictionaries, so a `cardinality` rule on `SampleType.attributes` receives the parent record with its children inside it. The facade stores children as separate `EntityNode` objects linked by `parent_id` (`src/metaseed/facade/store.py`), and the MCP `validate_dataset` tool validates each node from `node.instance.model_dump()` (`src/metaseed/agent/mcp/tools/validation.py:164-193`, `306+`). On that path the parent record has no `attributes` list, so a cardinality-over-children rule sees an empty list regardless of the predicate. Which paths enforce a predicated rule is therefore a property of the data representation, not of the rule, and must be stated in the documentation rather than assumed.

## Decisions and rationale

### 1. The predicate is a structured value, not an expression string

**Chosen:** a predicate is a mapping. Its leaf form is `{field, op, value}`; its composite forms are `{all: [...]}`, `{any: [...]}`, and `{not: {...}}`.

```yaml
where:
  all:
    - field: isa_tag
      op: in
      value: [source, protocol, sample, data_file, other_material]
    - field: name
      op: "!="
      value: Input
```

**Why, against the four criteria the choice turns on:**

*Authoring in YAML by hand.* The string wins on length: one line against four to eight. This is the structured form's only real cost and it is not negligible — the issue's three examples read as the sentences the constraints are. Against it: YAML types the literal for free. `value: true` is a boolean and `value: "true"` is a string, whereas in `is_display_column == true` the author has to know which spelling the grammar treats as a literal. The same holds for numbers and for a list literal with an embedded quote.

*Authoring by an agent over MCP.* Both work. A string parameter is trivially passable; a mapping parameter is expressible in the tool schema, and the operator set becomes discoverable from that schema rather than from prose the agent may not have read. The decisive difference is the failure mode: a malformed string is a parse error discovered at load, after the spec has been written, while a malformed mapping is rejected by Pydantic at the point of construction with a field-level message.

*Diffability.* For a single comparison the two are equivalent — one line changes either way — except that the structured diff names which of field, operator, or value changed. For a compound predicate the string changes wholesale and the reviewer must re-read it; the structured form changes on the line that moved.

*Content hash.* This is the criterion that decides it. `canonical_json` (`src/metaseed/specs/versioning.py:130-161`) serializes the spec model with `sort_keys=True`, so a mapping is canonical for free: key order in the source YAML is not content, and there is no whitespace or quote style to vary. A string is one JSON scalar, so `data_type=='X'`, `data_type == 'X'` and `data_type == "X"` are three different documents with three different content hashes. Because `_rule_changes` compares rule specs with `!=` (`src/metaseed/specs/compare.py:629-639`), reformatting a predicate would be reported as `validation_rule_changed`, which is classified BREAKING (`compare.py:117`) and would force a MAJOR bump for a whitespace edit. The two mitigations both make things worse: canonicalising the string at load means the only key in the format whose text is silently rewritten on save, and hashing a parsed form instead of the stored text means a special case inside the one function that is currently uniform for every key.

**Consequence, and the escape hatch if the authoring cost proves too high:** the string can be reintroduced later as an *input* syntax without changing the stored format — the UI and the MCP tools accept text, compile it to the structured form, and store that. The disk format then still has exactly one spelling per predicate. Doing it the other way round (storing strings, deriving structure) is what causes the hash problem, and cannot be undone once specs exist in the wild.

**The string is kept as the rendering.** A `render_predicate()` function produces exactly the issue's syntax from the structured form, and that rendering is what appears in error messages (decision 6), in the rules list in the UI, and in `spec_validate` output. Readability is preserved where it is read; canonicality is preserved where it is stored.

### 2. Evaluation walks the structure; there is no parser

**Chosen:** evaluation is a recursive walk over the predicate model with a fixed operator table. `eval` is excluded, and so is `ast.parse` with a node allowlist, because with the structured form there is nothing to parse.

The `ast.parse`-with-allowlist option would be the correct answer if the format were a string, and is recorded here as the rejected second-best: it needs a node allowlist, a depth bound, and a length bound of its own, and it makes Python semantics the default — chained comparisons, truthiness of non-empty containers, tuple literals, operator precedence — so every Python behaviour we do *not* want has to be excluded by name. A hand-written parser avoids that but adds a grammar to version, to document, and to keep in step with two editors.

**Operators:** `==`, `!=`, `in`, `not_in`, `>`, `>=`, `<`, `<=`, plus `is_set` and `is_not_set`. The last two exist so `when` is a superset of what the legacy `condition` can express; whether `condition` is eventually deprecated is out of scope. `matches` (regex) is deliberately not in the set.

**The bound, and the precedent it follows.** The repository already treats a user-supplied regex as hostile input: `PatternRule` and `UniqueIdPatternRule` match through `_matches_within_timeout` (`rules.py:23-36`) with a one-second ceiling per value, and the `regex` dependency exists for that reason alone (`pyproject.toml:40-43`) because stdlib `re` holds the GIL and cannot be preempted. A predicate is the same class of input — authored in a spec, executed against data — so it needs an equivalent bound. Because the structured form has no backtracking, the bound can be **structural and enforced once at load** rather than temporal and enforced per value:

| Bound | Value | Reason |
|-------|-------|--------|
| Maximum nesting depth | 8 | Bounds recursion; no legitimate constraint approaches it. |
| Maximum node count | 64 | Bounds the walk. |
| Maximum literal list length | 256 | Bounds the cost of `in`/`not_in`. |

Worst-case evaluation is then 64 × 256 primitive comparisons per record, with no operator whose cost is superlinear in the value. This is a stronger guarantee than the regex timeout, which fails a value closed at runtime and can only be discovered by hitting it; a predicate that exceeds a bound is rejected at load, loudly, once. If `matches` is ever added, it must go through `_matches_within_timeout` and the temporal bound comes back with it.

**Value semantics, chosen so a rule cannot silently stop firing:**

- An absent or null field value makes every operator false except `is_not_set`. An author who needs the other reading writes it explicitly: `{any: [{field: name, op: is_not_set}, {field: name, op: "!=", value: Input}]}`. The consequence is that a predicate over an optional field selects only records where the field is set, which is stated in the reference documentation rather than left to be discovered.
- `==`, `!=`, `in`, `not_in` are type-safe: a type mismatch is simply false.
- An ordering operator (`>`, `>=`, `<`, `<=`) applied to operands that are not both numeric, or not both dates, produces a **validation error against that record**, not a false. A silent false would let a mistyped comparison disable a constraint for exactly the records it was written to catch — the failure mode the issue reports.

**Where predicates are checked: at profile load.** `SpecLoader.load_profile` (`src/metaseed/specs/loader.py:212-254`) is the single point every caller passes through, and it already converts a Pydantic failure into `SpecLoadError` naming the location. The check runs there, after `_merge_rule_constraints_into_fields` (`loader.py:246`), and raises in the same loud style as the unknown-rule-type error in `engine.py:389-394`. Checking at engine construction instead would mean a rule scoped to an entity nobody validates never gets checked, which reproduces the defect class the issue describes. The same function is called by `SpecBuilder.validate` (`src/metaseed/specs/builder.py:643-680`), which today inspects no rules at all, so `spec_validate` reports predicate problems in its issue list.

Load-time spec errors: an unknown field name; an unknown operator; a bound exceeded; a `where` on a `cardinality` rule whose `field` is not a list of entities; a `require` naming an undeclared field; `when` without `require` or `require` without `when`; and `when` together with the legacy `condition` on the same rule, which is ambiguous and is rejected rather than resolved by precedence.

### 3. A predicate sees one record, and only that record

**Chosen:** the namespace of a predicate is the fields of the record it is evaluated against. Which record that is depends on the rule type, and the difference is deliberate:

| Rule | Key | Record the predicate sees |
|------|-----|---------------------------|
| `conditional` | `when` | The entity being validated — the same `data` dict that reaches `ValidationRule.validate` (`rules.py:502`). |
| `cardinality` | `where` | Each **item** of the list named by `field` — a child entity, not the parent. |
| `uniqueness` | `where` | The record whose field value is being counted, as visited by `_traverse_entity_tree` (`dataset.py:262-290`). |

The cardinality case is the one that needs stating plainly: in `where: is_display_column == true` on `field: attributes`, `is_display_column` is read from each `SampleAttribute`, not from the `SampleType`. The rule already reaches one level down through `field`; the predicate does not add any traversal of its own.

**Deliberately out of scope:** the parent's fields, ancestors' fields, other entity types, dereferencing a reference field, dotted paths of any kind, and aggregate functions inside a predicate (`count`, `sum`). All four SEEK constraints need only own-record fields. The asymmetry is the reason to start here: adding a parent scope later is additive — a new key, or a reserved prefix — and every spec written against the narrow scope keeps its meaning; removing a scope once specs use it is a breaking change to the format.

### 4. This lands in `spec_version` 0.7

`ValidationRuleSpec` sets `model_config = ConfigDict(extra="forbid")` (`src/metaseed/specs/schema.py:315`), so three new keys are a format change. The highest `spec_version` currently shipped is `0.6` (`src/metaseed/specs/ena/1.0/profile.yaml`, `src/metaseed/specs/isa/1.0/profile.yaml`), so `where`, `when` and `require` are **spec_version 0.7**, added to the table in `docs/api/schema-specs.md`.

**An older spec read by new metaseed** is unaffected. The keys are optional; absent means the behaviour is what it is today, evaluated by the same code paths with no predicate step. Nothing in the loader branches on `spec_version` — it only defaults the field when the key is missing (`loader.py:229-231`) — and this change does not add a runtime gate, consistent with how the constructs in 0.2 through 0.6 were introduced.

**A 0.7 spec read by an older metaseed fails at load**, which is the correct behaviour and must not be softened. `ProfileSpec.model_validate` raises, and `loader.py:232-244` renders the first error as:

```
SpecLoadError: Invalid profile /path/to/profile.yaml at validation_rules.3.where:
Extra inputs are not permitted
```

(verified against `ValidationRuleSpec` as it stands). Relaxing `extra="forbid"` to make old metaseed tolerate the key would drop the constraint and certify data the profile author intended to reject — precisely the failure the issue reports.

The message names the key but not the cause. This work should therefore also introduce a `SUPPORTED_SPEC_VERSION` constant — metaseed currently has no record of which format versions it understands, only a documentation table — so the loader can add, when a document declares a `spec_version` above the supported one and the parse failed with `extra_forbidden`, a second sentence naming the mismatch: `profile declares spec_version 0.7; this metaseed supports up to 0.6`. Without the constant that message cannot be produced.

### 5. The comparator classifies a predicate change on its own terms

Today `_rule_changes` (`compare.py:600-640`) has three outcomes: a rule added is `validation_rule_added` (BREAKING), a rule removed is `validation_rule_removed` (COMPATIBLE), and any inequality between two rules of the same name is `validation_rule_changed` (BREAKING). A predicate edit would fall into the last one and always report BREAKING.

**The general question:** does adding a `where` that narrows an existing rule reject strictly less data? For a rule body R and a predicate P, the new rule fails a record iff `P(record) and R fails`, and the old rule failed iff `R fails`. New failures are a subset of old failures, so the change is compatible. **Except for `cardinality` with a `min_items`:** there the predicate narrows the counted population, and a count that satisfied a lower bound before can fall below it after. A record with 24 attributes and `min_items: 1` passed; the same record with `where: is_display_column == true` counts 0 and fails. So adding a `where` to a lower-bounded cardinality rule is BREAKING, and this is not a corner case — it is the shape of the issue's own headline constraint.

**Chosen classification.** Three new change kinds replace `validation_rule_changed` when the only difference between two same-named rules is the predicate:

| Change | Kind | Compatibility | `required_bump` |
|--------|------|---------------|-----------------|
| Predicate added where none existed, `conditional` `when` (rule body otherwise unchanged) | `rule_predicate_added` | COMPATIBLE | `minor` |
| Predicate added where none existed, `uniqueness` | `rule_predicate_added` | COMPATIBLE | `minor` |
| Predicate added where none existed, `cardinality` with `max_items` only | `rule_predicate_added` | COMPATIBLE | `minor` |
| Predicate added where none existed, `cardinality` with `min_items` set | `rule_predicate_narrowed_count` | BREAKING | `major` |
| Predicate widened (selects a superset) | `rule_predicate_changed` | BREAKING | `major` |
| Predicate narrowed (selects a subset) | `rule_predicate_changed` | BREAKING | `major` |
| Predicate removed | `rule_predicate_removed` | BREAKING | `major` |

Adding `require` to a conditional rule that previously had only `condition` is a change to the rule body, not to a predicate, and stays `validation_rule_changed` (BREAKING).

**Why widening and narrowing are not distinguished.** Deciding whether one predicate selects a superset of another is predicate containment, which this comparator cannot settle in general (`{field: a, op: in, value: [x, y]}` against `{field: a, op: "!=", value: z}` depends on the domain of `a`). The module's stated policy is to err toward breaking, and it already applies exactly this reasoning to regular expressions: any pattern that changes but stays set is reported as tightened because containment "is not decidable here" (`compare.py:9-17`, `compare.py:325-340`). Predicate edits follow the same precedent. The consequence is that a genuinely narrowing edit is over-reported as MAJOR; the author who knows better can still publish a MINOR, since `required_bump` reports a floor rather than enforcing one.

**Why "predicate added where none existed" *is* decided.** That case needs no containment analysis: absence means every record is selected, so any predicate selects a subset by construction, whatever it says. The classification follows from the shape alone, plus the `min_items` caveat above, which is also decidable from the rule's own keys.

### 6. A predicate-scoped failure reports the subset it counted

"expected exactly 1, got 0" is unactionable when the reader cannot see which of 24 children were counted or why. Every message from a predicated rule carries five parts: the subject (entity type, its declared label or identifier, and the path), the comparison (bound, matched count, population size), the rendered predicate, the matched members (capped, with a residual count), and the rule name.

The four SEEK constraints, in the shapes they should produce:

**1. `cv_terms` required when `data_type` is `Controlled Vocabulary`** — field `cv_terms`:

```
SampleAttribute 'Sample Origin' (attributes[6]): field 'cv_terms' is required when
data_type == 'Controlled Vocabulary' [rule: cv_terms_required_for_controlled_vocabulary]
```

**2. Exactly one display column** — field `attributes`, the case the external checker caught:

```
SampleType 'CropXR extended metadata controlled vocabulary upload': expected exactly 1
of 24 'attributes' to match is_display_column == true, found 0
[rule: exactly_one_display_column]
```

and where the count is non-zero, the offenders are named:

```
SampleType 'Plant material': expected exactly 1 of 18 'attributes' to match
is_display_column == true, found 2: attributes[3] 'Sample Name', attributes[9] 'Title'
[rule: exactly_one_display_column]
```

**3. At most one `Registered Sample List`** — field `attributes`:

```
SampleType 'Assay sample': expected at most 1 of 24 'attributes' to match
data_type == 'Registered Sample List', found 2: attributes[4] 'Input',
attributes[17] 'Input 2' [rule: at_most_one_registered_sample_list]
```

**4. Singleton ISA tags with `Input` exempt** — field `isa_tag`, reported against the duplicate:

```
SampleAttribute 'Growth Protocol' (attributes[7]): isa_tag 'protocol' duplicates
attributes[2] within parent SampleType 'Assay sample'; counted among attributes matching
isa_tag in ['source', 'protocol', 'sample', 'data_file', 'other_material'] and
name != 'Input' [rule: singleton_isa_tags]
```

Two supporting decisions:

- **The label comes from the declared identity markers.** `FieldSpec` carries `is_identifier` and `is_label` (spec_version 0.6), and the facade exposes `identifier_field`; the message uses the declared label, falls back to the identifier, and falls back to the path. It does not guess from field names.
- **`message:` no longer discards the counts.** Today a custom `message` replaces the generated text entirely (`rules.py:583-607`), which for a predicated rule would throw away the only actionable part. For predicated rules the custom message is emitted first and the generated detail is appended after it. Non-predicated rules keep today's replace semantics, so no existing profile changes behaviour.

### 7. The UI gets a guided predicate builder, in this work and not after it

The project rule is that a feature is done when it is usable from the UI and covered by tests. The rule editor is `src/metaseed/ui/templates/spec_builder/partials/validation_rule_form.html` — a type selector plus per-type field groups toggled by `showRuleTypeFields()`, posting flat form fields to `PUT /spec-builder/validation-rule/{idx}` (`src/metaseed/ui/spec_builder/routes_rules.py:187-242`), which copies them onto the rule through `RuleUpdateData.apply_to_rule` (`routes_rules.py:55-79`).

**Chosen: a guided row builder, not free text.** The predicate is edited as repeated rows of (field, operator, value) with an `all`/`any` toggle for the group, posted as indexed form fields and assembled server-side into the structured predicate. The field selector is populated from the declared fields of the relevant entity — the entity itself for `when`, the *item* entity resolved from `FieldSpec.items` for a cardinality `where`. That is the decisive argument: the load-time "unknown field" spec error becomes unreachable from the editor, because the editor only offers fields that exist. A free-text box would move the whole class of authoring error to load time, after saving, which is the experience this design is trying to remove elsewhere.

Its limit is that a flat group cannot express nesting. All four SEEK constraints are flat, so the limit costs nothing today. A predicate loaded from YAML that the builder cannot represent is rendered read-only with its one-line `render_predicate()` text and a note saying it must be edited in YAML — it is neither flattened nor dropped.

**In scope for the same change, not a follow-up:**

- the rule form, the route, `RuleUpdateData`, and the rules-list rendering (which shows the rendered predicate under the rule name);
- `spec_add_rule` and `spec_update_rule` in the MCP tools (`src/metaseed/agent/mcp/tools/spec_builder.py:627-680`). Note these currently accept only `name`, `type`, `message`, `applies_to`, `field` and `reference` — not `condition`, `min_items`, `max_items` or `unique_within` — so an agent cannot author any of the three affected rule types end to end today. A predicate parameter alone would be unusable; those parameters are part of this work;
- `SpecBuilder.validate` calling the load-time predicate checker so `spec_validate` lists predicate problems (`builder.py:643-680` inspects no rules at all today);
- UI tests alongside `tests/test_ui/test_spec_builder.py`, each proved red first.

The hub has its own rule editor. The contract it needs is the `ValidationRuleSpec` schema plus the predicate model, the checker, and `render_predicate()` exported as public API, so the hub renders and validates predicates with the same code rather than reimplementing the operator table.

## Worked example: the four SEEK constraints

```yaml
spec_version: '0.7'

validation_rules:
  # 1. A Controlled Vocabulary attribute must carry cv_terms.
  - name: cv_terms_required_for_controlled_vocabulary
    type: conditional
    applies_to: [SampleAttribute]
    when:
      field: data_type
      op: "=="
      value: Controlled Vocabulary
    require: [cv_terms]

  # 2. Exactly one attribute per sample type is the display column.
  - name: exactly_one_display_column
    type: cardinality
    applies_to: [SampleType]
    field: attributes
    where:
      field: is_display_column
      op: "=="
      value: true
    min_items: 1
    max_items: 1

  # 3. At most one attribute per sample type is a Registered Sample List.
  - name: at_most_one_registered_sample_list
    type: cardinality
    applies_to: [SampleType]
    field: attributes
    where:
      field: data_type
      op: "=="
      value: Registered Sample List
    max_items: 1

  # 4. Each singleton ISA tag is used at most once per sample type;
  #    attributes named Input are exempt from the count.
  - name: singleton_isa_tags
    type: uniqueness
    applies_to: [SampleAttribute]
    field: isa_tag
    unique_within: parent
    where:
      all:
        - field: isa_tag
          op: in
          value: [source, protocol, sample, data_file, other_material]
        - field: name
          op: "!="
          value: Input
```

Rendered for messages and for the UI, these read exactly as the issue wrote them: `data_type == 'Controlled Vocabulary'`, `is_display_column == true`, `data_type == 'Registered Sample List'`, and `isa_tag in ['source', 'protocol', 'sample', 'data_file', 'other_material'] and name != 'Input'`.

Comparator outcome for adding these four rules to an existing profile: all four are new rules, so all four are `validation_rule_added` and `required_bump` is `major`. Adding the `where` to rule 2 *later*, on an existing `min_items: 1` rule, would also be `major` (decision 5); adding the `where` to rule 3 later would be `minor`.

## What shipped

All three slices, in the order below. One finding from doing it is recorded here
because it changed what "done" means: a rule scoped to a **nested** entity never
fired through `DatasetValidator` at all. A profile writes `SampleAttribute`, the
validator reaches a nested child as `sample_attribute` and its own root as
`sampletype`, and `_applies_to_entity` compared on case alone — so the root
matched and every nested entity missed, silently disabling 54 rules across the
shipped profiles. Slice 3's motivating constraint is a rule on a nested entity,
so it could not work until that was fixed. Blast radius measured against every
shipped example before shipping: no error count changed.

## First implementation slice

**Slice 1 is `cardinality` with `where`.** Reasons, in order:

- It is the constraint that found the real defect. The zero-display-column template is the issue's only evidence of data that metaseed currently certifies wrongly, so this slice is the one that can be demonstrated end to end against real input.
- It needs no new plumbing. `ListCardinalityRule` already receives the parent record with its children nested inside it on both engine paths — `validators/api.py` recursion and `DatasetValidator._validate_entity` (`dataset.py:418-462`) — so the predicate is the only new thing.
- It exercises every part of the design once: the schema key, the predicate model, the load-time checker, the evaluator, the message shape with counts, the comparator classification including the `min_items` caveat, the UI builder, and the MCP parameters. Slices 2 and 3 are then wiring against a settled contract.

**Slice 2 is `uniqueness` with `where`**, implemented in `DatasetValidator._load_uniqueness_rules`/`_validate_uniqueness`, because that is where uniqueness is actually enforced (finding 2). The inert `UniquenessRule` has since been deleted, so the dataset validator is the only site to change.

**Slice 3 is `conditional` with `when`/`require`**, last because it is entangled with the legacy `condition` parser: the two keys must coexist without either changing the other's behaviour, and that question is independent of predicates.

Ordering note: the `validate_extracted` gap (finding 1) is a prerequisite for the issue's definition of done but not for any of these slices. It was handled as its own change, since wiring the rule engine into `ExtractionContext` changes the results of an existing tool for every profile, predicate or not. A predicated `cardinality` rule reaches that path only for a list of scalars; over a child collection it is skipped there for the reason in finding 3.

## What this design does not cover

- **Running validation rules in `validate_extracted`.** Done as a separate change with its own compatibility question (see finding 1); nothing about predicates was decided by it.
- **Cardinality over children in the facade path.** Children are separate nodes there (finding 3); materialising them for validation, or declaring that path out of scope for collection rules, is undecided here.
- **The legacy `condition` parser.** `_extract_fields` and `_evaluate` (`rules.py:446-500`) stay exactly as they are, including their sharp edges (string substitution over field names; `and`/`or` in lower case are not operators). Nothing in this design changes, fixes, or deprecates them.
- **The duplicated uniqueness implementation.** Two enforcement sites remain, one of them inert.
- **Regex and aggregate operators in predicates**, and any traversal beyond the single record described in decision 3.
- **Predicate containment analysis** in the comparator; every predicate-to-predicate edit is reported BREAKING.
- **The coarse classification of non-predicate rule edits.** A cosmetic `message:` or `description:` change on a rule is still `validation_rule_changed` and therefore still reports `major` (`compare.py:629-639`). That is a pre-existing over-report, adjacent but not addressed.
- **Predicates anywhere other than these three rule types** — not on field constraints, not on `applies_to`, not on entity definitions.
- **Authoring the `seek-template-model` profile.** It is not in this repository; only the format it needs is decided here.
- **Localisation of the message shapes in decision 6.**

## Consequences

### Positive

- The four SEEK constraints become expressible, and the external Python checker can be retired once slices 1 to 3 land and the `validate_extracted` prerequisite is resolved.
- Predicates cost nothing at the content-hash and comparator layers: they are canonical by construction, so reformatting is not a change and a MAJOR bump is never forced by whitespace.
- The safety bound is static and verified at load, which is a stronger guarantee than the per-value regex timeout it is modelled on.
- A predicate that names a field the entity does not declare is rejected at profile load, so a rule cannot silently never run.

### Negative

- Predicates are more verbose to hand-write than the string syntax the issue proposed. The guided UI builder and the MCP parameters absorb most of that, but a profile author working directly in YAML pays it.
- A genuinely narrowing predicate edit is over-reported as BREAKING, so some MINOR releases will be labelled MAJOR by the comparator unless the author overrides.
- Nested predicates are authorable but not editable in the UI, which is a visible seam until nesting is either supported or ruled out.

### Neutral

- `spec_version` remains declarative: nothing branches on it at runtime, so a 0.7 construct in a spec declaring 0.5 is accepted. This design keeps that property rather than introducing gating for one construct.
- The string syntax survives as the display and rendering form, so the issue's examples remain the reader-facing spelling even though they are not the stored one.

## References

- Issue #211 — the constraints that could not be encoded, and the proposed string grammar
- `src/metaseed/validators/rules.py` — `ConditionalRule`, `ListCardinalityRule`, `_matches_within_timeout` (line numbers as of this date; `UniquenessRule` and `EntityReferenceRule` have since been deleted)
- `src/metaseed/validators/engine.py` — `_VALID_RULE_TYPES` (137-151), rule construction (154-253), loud rejection of an unknown type (389-394)
- `src/metaseed/validators/dataset.py` — `_load_uniqueness_rules` (159), `_traverse_entity_tree` (262), `_validate_uniqueness` (358), `_validate_entity` (418)
- `src/metaseed/agent/core.py` — `validate_instance` (376), `_validate_field` (409)
- `src/metaseed/specs/schema.py` — `ValidationRuleSpec` (288-335), `extra="forbid"` (315)
- `src/metaseed/specs/loader.py` — `spec_version` default (229-231), load error rendering (232-244)
- `src/metaseed/specs/versioning.py` — `canonical_json` (130-161)
- `src/metaseed/specs/compare.py` — module policy (9-24), `_pattern_change` precedent (325-340), `_rule_changes` (600-640)
- `src/metaseed/specs/builder.py` — `add_rule` (577), `update_rule` (587), `validate` (643)
- `src/metaseed/agent/mcp/tools/spec_builder.py` — `spec_validate` (266), `spec_add_rule` (627), `spec_update_rule` (655)
- `src/metaseed/ui/spec_builder/routes_rules.py` — `RuleUpdateData` (22-79), update route (187-242)
- `docs/api/schema-specs.md` — specification format versions, rule types, profile versioning
