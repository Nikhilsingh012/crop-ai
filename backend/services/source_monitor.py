"""Manual reachability and change checks for an explicit official-source allowlist."""
from hashlib import sha256
import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from psycopg.types.json import Jsonb

from db import connection

SOURCES = {
    "pm-kisan": ("https://pmkisan.gov.in/", {"pmkisan.gov.in"}),
    "pmfby": ("https://www.pmfby.gov.in/policy", {"www.pmfby.gov.in", "pmfby.gov.in"}),
    "pm-kusum": ("https://pmkusum.mnre.gov.in/", {"pmkusum.mnre.gov.in"}),
    "aif": ("https://agriinfra.dac.gov.in/", {"agriinfra.dac.gov.in"}),
    "enam": ("https://enam.gov.in/", {"enam.gov.in", "www.enam.gov.in"}),
}


def _fetch(key):
    url, hosts = SOURCES[key]
    request = Request(url, headers={"User-Agent": "KhetiLens-source-check/1.0", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=8) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in hosts:
                raise ValueError("redirect_outside_source_allowlist")
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("response_too_large")
            return {"result": "ok", "http_status": response.status, "sha256": sha256(body).hexdigest(), "bytes": len(body), "url": url}
    except Exception as error:
        return {"result": "failed", "http_status": None, "error_code": type(error).__name__, "url": url}


def check_official_sources(source_keys=None):
    keys = list(dict.fromkeys(source_keys or SOURCES.keys()))
    if any(key not in SOURCES for key in keys):
        raise ValueError("One or more source keys are not on the official-source allowlist.")
    fetched = {key: _fetch(key) for key in keys}
    output = []
    with connection() as conn:
        for key, result in fetched.items():
            row = conn.execute("SELECT id,last_content_sha256 FROM source_registry WHERE source_key=%s", (key,)).fetchone()
            if row is None:
                output.append({"source_key": key, "result": "skipped", "reason": "source_not_registered"})
                continue
            if result["result"] == "failed":
                status = "failed"
            elif row["last_content_sha256"] is None:
                status = "skipped"  # First fetch establishes a baseline; a human reviews content.
            else:
                status = "no_update" if row["last_content_sha256"] == result["sha256"] else "update_found"
            details = {k: v for k, v in result.items() if k not in {"result", "error_code"}}
            if result.get("error_code"):
                details["error_code"] = result["error_code"]
            conn.execute("INSERT INTO source_runs(source_id,source_key,finished_at,result,error_code,records_seen,details) VALUES(%s,%s,NOW(),%s,%s,0,%s)", (row["id"], key, status, result.get("error_code"), Jsonb(details)))
            if result["result"] == "ok":
                conn.execute("UPDATE source_registry SET last_content_sha256=%s,last_http_status=%s,last_seen_at=NOW(),updated_at=NOW() WHERE id=%s", (result["sha256"], result["http_status"], row["id"]))
            output.append({"source_key": key, "result": status, "http_status": result.get("http_status"), "human_review_required": status == "update_found", "source_url": result["url"]})
    return output


if __name__ == "__main__":
    print(json.dumps(check_official_sources(), indent=2))
