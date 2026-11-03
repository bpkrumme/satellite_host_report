#!/usr/bin/env python3
"""Query Satellite hosts API and emit CSV matching Custom - Hosts report template."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("This script requires the 'requests' package: pip install requests", file=sys.stderr)
    sys.exit(1)

HEADERS = [
    "Name",
    "Type",
    "Sockets",
    "Cores",
    "OS",
    "OS Version",
    "Hypervisor",
    "Registered Date/Time",
    "Organization",
    "Location",
    "Capsule",
]


class SatelliteClient:
    def __init__(self, base_url: str, user: str, password: str, verify: bool) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.auth = (user, password)
        self.session.headers.update({"Accept": "application/json"})
        self.session.verify = verify

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        response = self.session.get(url, params=params, timeout=120)
        response.raise_for_status()
        return response.json()

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        results: list[dict[str, Any]] = []

        while True:
            params["page"] = page
            payload = self.get(path, params=params)
            batch = payload.get("results") or []
            results.extend(batch)
            total = int(payload.get("total") or 0)
            if not batch or len(results) >= total:
                break
            page += 1

        return results


def format_registered_at(value: Any) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def os_version(major: Any, minor: Any) -> str:
    major_s = "" if major is None else str(major).strip()
    minor_s = "" if minor is None else str(minor).strip()
    if not major_s:
        return ""
    if not minor_s:
        return major_s
    return f"{major_s}.{minor_s}"


def host_type(virtual: Any) -> str:
    return "virtual" if virtual else "physical"


def build_os_map(client: SatelliteClient) -> dict[int, tuple[str, str]]:
    operating_systems = client.paginate("/api/operatingsystems")
    mapping: dict[int, tuple[str, str]] = {}
    for item in operating_systems:
        os_id = item.get("id")
        if os_id is None:
            continue
        mapping[int(os_id)] = (
            item.get("name") or "",
            os_version(item.get("major"), item.get("minor")),
        )
    return mapping


def row_from_host(host: dict[str, Any], os_map: dict[int, tuple[str, str]]) -> dict[str, Any]:
    reported = host.get("reported_data") or {}
    subscription = host.get("subscription_facet_attributes") or {}
    content = host.get("content_facet_attributes") or {}
    virtual_host = subscription.get("virtual_host") or {}

    os_id = host.get("operatingsystem_id")
    os_name = ""
    version = ""
    if os_id is not None and int(os_id) in os_map:
        os_name, version = os_map[int(os_id)]
    elif host.get("operatingsystem_name"):
        os_name = host["operatingsystem_name"]

    return {
        "Name": host.get("name") or "",
        "Type": host_type(reported.get("virtual")),
        "Sockets": reported.get("sockets") if reported.get("sockets") is not None else "",
        "Cores": reported.get("cores") if reported.get("cores") is not None else "",
        "OS": os_name,
        "OS Version": version,
        "Hypervisor": virtual_host.get("name") or "",
        "Registered Date/Time": format_registered_at(subscription.get("registered_at")),
        "Organization": host.get("organization_name") or "",
        "Location": host.get("location_name") or "",
        "Capsule": content.get("content_source_name") or "",
    }


def fetch_host_details(
    client: SatelliteClient,
    host_ids: list[int],
    workers: int,
) -> dict[int, dict[str, Any]]:
    details: dict[int, dict[str, Any]] = {}

    def fetch_one(host_id: int) -> tuple[int, dict[str, Any]]:
        return host_id, client.get(f"/api/hosts/{host_id}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one, host_id) for host_id in host_ids]
        for future in as_completed(futures):
            host_id, payload = future.result()
            details[host_id] = payload

    return details


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Custom - Hosts style CSV from the Satellite hosts API.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SATELLITE_URL", ""),
        help="Satellite base URL (or SATELLITE_URL).",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("SATELLITE_USER", ""),
        help="API username (or SATELLITE_USER).",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SATELLITE_PASSWORD", ""),
        help="API password (or SATELLITE_PASSWORD).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output CSV path, or '-' for stdout (default).",
    )
    parser.add_argument(
        "--search",
        default="",
        help="Optional Foreman search query passed to /api/hosts.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel host show requests (default: 8).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.url or not args.user or not args.password:
        print(
            "Provide --url/--user/--password or SATELLITE_URL/SATELLITE_USER/SATELLITE_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    client = SatelliteClient(args.url, args.user, args.password, verify=not args.insecure)

    list_params: dict[str, Any] = {}
    if args.search:
        list_params["search"] = args.search

    hosts = client.paginate("/api/hosts", params=list_params)
    os_map = build_os_map(client)
    host_ids = [int(host["id"]) for host in hosts if host.get("id") is not None]
    details = fetch_host_details(client, host_ids, workers=max(1, args.workers))

    rows = []
    for host in hosts:
        host_id = host.get("id")
        detail = details.get(int(host_id), host) if host_id is not None else host
        rows.append(row_from_host(detail, os_map))

    rows.sort(key=lambda row: row["Name"])

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    try:
        writer = csv.DictWriter(out, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if out is not sys.stdout:
            out.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        print(f"API error: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        raise SystemExit(1)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
