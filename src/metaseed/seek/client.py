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
    from collections.abc import Mapping, Sequence

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


class SeekApiError(RuntimeError):
    """A SEEK request was rejected, carrying what SEEK said was wrong.

    SEEK answers a rejected write with a JSON:API ``errors`` array naming the
    offending attribute. Without it the caller only sees the status code, which
    says a request failed but not which field SEEK refused or why -- leaving no
    way to act on it.
    """

    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self.detail = _error_detail(response)
        super().__init__(
            f"SEEK rejected {response.request.method} {response.request.url.path} "
            f"({response.status_code}): {self.detail}"
        )


def _error_detail(response: httpx.Response) -> str:
    """Summarise SEEK's error body, falling back to the raw text.

    Args:
        response: The rejected response.

    Returns:
        A single line naming each reported problem, or the body when it is not
        the JSON:API shape.
    """
    try:
        body = response.json()
    except ValueError:
        return (response.text or "no response body").strip()[:500]

    errors = body.get("errors") if isinstance(body, dict) else None
    if not errors:
        return str(body)[:500]

    parts = []
    for err in errors:
        if not isinstance(err, dict):
            parts.append(str(err))
            continue
        where = (err.get("source") or {}).get("pointer") or err.get("title") or ""
        what = err.get("detail") or err.get("title") or ""
        parts.append(f"{where}: {what}".strip(": ") if where else str(what))
    return "; ".join(p for p in parts if p)[:500]


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

    def _send(
        self, method: str, path: str, *, headers: Mapping[str, str], **kwargs: Any
    ) -> httpx.Response:
        """Issue one HTTP request, using the injected client or a short-lived one.

        The two encodings this client speaks -- JSON:API and the form bodies the
        ISA endpoints require -- differ only in headers and body, so the auth and
        client-lifetime handling lives here rather than being duplicated per
        encoding.
        """
        url = f"{self._base_url}{path}"
        if self._http_client is not None:
            return self._http_client.request(
                method, url, headers=headers, auth=self._auth, **kwargs
            )
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(
                method, url, headers=headers, auth=self._auth, **kwargs
            )

    def _request(
        self, method: str, path: str, *, json: Mapping[str, Any] | None = None
    ) -> Any:
        """Issue a request and return the parsed JSON body (``{}`` if empty)."""
        response = self._send(method, path, headers=self._headers(), json=json)
        if response.is_error:
            # SEEK answers a rejected write with a JSON:API ``errors`` array
            # naming the offending attribute. Raising the bare status turned
            # every failure into an unactionable "422 Unprocessable Content".
            raise SeekApiError(response) from None
        return response.json() if response.content else {}

    def get(self, path: str) -> Any:
        """GET ``path`` and return the parsed JSON body."""
        return self._request("GET", path)

    def _form_request(self, path: str, pairs: Sequence[tuple[str, str]]) -> str:
        """POST form-encoded ``pairs`` to an ISA endpoint; return the new record id.

        ``/isa_studies`` and ``/isa_assays`` back SEEK's web forms. Their JSON
        branch is unreachable -- ``check_json_id_type`` demands a JSON:API
        ``data`` member and ``convert_json_params`` then drops the ``isa_*`` key
        -- so the body must be form-encoded and the request must not ask for
        JSON. Success is a 302 whose ``Location`` carries ``item_id``; a
        rejection renders the form again as HTML, which is raised rather than
        returned so a caller cannot attach samples to an assay that was never
        created.
        """
        headers = {
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        body = "&".join(str(httpx.QueryParams({key: value})) for key, value in pairs)
        response = self._send(
            "POST", path, headers=headers, content=body, follow_redirects=False
        )
        if response.status_code not in (301, 302, 303):
            raise SeekApiError(response) from None
        item_id = httpx.URL(response.headers.get("Location", "")).params.get("item_id")
        if not item_id:
            raise ValueError(f"SEEK accepted POST {path} but returned no item_id")
        return str(item_id)

    def isa_tag_ids(self) -> dict[str, str]:
        """ISA tag title -> id, as an ISA-compliant Sample Type attribute needs.

        Attributes take ``isa_tag_id``, but the numeric ids are per-instance, so
        they are resolved by title against the instance being written to.
        """
        return {
            row["attributes"]["title"]: str(row["id"])
            for row in self.get("/isa_tags").get("data", [])
        }

    def template_ids_by_title(self) -> dict[str, str]:
        """ISA Template title -> id, for attaching a Template to a Sample Type.

        SEEK's ISA-JSON exporter reads a Sample Type's Template to tell an assay
        data file from an assay material, so a Sample Type without one cannot be
        exported however correct its attributes are.
        """
        return {
            row["attributes"]["title"]: str(row["id"])
            for row in self.get("/templates").get("data", [])
            if (row.get("attributes") or {}).get("title")
        }

    def create_isa_study(
        self,
        *,
        title: str,
        investigation_id: str,
        source_title: str,
        source_attributes: Sequence[Mapping[str, Any]],
        collection_title: str,
        collection_attributes: Sequence[Mapping[str, Any]],
        source_template_id: str | None = None,
        collection_template_id: str | None = None,
        sharing: str | None = None,
    ) -> str:
        """Create a Study with its Source and Sample Collection types; return its id.

        A Study is ISA-JSON compliant only once it owns these two Sample Types,
        so they are created with it rather than attached afterwards -- the
        JSON:API cannot attach them at all, since ``study_ids`` is not permitted
        on ``POST /sample_types``.
        """
        return self._form_request(
            "/isa_studies",
            payloads.isa_study_form(
                title=title,
                investigation_id=investigation_id,
                source_title=source_title,
                source_attributes=source_attributes,
                collection_title=collection_title,
                collection_attributes=collection_attributes,
                source_template_id=source_template_id,
                collection_template_id=collection_template_id,
                sharing=sharing,
            ),
        )

    def study_sample_type_ids(self, study_id: str) -> dict[str, str]:
        """A Study's Sample Types as title -> id.

        Keyed by title rather than position: ``GET /studies/{id}/sample_types``
        does not preserve ``study.sample_types`` order, so the Source type cannot
        be told from the Sample Collection type by where it appears. The caller
        created both and knows the titles it used.
        """
        return {
            row["attributes"]["title"]: str(row["id"])
            for row in self.get(f"/studies/{study_id}/sample_types").get("data", [])
        }

    def assay_sample_type_ids(self, assay_id: str) -> dict[str, str]:
        """An Assay's Sample Types as title -> id.

        Read from the sub-route because the assay resource omits ``sample_types``
        from its ``relationships`` block, which makes the association look absent
        when it is not.
        """
        return {
            row["attributes"]["title"]: str(row["id"])
            for row in self.get(f"/assays/{assay_id}/sample_types").get("data", [])
        }

    def create_isa_assay(
        self,
        *,
        title: str,
        study_id: str,
        assay_class_id: int,
        assay_stream_id: str | None = None,
        input_sample_type_id: str | None = None,
        sample_type_title: str | None = None,
        sample_type_attributes: Sequence[Mapping[str, Any]] | None = None,
        sample_type_template_id: str | None = None,
        sharing: str | None = None,
    ) -> str:
        """Create an assay stream, or an assay within one; return its id.

        ``POST /assays`` cannot do this: ``assay_stream_id`` is absent from its
        permitted params and from the ``assayPost`` schema, so it answers 200 and
        discards the link, leaving an assay that belongs to no stream.
        """
        return self._form_request(
            "/isa_assays",
            payloads.isa_assay_form(
                title=title,
                study_id=study_id,
                assay_class_id=assay_class_id,
                assay_stream_id=assay_stream_id,
                input_sample_type_id=input_sample_type_id,
                sample_type_title=sample_type_title,
                sample_type_attributes=sample_type_attributes,
                sample_type_template_id=sample_type_template_id,
                sharing=sharing,
            ),
        )

    def delete(self, path: str) -> None:
        """DELETE ``path``.

        Every other method here writes or reads; without this, a caller that
        creates resources has no supported way to remove them again, which is
        what a test fixture tearing down its own records needs.
        """
        self._request("DELETE", path)

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
        self,
        *,
        title: str,
        project_id: str,
        description: str | None = None,
        isa_json_compliant: bool = False,
        sharing: str | None = None,
    ) -> str:
        """Create an Investigation under ``project_id``; return its id."""
        return self._create(
            "/investigations",
            payloads.investigation_payload(
                title=title,
                project_id=project_id,
                description=description,
                isa_json_compliant=isa_json_compliant,
                sharing=sharing,
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

    def create_sample(
        self,
        *,
        sample_type_id: str,
        project_id: str,
        data: dict[str, Any],
        assay_ids: Sequence[str] | None = None,
        study_id: str | None = None,
    ) -> str:
        """Create a Sample of ``sample_type_id``; return its id.

        ``assay_ids`` links the Sample into the ISA tree. Omitting it leaves the
        Sample reachable only through the project's sample list.
        """
        return self._create(
            "/samples",
            payloads.sample_payload(
                sample_type_id=sample_type_id,
                project_id=project_id,
                data=data,
                assay_ids=assay_ids,
                study_id=study_id,
            ),
        )

    def create_data_file(
        self,
        *,
        title: str,
        project_id: str,
        url: str,
        original_filename: str,
        description: str | None = None,
        assay_ids: list[str | int] | None = None,
    ) -> str:
        """Register a remote Data File (external content by URL); return its id."""
        return self._create(
            "/data_files",
            payloads.data_file_payload(
                title=title,
                project_id=project_id,
                url=url,
                original_filename=original_filename,
                description=description,
                assay_ids=assay_ids,
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

    def find_investigation_id_by_title(
        self, title: str, *, project_id: str
    ) -> str | None:
        """An existing Investigation with ``title`` in ``project_id``, if any.

        Pushing the same dataset twice created a second copy of everything,
        because nothing looked for what the first push had made. Titles are how
        SEEK's own interface distinguishes these records, and the same rule the
        Sample Type lookup already used.
        """
        for row in self.get("/investigations").get("data", []):
            if row["attributes"].get("title") == title and _relates_to_project(
                row, project_id
            ):
                return str(row["id"])
        return None

    def find_study_id_by_title(
        self, title: str, *, investigation_id: str
    ) -> str | None:
        """An existing Study with ``title`` under ``investigation_id``, if any."""
        return self._find_child("/studies", title, "investigation", investigation_id)

    def find_assay_id_by_title(self, title: str, *, study_id: str) -> str | None:
        """An existing Assay with ``title`` under ``study_id``, if any."""
        return self._find_child("/assays", title, "study", study_id)

    def _find_child(
        self, path: str, title: str, relation: str, parent_id: str
    ) -> str | None:
        """The id of a record at ``path`` titled ``title`` under ``parent_id``.

        The list view carries the parent relationship for studies and assays; a
        row whose relationship is absent is confirmed against its detail rather
        than assumed to match, so a same-titled record in another investigation
        is never reused.
        """
        for row in self.get(path).get("data", []):
            if row["attributes"].get("title") != title:
                continue
            related = ((row.get("relationships") or {}).get(relation) or {}).get("data")
            if related is None:
                detail = self.get(f"{path}/{row['id']}").get("data", {})
                related = ((detail.get("relationships") or {}).get(relation) or {}).get(
                    "data"
                )
            if related and str(related.get("id")) == str(parent_id):
                return str(row["id"])
        return None

    def find_sample_id_by_title(self, title: str, *, sample_type_id: str) -> str | None:
        """An existing Sample with ``title`` of ``sample_type_id``, if any."""
        for row in self.get(f"/sample_types/{sample_type_id}/samples").get("data", []):
            attributes = row.get("attributes") or {}
            if attributes.get("title") == title:
                return str(row["id"])
            values = attributes.get("attribute_map") or {}
            if values.get("Title") == title:
                return str(row["id"])
        return None

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
