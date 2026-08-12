"""Where a term is looked up, and in what order.

OLS4 is the default and covers most of what the shipped profiles name. It is
not the only place a term can live: it hosts ``to`` but not ``co_321``, which
MIAPPE names beside it, a consortium's own list exists nowhere public, and a
laptop in a glasshouse has no network at all.

So OLS is one adapter among several, and the application asks a router rather
than a service. The router's rule is that a source claiming an ontology is
authoritative for it — a term missing from a vocabulary we hold is missing, and
falling through to a public service would silently widen a list somebody
narrowed on purpose. When nobody can say, the answer is ``None``, which the
check reports as *not checked* rather than as invalid.

See ``docs/architecture/term-sources.md``.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.services.term_check import TermSource

logger = logging.getLogger(__name__)

#: Directory of local vocabulary files loaded at first use. Unset means OLS
#: alone, which is the behaviour that existed before local vocabularies.
VOCABULARY_DIR_ENV = "METASEED_VOCABULARIES"


@dataclass(frozen=True)
class TermHit:
    """One search result, whichever source produced it.

    Attributes:
        id: The term identifier as the source writes it.
        label: Its human-readable name.
        ontology: The ontology it belongs to, where the source says.
        description: A definition, where the source has one.
        source: Which adapter answered, so a local addition is distinguishable
            from a public term in a picker.
    """

    id: str
    label: str = ""
    ontology: str | None = None
    description: str | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """The shape the pickers consume."""
        return {
            "value": self.id,
            "label": self.label,
            "ontology": self.ontology,
            "description": self.description,
            "source": self.source,
        }


def _owns(source: object, ontology_id: str | None) -> bool:
    """Whether ``source`` claims to carry ``ontology_id``.

    Only an explicit ``True`` counts. A source that cannot say — an outage, an
    adapter that does not implement the question — has not claimed anything,
    and must not be treated as the last word on a term.
    """
    if not ontology_id:
        return False
    asks = getattr(source, "has_ontology_sync", None)
    if not callable(asks):
        return False
    try:
        return asks(ontology_id) is True
    except Exception:
        return False


def _as_hit(result: object, source_name: str) -> TermHit:
    """Normalise whatever an adapter returns into a :class:`TermHit`."""
    term_id = getattr(result, "term_id", None) or getattr(result, "id", "")
    return TermHit(
        id=str(term_id),
        label=str(getattr(result, "label", "") or ""),
        ontology=getattr(result, "ontology", None),
        description=getattr(result, "description", None),
        # A result that names its own origin — the file a local term came from —
        # says more than the adapter's class name, so it wins.
        source=str(getattr(result, "source", "") or source_name),
    )


@dataclass
class TermRouter:
    """Several term sources asked as one, in order.

    Implements :class:`~metaseed.services.term_check.TermSource` itself, so a
    router can be handed anywhere a single source is expected — including to
    another router.
    """

    sources: list[Any] = field(default_factory=list)

    def get_term_sync(self, term_id: str) -> object | None:
        """The term from the first source that has it, or ``None``.

        The first source claiming the term's ontology is asked alone: if it
        does not list the term, the term is not in that vocabulary, and asking
        anything else afterwards would answer about a different one. Later
        claimants do not get a say — two sources holding the same ontology is
        exactly the case where order has to decide.
        """
        from metaseed.services.term_check import ontology_of

        prefix = ontology_of(term_id)
        owner = next((s for s in self.sources if _owns(s, prefix)), None)
        for source in [owner] if owner is not None else self.sources:
            try:
                term: object | None = source.get_term_sync(term_id)
            except Exception:
                # Someone else's outage is not the next source's problem, and
                # it is certainly not the dataset's. Logged rather than
                # swallowed: a source that always fails is a misconfiguration,
                # and silence is how it survives.
                logger.warning(
                    "term source %s failed on %s",
                    type(source).__name__,
                    term_id,
                    exc_info=True,
                )
                continue
            if term is not None:
                return term
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        """Whether any source carries the ontology.

        ``False`` only when every source said so plainly. If any could not
        answer, the honest result is ``None``: we do not know.
        """
        unknown = False
        for source in self.sources:
            asks = getattr(source, "has_ontology_sync", None)
            if not callable(asks):
                continue
            try:
                answer = asks(ontology_id)
            except Exception:
                unknown = True
                continue
            if answer is True:
                return True
            if answer is None:
                unknown = True
        if unknown:
            return None
        return False if self.sources else None

    def search_sync(
        self,
        query: str,
        ontology: str | None = None,
        limit: int = 20,
        within: str | None = None,
    ) -> list[TermHit]:
        """Search every source that can search, nearest first.

        Local results come first because they are the ones a public service
        cannot offer at all. Duplicates are dropped by term id, keeping the
        earlier — and therefore more local — answer.

        Args:
            query: What the person typed.
            ontology: Restrict to this ontology.
            limit: Most results to return.
            within: Restrict to terms beneath this one. A source that cannot
                honour a subtree is **skipped** rather than allowed to answer
                unrestricted: offering the whole ontology to a column that asked
                for one branch of it is the thing the restriction exists to
                prevent.
        """
        hits: list[TermHit] = []
        seen: set[str] = set()
        for source in self.sources:
            searches = getattr(source, "search_sync", None)
            if not callable(searches):
                continue
            try:
                if within:
                    results = self._search_within(
                        searches, query, ontology, limit, within
                    )
                    if results is None:
                        logger.debug(
                            "term source %s cannot restrict to a branch; skipped",
                            type(source).__name__,
                        )
                        continue
                else:
                    results = searches(query, ontology, limit)
            except Exception:
                logger.warning(
                    "term source %s failed searching %r",
                    type(source).__name__,
                    query,
                    exc_info=True,
                )
                continue
            for result in results or []:
                hit = _as_hit(result, type(source).__name__)
                if not hit.id or hit.id in seen:
                    continue
                seen.add(hit.id)
                hits.append(hit)
                if len(hits) >= limit:
                    return hits
        return hits

    @staticmethod
    def _search_within(
        searches: Any, query: str, ontology: str | None, limit: int, within: str
    ) -> list[Any] | None:
        """Search with a subtree restriction, or ``None`` if unsupported.

        Duck-typed rather than declared on the protocol: an adapter written
        before branches existed keeps working, and simply does not answer
        branch-scoped queries.
        """
        try:
            return list(searches(query, ontology, limit, within=within))
        except TypeError:
            return None

    async def get_term(self, term_id: str) -> object | None:
        """:meth:`get_term_sync` off the event loop.

        Adapters are synchronous by contract — the simplest ones are a dict in
        a file — so an async caller must not resolve a term inline: one
        unreachable service would stall every other request in the process.
        """
        import anyio.to_thread

        return await anyio.to_thread.run_sync(self.get_term_sync, term_id)

    async def search(
        self,
        query: str,
        ontology: str | None = None,
        limit: int = 20,
        within: str | None = None,
    ) -> list[TermHit]:
        """:meth:`search_sync` off the event loop."""
        from functools import partial

        import anyio.to_thread

        return await anyio.to_thread.run_sync(
            partial(self.search_sync, query, ontology, limit, within)
        )


_router_var: ContextVar[TermRouter | None] = ContextVar("term_router", default=None)


def _default_router() -> TermRouter:
    """Local vocabularies if any are configured, then OLS.

    Ordering is the whole configuration: local first means offline work
    resolves without a network round trip, and a vocabulary held locally
    answers for itself rather than being second-guessed by a public service.
    """
    from metaseed.services.local_terms import VocabularyStore
    from metaseed.services.ontology import get_ontology_service

    sources: list[Any] = []
    directory = os.environ.get(VOCABULARY_DIR_ENV, "").strip()
    if directory:
        store = VocabularyStore.from_directory(directory)
        if store.vocabularies:
            sources.append(store)
    sources.append(get_ontology_service())
    return TermRouter(sources=sources)


def get_term_source() -> TermRouter:
    """The router this context asks about terms.

    Built on first use and kept for the context, like the ontology service it
    composes, so a request or a test can install its own sources without
    reaching into global state.
    """
    router = _router_var.get()
    if router is None:
        router = _default_router()
        _router_var.set(router)
    return router


def register_term_source(source: TermSource, *, first: bool = False) -> TermRouter:
    """Add an adapter to this context's router.

    Args:
        source: Anything answering the ``TermSource`` questions.
        first: Ask it before the sources already registered. Use this for a
            vocabulary that should answer for itself rather than deferring to
            a public service.

    Returns:
        The router, so a caller can hold it directly.
    """
    router = get_term_source()
    if first:
        router.sources.insert(0, source)
    else:
        router.sources.append(source)
    return router


def reset_term_sources() -> None:
    """Forget this context's router, so the next call rebuilds it."""
    _router_var.set(None)
