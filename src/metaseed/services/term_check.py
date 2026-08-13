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

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from metaseed.specs.schema import FieldSpec


class Outcome(StrEnum):
    """What was learned about a value."""

    OK = "ok"
    NOT_IN_ONTOLOGY = "not_in_ontology"
    NOT_IN_BRANCH = "not_in_branch"
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
        return self.outcome in (
            Outcome.NOT_IN_ONTOLOGY,
            Outcome.NOT_IN_BRANCH,
            Outcome.NOT_FOUND,
        )


class Materialisation(StrEnum):
    """How expensive it is to hold a source's data locally.

    A statement for a consumer that materialises sources -- imports an ontology
    into its own store -- to act on before it starts, rather than discover
    mid-import: GAZ is around 180 MB, ChEBI and NCBITaxon the same class (#247).
    metaseed itself materialises nothing, so it skips nothing on this basis; it
    carries the declaration so a consumer reads one interface instead of
    inventing its own.
    """

    NONE = "none"
    """Nothing to hold: a remote service answered over the network."""

    CHEAP = "cheap"
    """Small enough that holding it needs no decision."""

    LARGE = "large"
    """Big enough that a consumer should decide deliberately."""

    UNKNOWN = "unknown"
    """The source did not say."""


_MATERIALISATION_ORDER = (
    Materialisation.NONE,
    Materialisation.CHEAP,
    Materialisation.UNKNOWN,
    Materialisation.LARGE,
)
"""Least to most demanding, for reporting the worst case a router holds."""


@dataclass(frozen=True)
class SourceCapabilities:
    """What a source says about itself before anyone asks it a question.

    Attributes:
        name: How to name this source when reporting what was asked or skipped.
        interactive: Whether it can answer inside a typeahead's budget. A
            picker debounces at 300 ms; a source measured at 51 seconds is not
            slow, it is unusable there, while remaining exactly the right thing
            to validate against (#247). Defaults to ``True``: an adapter that
            declares nothing behaves as it always has.
        materialisation: How expensive the source is to hold locally.
        note: Why, in a few words, for whoever reads the report.
    """

    name: str = ""
    interactive: bool = True
    materialisation: Materialisation = Materialisation.UNKNOWN
    note: str = ""


class TermSource(Protocol):
    """The part of an ontology service this needs.

    A protocol rather than the service itself: the check is pure logic about
    what an answer means, testing it must not depend on EBI being up, and a
    source that is not OLS — AgroPortal carries the Crop Ontology that OLS does
    not, and a consortium's own list is nowhere public — should be able to
    answer without this module knowing anything about it. OLS is one adapter;
    :mod:`metaseed.services.terms` holds the rest and the order they are asked
    in.
    """

    def get_term_sync(self, term_id: str) -> object | None:
        """The term, or ``None`` when the ontology does not have it."""
        ...

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        """Whether this source hosts the ontology; ``None`` if it cannot say."""
        ...

    def is_within_sync(self, term_id: str, ancestor: str) -> bool | None:
        """Whether ``term_id`` sits beneath ``ancestor``; ``None`` if unknown.

        Optional, and ``None`` is a real answer rather than a failure: a flat
        vocabulary file has no parents to walk, and a service that did not
        respond has not said no. Both mean *not checked*; only a source that
        can see the hierarchy and looked may answer ``False``.

        A term is within itself. "Within this branch" reads inclusively, and
        rejecting the branch root would be a surprising way to fail.
        """
        ...

    def capabilities(self) -> SourceCapabilities:
        """What this source can do, declared rather than discovered.

        Optional. A source that does not implement it is read as the defaults:
        usable interactively, cost unstated. Silence must not make an adapter
        written before this existed unusable.
        """
        ...

    def search_sync(
        self, query: str, ontology: str | None = None, limit: int = 20
    ) -> Sequence[object]:
        """Terms matching ``query``, for a picker.

        Optional: a source that can confirm a term is useful even if it cannot
        be browsed, and :class:`~metaseed.services.terms.TermRouter` skips the
        ones that do not offer this.
        """
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
    within: str | None = None,
) -> TermVerdict:
    """Check ``value`` against the ontologies a field names.

    Args:
        value: The value as written in the dataset.
        ontologies: The ontologies the field allows, by id. ``None`` or empty
            means any: the value is still checked to be a real term, and only
            the restriction is lifted. Stated rather than implied, because two
            shipped profiles depend on it (#246).
        source: Where to ask whether a term exists. ``None`` asks the
            application's router, which holds whichever adapters are
            configured — local vocabularies, OLS, or both.
        within: The branch the field restricts values to, if it declares one.
            Checked only once the term is known to exist: where a value sits is
            not a question worth asking about a value that is not a term.

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
        from metaseed.services.terms import get_term_source

        source = get_term_source()

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
        # Before calling a value wrong, ask whether this source can see the
        # ontology at all. OLS4 hosts `to` but not `co_321`, which MIAPPE names
        # beside it, so every Crop Ontology term would be reported as missing
        # from a vocabulary the service simply does not carry.
        hosts = getattr(source, "has_ontology_sync", None)
        available = hosts(prefix) if callable(hosts) else True
        if available is not True:
            return TermVerdict(
                Outcome.NOT_CHECKED,
                f"'{value}' could not be checked: the term service does not "
                f"carry {prefix}.",
                allowed,
            )
        return TermVerdict(
            Outcome.NOT_FOUND, f"'{value}' is not a term in {prefix}.", allowed
        )

    if within:
        return _branch_verdict(value, within, source, allowed)

    return TermVerdict(Outcome.OK, None, allowed)


def _branch_verdict(
    value: str,
    within: str,
    source: TermSource,
    allowed: tuple[str, ...],
) -> TermVerdict:
    """Whether a term that exists also sits where the field says it must.

    Three outcomes again, for the same reason: a source with no hierarchy and a
    source that would not answer have both failed to establish anything, and
    reporting that as "outside the branch" would turn a gap in what we know into
    a fault in someone's data.
    """
    if value.strip().lower() == within.strip().lower():
        # A term is within itself; see the port's docstring.
        return TermVerdict(Outcome.OK, None, allowed)

    asks = getattr(source, "is_within_sync", None)
    if not callable(asks):
        return TermVerdict(
            Outcome.NOT_CHECKED,
            f"'{value}' could not be checked against {within}: the term source "
            f"has no hierarchy to walk.",
            allowed,
        )
    try:
        answer = asks(value, within)
    except Exception:
        return TermVerdict(
            Outcome.NOT_CHECKED,
            f"'{value}' could not be checked against {within}: the ontology "
            f"service did not answer.",
            allowed,
        )
    if answer is True:
        return TermVerdict(Outcome.OK, None, allowed)
    if answer is None:
        return TermVerdict(
            Outcome.NOT_CHECKED,
            f"'{value}' could not be checked against {within}: the term source "
            f"could not say where it sits.",
            allowed,
        )
    return TermVerdict(
        Outcome.NOT_IN_BRANCH,
        f"'{value}' is not beneath {within}, which is what this field takes.",
        allowed,
    )


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
        verdicts[field.name] = check_term(
            str(value), field.ontologies, source, within=field.within
        )
    return verdicts
