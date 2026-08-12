"""Checking a value against the ontology its field names.

A profile can already say where a value must come from::

    - name: trait_accession_number
      type: ontology_term
      ontologies: ["to", "co_321"]

Nothing read the second line. ``validate_term`` asked OLS whether the term
exists *anywhere*, so ``PATO:0000001`` passed a field that demands a trait
ontology term, and the pointer was decoration (issue #215).

Three outcomes, not two. A term can be right, wrong, or **unchecked** — and an
OLS outage must produce the third, never the second: someone else's downtime
must not mark a researcher's data invalid. That distinction is the whole point
of this module; a boolean cannot carry it, which is why the existing fail-open
check silently reported "fine" when it had learned nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from metaseed.specs.schema import FieldSpec


class Outcome(StrEnum):
    """What was learned about a value."""

    OK = "ok"
    NOT_IN_ONTOLOGY = "not_in_ontology"
    NOT_FOUND = "not_found"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class TermVerdict:
    """The result of checking one value.

    Attributes:
        outcome: What was established.
        message: What to tell a person, or ``None`` when there is nothing to say.
        ontologies: The ontologies the field named, for the message.
    """

    outcome: Outcome
    message: str | None = None
    ontologies: tuple[str, ...] = ()

    @property
    def is_problem(self) -> bool:
        """Whether this should be shown as something to fix.

        ``NOT_CHECKED`` is not a problem with the data — it is a gap in what we
        know — and reporting it as one turns an OLS outage into hundreds of
        false errors across a dataset.
        """
        return self.outcome in (Outcome.NOT_IN_ONTOLOGY, Outcome.NOT_FOUND)


class TermSource(Protocol):
    """The part of an ontology service this needs.

    A protocol rather than the service itself: the check is pure logic about
    what an answer means, and testing it must not depend on EBI being up.
    """

    def get_term_sync(self, term_id: str) -> object | None:
        """The term, or ``None`` when the ontology does not have it."""
        ...


def ontology_of(term_id: str) -> str | None:
    """The ontology prefix a term id names, lowercased, or ``None``.

    ``TO:0000387`` names ``to``; ``NCBITaxon_3702`` names ``ncbitaxon``. A value
    with neither separator is a plain label, and a label cannot be traced to an
    ontology without asking, which is a different question from this one.
    """
    for separator in (":", "_"):
        if separator in term_id:
            prefix = term_id.split(separator, 1)[0].strip()
            return prefix.lower() or None
    return None


def check_term(
    value: str,
    ontologies: list[str] | None,
    source: TermSource | None = None,
) -> TermVerdict:
    """Check ``value`` against the ontologies a field names.

    Args:
        value: The value as written in the dataset.
        ontologies: OLS ids the field allows, or ``None`` for any.
        source: Where to ask whether a term exists. ``None`` asks the
            application's shared service.

    Returns:
        A :class:`TermVerdict`. Anything that cannot be established — a value
        that is not an identifier, a service that will not answer — is
        ``NOT_CHECKED``, said plainly rather than passed off as valid.
    """
    allowed = tuple(o.lower() for o in (ontologies or []))

    if not value or not isinstance(value, str):
        return TermVerdict(Outcome.NOT_CHECKED, None, allowed)

    prefix = ontology_of(value)
    if prefix is None:
        # A label, not an identifier: this check is about identifiers, and
        # calling a label wrong would flag most of the free text people write.
        return TermVerdict(
            Outcome.NOT_CHECKED,
            None
            if not allowed
            else (
                f"'{value}' is not an ontology identifier, so it cannot be "
                f"checked against {', '.join(allowed)}."
            ),
            allowed,
        )

    if allowed and prefix not in allowed:
        return TermVerdict(
            Outcome.NOT_IN_ONTOLOGY,
            f"'{value}' comes from {prefix}, but this field takes a term from "
            f"{' or '.join(allowed)}.",
            allowed,
        )

    if source is None:
        from metaseed.services.ontology import get_ontology_service

        source = get_ontology_service()

    try:
        term = source.get_term_sync(value)
    except Exception:
        # Someone else's outage is not this dataset's problem.
        return TermVerdict(
            Outcome.NOT_CHECKED,
            f"'{value}' could not be checked: the ontology service did not answer.",
            allowed,
        )

    if term is None:
        return TermVerdict(
            Outcome.NOT_FOUND, f"'{value}' is not a term in {prefix}.", allowed
        )

    return TermVerdict(Outcome.OK, None, allowed)


def check_entity_terms(
    fields: list[FieldSpec],
    data: dict[str, object],
    source: TermSource | None = None,
) -> dict[str, TermVerdict]:
    """Check every ontology-term field of one entity.

    Returns:
        Field name -> verdict, for the fields that carry a value. Fields left
        empty are not checked: whether they should be filled is requiredness,
        a separate question with its own answer.
    """
    from metaseed.specs.schema import FieldType

    verdicts: dict[str, TermVerdict] = {}
    for field in fields:
        if field.type != FieldType.ONTOLOGY_TERM:
            continue
        value = data.get(field.name)
        if not value:
            continue
        verdicts[field.name] = check_term(str(value), field.ontologies, source)
    return verdicts
