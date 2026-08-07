"""Command-line interface for read-only App Store Connect reports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from .auth import AuthError, load_config
from .client import ApiError, AppStoreConnectClient, encode_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asc",
        description="Read-only App Store Connect apps, sales, finance, and analytics reports.",
    )
    parser.add_argument("--issuer-id", help="App Store Connect issuer ID (or ASC_ISSUER_ID).")
    parser.add_argument("--key-id", help="App Store Connect key ID (or ASC_KEY_ID).")
    parser.add_argument("--private-key", help="Path to the .p8 key (or ASC_PRIVATE_KEY).")
    parser.add_argument("--vendor-number", help="Vendor number (or ASC_VENDOR_NUMBER).")
    parser.add_argument("--format", choices=("table", "json", "csv", "tsv"), default="table")
    parser.add_argument("--output", help="Write report data to this file instead of stdout.")

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apps", help="List apps visible to the API key.")

    sales = commands.add_parser("sales", help="Download a Sales and Trends report.")
    sales.add_argument("--report-type", default="SALES")
    sales.add_argument("--report-subtype", default="SUMMARY")
    sales.add_argument("--frequency", choices=("DAILY", "WEEKLY", "MONTHLY", "YEARLY"), default="DAILY")
    sales.add_argument("--report-date", help="YYYY-MM-DD for non-daily reports.")
    sales.add_argument("--version", default="1_0")

    finance = commands.add_parser("finance", help="Download a monthly Finance report.")
    finance.add_argument("--region-code", required=True, help="Apple financial report region, for example WW.")
    finance.add_argument("--report-date", required=True, help="Apple fiscal month in YYYY-MM format.")
    finance.add_argument("--report-type", choices=("FINANCIAL", "FINANCE_DETAIL"), default="FINANCIAL")

    requests = commands.add_parser("analytics-requests", help="List analytics report requests for an app.")
    requests.add_argument("--app-id", required=True)

    reports = commands.add_parser("analytics-reports", help="List reports generated for an analytics request.")
    reports.add_argument("--request-id", required=True)
    reports.add_argument("--category", choices=("APP_USAGE", "APP_STORE_ENGAGEMENT", "COMMERCE", "FRAMEWORK_USAGE", "PERFORMANCE"))

    instances = commands.add_parser("analytics-instances", help="List report instances for an analytics report.")
    instances.add_argument("--report-id", required=True)

    download = commands.add_parser("analytics-download", help="Download and parse all segments for a report instance.")
    download.add_argument("--instance-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(
            issuer_id=args.issuer_id,
            key_id=args.key_id,
            private_key=args.private_key,
            vendor_number=args.vendor_number,
        )
        client = AppStoreConnectClient(config)

        if args.command == "apps":
            value: Any = client.apps()
        elif args.command == "sales":
            vendor = _required_vendor(config, parser)
            _validate_sales_args(args.frequency, args.report_date)
            value = client.sales_report(
                vendor_number=vendor,
                report_type=args.report_type,
                report_subtype=args.report_subtype,
                frequency=args.frequency,
                report_date=args.report_date,
                version=args.version,
            )
        elif args.command == "finance":
            vendor = _required_vendor(config, parser)
            _validate_month(args.report_date)
            value = client.finance_report(
                vendor_number=vendor,
                region_code=args.region_code,
                report_date=args.report_date,
                report_type=args.report_type,
            )
        elif args.command == "analytics-requests":
            value = client.analytics_requests(app_id=args.app_id)
        elif args.command == "analytics-reports":
            value = client.analytics_reports(request_id=args.request_id, category=args.category)
        elif args.command == "analytics-instances":
            value = client.analytics_instances(report_id=args.report_id)
        elif args.command == "analytics-download":
            value = client.analytics_download(instance_id=args.instance_id)
        else:  # pragma: no cover - argparse enforces commands
            parser.error("unknown command")
            return 2

        rendered = render(value, output_format=args.format, command=args.command)
        if args.output:
            Path(args.output).expanduser().write_text(rendered + ("\n" if rendered else ""), encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            print(rendered)
        return 0
    except (AuthError, ApiError, ValueError) as exc:
        print(f"asc: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"asc: unexpected App Store Connect failure: {exc}", file=sys.stderr)
        return 1


def _required_vendor(config: dict[str, str], parser: argparse.ArgumentParser) -> str:
    if not config["vendor_number"]:
        parser.error("--vendor-number is required for sales and finance reports (or set ASC_VENDOR_NUMBER)")
    return config["vendor_number"]


def _validate_sales_args(frequency: str, report_date: str | None) -> None:
    if frequency != "DAILY" and not report_date:
        raise ValueError("--report-date is required for weekly, monthly, and yearly sales reports")
    if report_date:
        _validate_date(report_date)


def _validate_date(value: str) -> None:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid report date {value!r}; use YYYY-MM-DD") from exc


def _validate_month(value: str) -> None:
    try:
        dt.datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"invalid finance report date {value!r}; use YYYY-MM") from exc


def render(value: Any, *, output_format: str, command: str) -> str:
    if output_format == "json":
        return json.dumps(value, indent=2, ensure_ascii=False)
    if output_format in {"csv", "tsv"}:
        rows = value if isinstance(value, list) else [value]
        return encode_rows(rows, output_format)
    if command in {"sales", "finance", "analytics-download"}:
        rows = value if isinstance(value, list) else []
        if not rows:
            return "No report rows returned."
        headers = list(rows[0])
        return "\n".join(["\t".join(headers), *["\t".join(str(row.get(key, "")) for key in headers) for row in rows]])
    if command == "apps" and isinstance(value, list):
        if not value:
            return "No apps returned."
        headers = ["id", "name", "bundleId", "sku"]
        lines = ["\t".join(headers)]
        lines.extend(
            "\t".join(
                str(
                    item.get("id", "")
                    if key == "id"
                    else item.get("attributes", {}).get(key, "")
                )
                for key in headers
            )
            for item in value
        )
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "No results returned."
        return json.dumps(value, indent=2, ensure_ascii=False)
    return json.dumps(value, indent=2, ensure_ascii=False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
