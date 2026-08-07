"""Small read-only HTTP client for App Store Connect reporting endpoints."""

from __future__ import annotations

import csv
import gzip
import io
import json
from typing import Any

import requests

from .auth import create_token

BASE_URL = "https://api.appstoreconnect.apple.com"


class ApiError(RuntimeError):
    """Raised when App Store Connect returns an error response."""


class AppStoreConnectClient:
    def __init__(self, config: dict[str, str], *, timeout: int = 60):
        self._config = config
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(self._config)}"}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=self._headers(),
            params={key: value for key, value in (params or {}).items() if value not in (None, "")},
            timeout=self._timeout,
        )
        return _json_response(response)

    def download_gzip(self, path: str, *, params: dict[str, Any]) -> bytes:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=self._headers(),
            params={key: value for key, value in params.items() if value not in (None, "")},
            timeout=self._timeout,
        )
        if not response.ok:
            raise ApiError(_error_message(response))
        try:
            return gzip.decompress(response.content)
        except OSError as exc:
            raise ApiError(f"Apple returned a report that was not valid gzip data: {exc}") from exc

    def download_url(self, url: str) -> bytes:
        response = requests.get(url, timeout=self._timeout)
        if not response.ok:
            raise ApiError(_error_message(response))
        try:
            return gzip.decompress(response.content)
        except OSError as exc:
            raise ApiError(f"Apple returned an analytics segment that was not valid gzip data: {exc}") from exc

    def apps(self) -> list[dict]:
        return [serialize_resource(item) for item in self.get_json("/v1/apps", params={"limit": 200}).get("data", [])]

    def sales_report(
        self,
        *,
        vendor_number: str,
        report_type: str,
        report_subtype: str,
        frequency: str,
        report_date: str | None,
        version: str | None,
    ) -> list[dict]:
        content = self.download_gzip(
            "/v1/salesReports",
            params={
                "filter[frequency]": frequency,
                "filter[reportDate]": report_date,
                "filter[reportSubType]": report_subtype,
                "filter[reportType]": report_type,
                "filter[vendorNumber]": vendor_number,
                "filter[version]": version,
            },
        )
        return parse_tab_report(content)

    def finance_report(
        self,
        *,
        vendor_number: str,
        region_code: str,
        report_date: str,
        report_type: str,
    ) -> list[dict]:
        content = self.download_gzip(
            "/v1/financeReports",
            params={
                "filter[regionCode]": region_code,
                "filter[reportDate]": report_date,
                "filter[reportType]": report_type,
                "filter[vendorNumber]": vendor_number,
            },
        )
        return parse_tab_report(content)

    def analytics_requests(self, *, app_id: str) -> list[dict]:
        return [
            serialize_resource(item)
            for item in self.get_json(f"/v1/apps/{app_id}/analyticsReportRequests", params={"limit": 200}).get(
                "data", []
            )
        ]

    def analytics_reports(self, *, request_id: str, category: str | None = None) -> list[dict]:
        return [
            serialize_resource(item)
            for item in self.get_json(
                f"/v1/analyticsReportRequests/{request_id}/reports",
                params={"limit": 200, "filter[category]": category},
            ).get("data", [])
        ]

    def analytics_instances(self, *, report_id: str) -> list[dict]:
        return [
            serialize_resource(item)
            for item in self.get_json(f"/v1/analyticsReports/{report_id}/instances", params={"limit": 200}).get(
                "data", []
            )
        ]

    def analytics_segments(self, *, instance_id: str) -> list[dict]:
        return [
            serialize_resource(item)
            for item in self.get_json(
                f"/v1/analyticsReportInstances/{instance_id}/segments", params={"limit": 200}
            ).get("data", [])
        ]

    def analytics_download(self, *, instance_id: str) -> list[dict]:
        rows: list[dict] = []
        for segment in self.analytics_segments(instance_id=instance_id):
            url = segment.get("attributes", {}).get("url")
            if not url:
                raise ApiError(f"Analytics segment {segment.get('id', '<unknown>')} has no download URL")
            rows.extend(parse_tab_report(self.download_url(url)))
        return rows


def _json_response(response: requests.Response) -> dict:
    if not response.ok:
        raise ApiError(_error_message(response))
    try:
        return response.json()
    except ValueError as exc:
        raise ApiError("Apple returned a non-JSON response where JSON was expected") from exc


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        errors = payload.get("errors", [])
        detail = "; ".join(error.get("detail", "") for error in errors if error.get("detail"))
        if detail:
            return f"App Store Connect API {response.status_code}: {detail}"
    except ValueError:
        pass
    return f"App Store Connect API {response.status_code}: {response.text[:500]}"


def serialize_resource(resource: dict) -> dict:
    return {
        "type": resource.get("type"),
        "id": resource.get("id"),
        "attributes": resource.get("attributes", {}),
        "relationships": resource.get("relationships", {}),
    }


def parse_tab_report(content: bytes) -> list[dict]:
    """Parse Apple's gzip-compressed tab-delimited report payload."""

    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    return [dict(row) for row in reader]


def encode_rows(rows: list[dict], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False)
    if output_format == "tsv":
        delimiter = "\t"
    else:
        delimiter = ","
    if not rows:
        return ""
    fields = list(rows[0])
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, delimiter=delimiter, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().rstrip("\n")

