"""Record a BrAPI v2 fixture from the reference test server, de-identified.

Records the exact (endpoint, params) -> response pairs the importer asks for,
so the fixture reproduces what a real server does rather than what we assume it
does. Person-shaped values are replaced on the way in; technical identifiers and
accessions are kept, since the mapper depends on them and they are not personal
data.
"""

import json
import re
from pathlib import Path

import httpx

BASE = "https://test-server.brapi.org/brapi/v2"
OUT = Path("tests/test_brapi/fixtures/brapi_v2_recorded.json")
PAGE = 10

_PEOPLE = ["Robin Alvarez", "Sam Okafor", "Kit Nakamura", "Lee Fontaine"]
_INSTITUTES = ["Fictional Crop Institute", "Example Plant Research Centre"]
_ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
_counter = {"n": 0}


def deidentify(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in {
                "name",
                "contactname",
                "personname",
                "collector",
                "uploadedby",
            } and (isinstance(item, str)):
                _counter["n"] += 1
                out[key] = _PEOPLE[_counter["n"] % len(_PEOPLE)]
            elif lowered == "email" and isinstance(item, str):
                out[key] = f"contact{_counter['n']}@example.org"
            elif lowered == "orcid" and isinstance(item, str):
                out[key] = "0000-0000-0000-0000"
            elif "institute" in lowered and isinstance(item, str):
                out[key] = _INSTITUTES[_counter["n"] % len(_INSTITUTES)]
            else:
                out[key] = deidentify(item)
        return out
    if isinstance(value, list):
        return [deidentify(v) for v in value]
    if isinstance(value, str):
        value = _ORCID.sub("0000-0000-0000-0000", value)
        return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "contact@example.org", value)
    return value


records: list[dict] = []


def record(client: httpx.Client, endpoint: str, params: dict) -> dict:
    query = {"pageSize": PAGE, **params}
    response = client.get(f"{BASE}/{endpoint}", params=query)
    response.raise_for_status()
    body = deidentify(response.json())
    records.append({"endpoint": endpoint, "params": params, "response": body})
    return body


with httpx.Client(timeout=30) as client:
    studies = record(client, "studies", {})
    study_ids = [
        s["studyDbId"] for s in studies["result"]["data"] if s.get("studyDbId")
    ]

    for study_id in study_ids:
        units = record(client, "observationunits", {"studyDbId": study_id})
        # The query the importer makes today. The reference server answers it
        # with zero rows even though its observations carry that studyDbId.
        record(client, "observations", {"studyDbId": study_id})
        for unit in units["result"]["data"]:
            unit_id = unit.get("observationUnitDbId")
            if unit_id:
                record(client, "observations", {"observationUnitDbId": unit_id})

    record(client, "germplasm", {})

OUT.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")

blob = json.dumps(records)
assert "@brapi.org" not in blob, "an email survived de-identification"
for name in ("Dave Breeder", "Bob "):
    assert name not in blob, f"{name!r} survived de-identification"

print("wrote", OUT, f"({len(records)} recorded requests)")
for r in records:
    total = r["response"]["metadata"]["pagination"]["totalCount"]
    print(f"  {r['endpoint']:18} {r['params']!s:45} totalCount={total}")
print("de-identification checks passed")
