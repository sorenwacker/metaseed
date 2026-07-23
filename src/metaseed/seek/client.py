"""HTTP client for the FAIRDOM-SEEK JSON:API.

Creates ISA content (Investigations, Studies, Assays) and Samples in a SEEK
instance. Requires ``httpx`` (the ``metaseed[seek]`` extra). An ``httpx.Client``
can be injected for hermetic testing.

Auth is HTTP Basic (``auth=(login, password)``) or an API token
(``token=...``); pass exactly one. The pure JSON:API bodies come from
:mod:`metaseed.seek.payloads`; this client posts them and threads the returned
ids so the hierarchy links up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import httpx
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "SEEK support requires httpx. Install with: pip install 'metaseed[seek]'"
    ) from exc

from metaseed.seek import payloads

if TYPE_CHECKING:
    from collections.abc import Mapping

JSONAPI_MEDIA_TYPE = "application/vnd.api+json"
USER_AGENT = "metaseed (+https://github.com/sorenwacker/metaseed)"


def _relates_to_project(row: Mapping[str, Any], project_id: str) -> bool:
    """Whether a JSON:API resource row links to ``project_id`` via ``projects``."""
    projects = row.get("relationships", {}).get("projects", {}).get("data", [])
    return any(str(p.get("id")) == str(project_id) for p in projects)


def client_from_settings(
    config: Mapping[str, str],
    *,
    timeout: float = 30.0,
    http_client: httpx.Client | None = None,
) -> SeekClient:
    """Build a :class:`SeekClient` from a stored adapter config.

    ``config`` is the ``get_adapter_config("seek")`` dict: ``url`` (required) and
    an optional ``api_key`` used as a bearer token. A blank ``api_key`` yields an
    unauthenticated client (callers should warn); a blank ``url`` is an error.
    ``timeout`` bounds each request (use a small value for a liveness probe).
    """
    url = (config.get("url") or "").strip()
    if not url:
        raise ValueError("SEEK URL is not configured (set it on the Plugins page)")
    token = (config.get("api_key") or "").strip() or None
    return SeekClient(url, token=token, timeout=timeout, http_client=http_client)


class SeekClient:
    """Minimal read/write client for the SEEK JSON:API."""

    def __init__(
        self,
        base_url: str,
        *,
        auth: tuple[str, str] | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: SEEK root URL, e.g. ``http://localhost:3001``.
            auth: ``(login, password)`` for HTTP Basic auth.
            token: API token for bearer auth (alternative to ``auth``).
            timeout: Per-request timeout in seconds (ignored when
                ``http_client`` is provided).
            http_client: Optional pre-configured ``httpx.Client`` (e.g. a mock
                transport for tests).
        """
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._token = token
        self._timeout = timeout
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": JSONAPI_MEDIA_TYPE,
            "Content-Type": JSONAPI_MEDIA_TYPE,
            "User-Agent": USER_AGENT,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self, method: str, path: str, *, json: Mapping[str, Any] | None = None
    ) -> Any:
        """Issue a request and return the parsed JSON body (``{}`` if empty)."""
        url = f"{self._base_url}{path}"
        headers = self._headers()
        if self._http_client is not None:
            response = self._http_client.request(
                method, url, headers=headers, json=json, auth=self._auth
            )
        else:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(
                    method, url, headers=headers, json=json, auth=self._auth
                )
        response.raise_for_status()
        return response.json() if response.content else {}

    def get(self, path: str) -> Any:
        """GET ``path`` and return the parsed JSON body."""
        return self._request("GET", path)

    def _create(self, path: str, document: Mapping[str, Any]) -> str:
        """POST a JSON:API document and return the created resource id."""
        body = self._request("POST", path, json=document)
        return str(body["data"]["id"])

    # -- resource creation -------------------------------------------------

    def default_project_id(self) -> str:
        """Return the id of the first project on the instance."""
        projects = self.get("/projects").get("data", [])
        if not projects:
            raise ValueError("SEEK instance has no projects to attach content to")
        return str(projects[0]["id"])

    def list_projects(self) -> list[tuple[str, str]]:
        """Return ``(id, title)`` for every project (for a UI selector)."""
        return [
            (str(row["id"]), str(row["attributes"].get("title", row["id"])))
            for row in self.get("/projects").get("data", [])
        ]

    def sample_attribute_type_id(self, title: str) -> str:
        """Resolve a base sample-attribute-type id by its title (e.g. 'String').

        Ids are instance-assigned, so look them up rather than hard-coding.
        """
        for row in self.get("/sample_attribute_types").get("data", []):
            if row["attributes"].get("title") == title:
                return str(row["id"])
        raise ValueError(f"no sample attribute type titled {title!r}")

    def create_investigation(
        self, *, title: str, project_id: str, description: str | None = None
    ) -> str:
        """Create an Investigation under ``project_id``; return its id."""
        return self._create(
            "/investigations",
            payloads.investigation_payload(
                title=title, project_id=project_id, description=description
            ),
        )

    def create_study(
        self, *, title: str, investigation_id: str, description: str | None = None
    ) -> str:
        """Create a Study under ``investigation_id``; return its id."""
        return self._create(
            "/studies",
            payloads.study_payload(
                title=title,
                investigation_id=investigation_id,
                description=description,
            ),
        )

    def create_assay(
        self,
        *,
        title: str,
        study_id: str,
        assay_class_key: str = "EXP",
        assay_type_uri: str = payloads.DEFAULT_ASSAY_TYPE_URI,
    ) -> str:
        """Create an Assay under ``study_id``; return its id."""
        return self._create(
            "/assays",
            payloads.assay_payload(
                title=title,
                study_id=study_id,
                assay_class_key=assay_class_key,
                assay_type_uri=assay_type_uri,
            ),
        )

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str:
        """Create a Sample Type under ``project_id``; return its id."""
        return self._create(
            "/sample_types",
            payloads.sample_type_payload(
                title=title, project_id=project_id, attributes=attributes
            ),
        )

    def add_missing_sample_type_attributes(
        self, sample_type_id: str, attributes: list[dict[str, Any]]
    ) -> list[str]:
        """Append any ``attributes`` (matched by title) the Sample Type lacks.

        Enables provisioning to add a newly-added profile field as a column on an
        already-provisioned Sample Type. Existing attributes are preserved with
        their ids; a new attribute is added **non-required** (a required column
        would fail validation against the type's pre-existing samples). Returns
        the titles actually added (empty if the type already had them all).
        """
        detail = self.get(f"/sample_types/{sample_type_id}").get("data", {})
        existing = detail.get("attributes", {}).get("sample_attributes", [])
        existing_titles = {a.get("title") for a in existing}
        to_add = [a for a in attributes if a.get("title") not in existing_titles]
        if not to_add:
            return []
        merged = [payloads.preserved_sample_attribute(a) for a in existing]
        added: list[str] = []
        for attr in to_add:
            merged.append({**attr, "required": False})
            added.append(str(attr["title"]))
        self._request(
            "PATCH",
            f"/sample_types/{sample_type_id}",
            json=payloads.sample_type_update_payload(
                sample_type_id=sample_type_id, attributes=merged
            ),
        )
        return added

    def create_sample(
        self, *, sample_type_id: str, project_id: str, data: dict[str, Any]
    ) -> str:
        """Create a Sample of ``sample_type_id``; return its id."""
        return self._create(
            "/samples",
            payloads.sample_payload(
                sample_type_id=sample_type_id, project_id=project_id, data=data
            ),
        )

    def create_controlled_vocab(
        self,
        *,
        title: str,
        terms: list[dict[str, Any]],
        description: str | None = None,
        source_ontology: str | None = None,
        ols_root_term_uris: str | None = None,
    ) -> str:
        """Create a Controlled Vocabulary (with its terms); return its id."""
        return self._create(
            "/sample_controlled_vocabs",
            payloads.controlled_vocab_payload(
                title=title,
                terms=terms,
                description=description,
                source_ontology=source_ontology,
                ols_root_term_uris=ols_root_term_uris,
            ),
        )

    # -- idempotency lookups ----------------------------------------------

    def find_sample_type_id_by_title(
        self, title: str, *, project_id: str | None = None
    ) -> str | None:
        """Return an existing Sample Type id matching ``title`` (else ``None``).

        When ``project_id`` is given, only a sample type attached to that project
        matches — titles are unique per project, not globally. SEEK's
        ``/sample_types`` *list* omits the ``projects`` relationship (it is only on
        the single-resource view), so a title match is confirmed against the
        resource detail when the list row can't prove the project.
        """
        for row in self.get("/sample_types").get("data", []):
            if row["attributes"].get("title") != title:
                continue
            if project_id is None or _relates_to_project(row, project_id):
                return str(row["id"])
            detail = self.get(f"/sample_types/{row['id']}").get("data", {})
            if _relates_to_project(detail, project_id):
                return str(row["id"])
        return None

    def find_controlled_vocab_id_by_title(self, title: str) -> str | None:
        """Return an existing Controlled Vocabulary id matching ``title``.

        Controlled Vocabularies are instance-global in SEEK (not per-project), so
        this matches on title alone.
        """
        for row in self.get("/sample_controlled_vocabs").get("data", []):
            if row["attributes"].get("title") == title:
                return str(row["id"])
        return None
