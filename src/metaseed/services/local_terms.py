"""Vocabularies held locally, and asking them before asking the internet.

Not every vocabulary lives in OLS. OLS4 carries ``to`` but not ``co_321``,
which MIAPPE names beside it; a consortium's own list exists nowhere public; a
SEEK instance's controlled vocabularies are local by construction. And a
project that must work on a laptop in a glasshouse cannot depend on EBI
answering.

So a vocabulary can be a file: terms with their labels, carried with the
profile that needs them. Answering the same two questions as the remote
service — does this term exist, do you carry this ontology — it plugs into the
same :class:`~metaseed.services.term_check.TermSource` port, and a chain asks
the local ones first.

Vocabularies are kept apart from the specifications that use them. A spec names
an ontology by id and says nothing about where its terms come from, so the same
vocabulary serves many specs, is versioned on its own, and can be extended
without editing a profile — or the ontology snapshot someone else maintains.
Extension is another file: several files may declare the same ontology id, and
they layer, each term remembering which file it came from.

Held deliberately simple: a dict of id to label, from JSON, one entry per term.
A local copy of an ontology is a snapshot, not a service, and pretending
otherwise — inheritance, reasoning, synonym expansion — would be a second
ontology system nobody asked for. What it must do is answer honestly, and say
when it cannot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from metaseed.services.term_check import Materialisation, SourceCapabilities


@dataclass(frozen=True)
class LocalTerm:
    """One term as a local vocabulary holds it.

    Attributes:
        id: The identifier as the file writes it.
        label: Its name.
        source: Which file supplied it. Where vocabularies are layered this is
            the answer to "who added this term", which is the question asked of
            any term that is not in the public snapshot.
    """

    id: str
    label: str = ""
    source: str = ""


@dataclass
class LocalVocabulary:
    """A vocabulary carried as a file rather than fetched.

    Attributes:
        ontology_id: The prefix its terms use, lowercased (e.g. ``co_321``).
        terms: Term id -> label, ids as written in the file.
        source: Where it came from, for the record.
    """

    ontology_id: str
    terms: dict[str, str] = field(default_factory=dict)
    source: str = ""

    def capabilities(self) -> SourceCapabilities:
        """A dictionary in memory: fast to ask, small to hold.

        Declared rather than assumed, because the point of the declaration is
        that a consumer can tell this apart from a remote service that may take
        51 seconds to answer the same question (#247).
        """
        return SourceCapabilities(
            name=self.source or f"local:{self.ontology_id}",
            interactive=True,
            materialisation=Materialisation.CHEAP,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> LocalVocabulary:
        """Load a vocabulary from JSON.

        The file states the ontology it is and lists its terms::

            {
              "ontology": "co_321",
              "terms": {"CO_321:0000123": "plant height", ...}
            }

        Raises:
            ValueError: If the file names no ontology, since a vocabulary that
                cannot say what it is cannot be matched to a field.
        """
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        ontology_id = str(payload.get("ontology", "")).strip().lower()
        if not ontology_id:
            msg = f"{path} does not say which ontology it holds"
            raise ValueError(msg)
        terms = {str(k): str(v) for k, v in (payload.get("terms") or {}).items()}
        return cls(ontology_id=ontology_id, terms=terms, source=str(path))

    def get_term_sync(self, term_id: str) -> LocalTerm | None:
        """The term, or ``None`` when this vocabulary does not list it."""
        label = self.terms.get(term_id)
        return LocalTerm(term_id, label, self.source) if label is not None else None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        """Whether this is that ontology. Never ``None``: a file knows itself."""
        return ontology_id.strip().lower() == self.ontology_id

    def search_sync(
        self, query: str, ontology: str | None = None, limit: int = 20
    ) -> list[LocalTerm]:
        """Terms whose id or label contains ``query``, for a picker.

        Args:
            query: What the person typed. Empty matches everything, so a picker
                can offer the whole vocabulary when it is small.
            ontology: Restrict to this ontology. A vocabulary that is not it
                returns nothing rather than pretending the filter did not apply.
            limit: Most results to return.
        """
        if ontology and not self.has_ontology_sync(ontology):
            return []
        needle = query.lower().strip()
        found = [
            LocalTerm(term_id, label, self.source)
            for term_id, label in self.terms.items()
            if not needle or needle in term_id.lower() or needle in label.lower()
        ]
        return found[:limit]


@dataclass
@dataclass
class VocabularyStore:
    """The vocabularies available to an installation, by ontology id.

    Kept apart from the specifications: a spec names an ontology and nothing
    else, so one vocabulary serves many specs and neither has to know where the
    other lives.

    Several files may declare the same ontology. They layer in the order given,
    later terms winning, which is how a vocabulary is extended: a consortium
    adds its own terms in its own file beside the public snapshot, and neither
    file has to be edited to accommodate the other.
    """

    vocabularies: dict[str, LocalVocabulary] = field(default_factory=dict)
    #: Term id -> the file that supplied the label in force, so an extension
    #: can be traced back to whoever added it.
    provenance: dict[str, str] = field(default_factory=dict)

    def capabilities(self) -> SourceCapabilities:
        """As cheap and as fast as the files it loaded."""
        return SourceCapabilities(
            name="local vocabularies",
            interactive=True,
            materialisation=Materialisation.CHEAP,
        )

    @classmethod
    def from_directory(cls, directory: str | Path) -> VocabularyStore:
        """Load every ``*.json`` vocabulary in ``directory``, layering by id.

        Files are read in sorted order so the outcome does not depend on the
        filesystem; a file named ``co_321.20-local.json`` therefore extends
        ``co_321.10-snapshot.json`` predictably.
        """
        store = cls()
        directory = Path(directory)
        if not directory.is_dir():
            return store
        for path in sorted(directory.glob("*.json")):
            try:
                store.add(LocalVocabulary.from_file(path))
            except (ValueError, OSError) as exc:
                # Name the file: the raw JSONDecodeError surfaced on the
                # first term lookup with a traceback pointing nowhere near
                # the configuration mistake that caused it.
                raise ValueError(
                    f"Vocabulary file {path} could not be loaded: {exc}"
                ) from exc
        return store

    def add(self, vocabulary: LocalVocabulary) -> None:
        """Layer ``vocabulary`` onto whatever is already held for its ontology."""
        existing = self.vocabularies.get(vocabulary.ontology_id)
        if existing is None:
            self.vocabularies[vocabulary.ontology_id] = LocalVocabulary(
                ontology_id=vocabulary.ontology_id,
                terms=dict(vocabulary.terms),
                source=vocabulary.source,
            )
        else:
            existing.terms.update(vocabulary.terms)
            existing.source = f"{existing.source}, {vocabulary.source}".strip(", ")

        for term_id in vocabulary.terms:
            self.provenance[term_id] = vocabulary.source

    def source_of(self, term_id: str) -> str | None:
        """Which file supplied the term in force, if any."""
        return self.provenance.get(term_id)

    def get_term_sync(self, term_id: str) -> LocalTerm | None:
        """The term from whichever vocabulary holds it, naming its file.

        The store answers rather than its vocabularies individually, because
        after layering only the store still knows which of several files
        supplied a given term.
        """
        for vocabulary in self.vocabularies.values():
            term = vocabulary.get_term_sync(term_id)
            if term is not None:
                return LocalTerm(term.id, term.label, self.source_of(term_id) or "")
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        """Whether any vocabulary here is that ontology."""
        return ontology_id.strip().lower() in self.vocabularies

    def search_sync(
        self, query: str, ontology: str | None = None, limit: int = 20
    ) -> list[LocalTerm]:
        """Matching terms across every vocabulary held, nearest first."""
        hits: list[LocalTerm] = []
        for vocabulary in self.vocabularies.values():
            for term in vocabulary.search_sync(query, ontology, limit):
                hits.append(
                    LocalTerm(term.id, term.label, self.source_of(term.id) or "")
                )
                if len(hits) >= limit:
                    return hits
        return hits
