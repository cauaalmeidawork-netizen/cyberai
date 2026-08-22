"""Minimal deployment smoke tests.

Usage:
    python scripts/smoke.py --base-url https://api.example.com
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class SmokeResponse:
    status: int
    body: bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Nomercy AI deployment smoke tests.")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. https://api.example.com")
    parser.add_argument("--skip-metrics", action="store_true", help="Do not check /metrics")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    checks = [
        ("liveness", lambda: expect_status(base_url, "/health/live", 200)),
        ("readiness", lambda: expect_status(base_url, "/health/ready", 200)),
        ("auth failure", lambda: expect_status(base_url, "/api/v1/projects", 401)),
        ("metadata", lambda: expect_json_field(base_url, "/api/v1/meta", "version")),
    ]
    if not args.skip_metrics:
        checks.append(("metrics", lambda: expect_status(base_url, "/metrics", 200)))

    failures: list[str] = []
    for name, check in checks:
        try:
            check()
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("OK smoke checks passed")
    return 0


def expect_status(base_url: str, path: str, status: int) -> SmokeResponse:
    response = request(base_url, path)
    if response.status != status:
        raise RuntimeError(f"{path} returned {response.status}, expected {status}")
    return response


def expect_json_field(base_url: str, path: str, field: str) -> None:
    response = expect_status(base_url, path, 200)
    data = json.loads(response.body.decode("utf-8"))
    if not isinstance(data, dict) or field not in data:
        raise RuntimeError(f"{path} did not include JSON field {field}")


def request(base_url: str, path: str) -> SmokeResponse:
    req = Request(f"{base_url}{path}", headers={"accept": "application/json"})
    try:
        with urlopen(req, timeout=10) as response:
            return SmokeResponse(status=response.status, body=response.read())
    except HTTPError as exc:
        return SmokeResponse(status=exc.code, body=exc.read())
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
