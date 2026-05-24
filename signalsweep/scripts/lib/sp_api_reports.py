"""SP-API Reports async lifecycle helper (signalsweep 3.27.0+).

Handles the request → poll → download flow for SP-API reports (Brand Analytics,
inventory, etc.). The Reports API is async: you POST a report request, poll
until DONE, then GET the download URL.

Auth: reuses `amazon_auth.py` LWA token flow + `sp_api.py` region/profile
resolution and endpoint allowlist.

Endpoints used (all in sp_api.ALLOWED_ENDPOINTS):
  POST /reports/2021-06-30/reports       — create report
  GET  /reports/2021-06-30/reports/{id}   — poll status
  GET  /reports/2021-06-30/documents/{id} — get download URL

Never raises. Returns envelope dicts.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
import time
from typing import Any

from . import amazon_auth, amazon_marketplaces, paid_api

REPORTS_PATH = "/reports/2021-06-30/reports"
DOCUMENTS_PATH = "/reports/2021-06-30/documents"

POLL_INTERVAL_SECONDS = 5
POLL_MAX_ATTEMPTS = 24  # 24 * 5s = 120s max wait
DOWNLOAD_TIMEOUT_SECONDS = 30

TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}


def _resolve_config(config: dict[str, Any]) -> dict[str, Any]:
    from . import sp_api
    return sp_api._resolve_profile(config)


def _get_access_token(config: dict[str, Any]) -> tuple[str | None, str | None]:
    cfg = _resolve_config(config)
    refresh_token = cfg.get("AMAZON_LWA_REFRESH_TOKEN") or ""
    client_id = cfg.get("AMAZON_LWA_CLIENT_ID") or ""
    client_secret = cfg.get("AMAZON_LWA_CLIENT_SECRET") or ""
    if not (refresh_token and client_id and client_secret):
        return None, "credentials_missing"
    token, _ = amazon_auth.get_lwa_access_token(refresh_token, client_id, client_secret)
    if not token:
        return None, amazon_auth.get_last_error() or "lwa_token_failed"
    return token, None


def _region_base(config: dict[str, Any]) -> str:
    from . import sp_api
    return sp_api._region_base(config)


def _marketplace_id(config: dict[str, Any]) -> str:
    from . import sp_api
    return sp_api._marketplace_id(config)


def request_report(
    report_type: str,
    *,
    config: dict[str, Any],
    data_start_time: str | None = None,
    data_end_time: str | None = None,
    report_options: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a report request. Returns envelope with report_id or error."""
    token, err = _get_access_token(config)
    if err:
        return {"report_id": None, "error": err}

    base = _region_base(config)
    marketplace = _marketplace_id(config)

    body: dict[str, Any] = {
        "reportType": report_type,
        "marketplaceIds": [marketplace],
    }
    if data_start_time:
        body["dataStartTime"] = data_start_time
    if data_end_time:
        body["dataEndTime"] = data_end_time
    if report_options:
        body["reportOptions"] = report_options

    result = paid_api.post_json(
        f"{base}{REPORTS_PATH}",
        body,
        extra_headers={
            "x-amz-access-token": token,
            "Content-Type": "application/json",
        },
        user_agent_suffix="(sp-api-reports)",
        timeout=15,
    )

    if result.get("error"):
        return {"report_id": None, "error": result["error"]}

    payload = result.get("items") or {}
    report_id = payload.get("reportId")
    if not report_id:
        return {"report_id": None, "error": "no_report_id_in_response"}
    return {"report_id": report_id, "error": None}


def poll_report(
    report_id: str,
    *,
    config: dict[str, Any],
    max_attempts: int = POLL_MAX_ATTEMPTS,
    interval: int = POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Poll until report reaches a terminal status. Returns envelope with document_id or error."""
    token, err = _get_access_token(config)
    if err:
        return {"document_id": None, "status": None, "error": err}

    base = _region_base(config)
    path = f"{REPORTS_PATH}/{report_id}"

    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(interval)

        result = paid_api.fetch_json(
            f"{base}{path}",
            extra_headers={"x-amz-access-token": token},
            user_agent_suffix="(sp-api-reports-poll)",
            cache_key=None,
            timeout=15,
        )

        if result.get("error"):
            return {"document_id": None, "status": None, "error": result["error"]}

        payload = result.get("items") or {}
        status = payload.get("processingStatus") or ""

        if status == "DONE":
            doc_id = payload.get("reportDocumentId")
            if not doc_id:
                return {"document_id": None, "status": "DONE", "error": "no_document_id"}
            return {"document_id": doc_id, "status": "DONE", "error": None}

        if status in ("CANCELLED", "FATAL"):
            return {"document_id": None, "status": status, "error": f"report_{status.lower()}"}

    return {"document_id": None, "status": "IN_PROGRESS", "error": "poll_timeout"}


def download_report(
    document_id: str,
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Download and parse a report document. Returns envelope with rows (list of dicts) or error."""
    token, err = _get_access_token(config)
    if err:
        return {"rows": None, "error": err}

    base = _region_base(config)
    path = f"{DOCUMENTS_PATH}/{document_id}"

    result = paid_api.fetch_json(
        f"{base}{path}",
        extra_headers={"x-amz-access-token": token},
        user_agent_suffix="(sp-api-reports-doc)",
        cache_key=None,
        timeout=15,
    )

    if result.get("error"):
        return {"rows": None, "error": result["error"]}

    payload = result.get("items") or {}
    download_url = payload.get("url")
    compression = payload.get("compressionAlgorithm") or ""

    if not download_url:
        return {"rows": None, "error": "no_download_url"}

    raw = paid_api._fetch_raw(
        download_url,
        method="GET",
        body=None,
        params=None,
        auth=None,
        cache_key=None,
        cache_ttl_hours=0,
        user_agent_suffix="(sp-api-reports-download)",
        extra_headers=None,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )

    if raw.get("error"):
        return {"rows": None, "error": raw["error"]}

    body_bytes = raw.get("body") or b""
    if compression.upper() == "GZIP":
        try:
            body_bytes = gzip.decompress(body_bytes)
        except Exception as e:
            return {"rows": None, "error": f"gzip_decompress_error: {e}"}

    return _parse_csv_bytes(body_bytes)


def _parse_csv_bytes(data: bytes) -> dict[str, Any]:
    """Parse tab-delimited CSV bytes into list of dicts."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception as e:
            return {"rows": None, "error": f"decode_error: {e}"}

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    rows = []
    for row in reader:
        rows.append(dict(row))
    return {"rows": rows, "error": None}


def fetch_report(
    report_type: str,
    *,
    config: dict[str, Any],
    data_start_time: str | None = None,
    data_end_time: str | None = None,
    report_options: dict[str, str] | None = None,
    max_poll_attempts: int = POLL_MAX_ATTEMPTS,
    poll_interval: int = POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """End-to-end: request → poll → download. Returns {"rows": [...], "error": None|str}."""
    req = request_report(
        report_type,
        config=config,
        data_start_time=data_start_time,
        data_end_time=data_end_time,
        report_options=report_options,
    )
    if req.get("error"):
        return {"rows": None, "error": req["error"]}

    poll = poll_report(
        req["report_id"],
        config=config,
        max_attempts=max_poll_attempts,
        interval=poll_interval,
    )
    if poll.get("error"):
        return {"rows": None, "error": poll["error"]}

    return download_report(poll["document_id"], config=config)
