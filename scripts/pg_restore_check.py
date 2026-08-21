"""Validate a PostgreSQL backup by restoring it into a disposable database."""

from __future__ import annotations

import argparse
import subprocess
from urllib.parse import urlsplit, urlunsplit


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a backup into a disposable database.")
    parser.add_argument("--admin-url", required=True, help="PostgreSQL admin connection URL.")
    parser.add_argument("--backup", required=True, help="Backup file produced by pg_backup.py.")
    parser.add_argument("--database", required=True, help="Disposable restore database name.")
    args = parser.parse_args()

    restore_url = _replace_database(args.admin_url, args.database)
    subprocess.run(["createdb", args.admin_url, args.database], check=True)
    try:
        subprocess.run(["pg_restore", "--no-owner", "--dbname", restore_url, args.backup], check=True)
        subprocess.run(["psql", restore_url, "-c", "SELECT 1;"], check=True)
    finally:
        subprocess.run(["dropdb", "--if-exists", args.admin_url, args.database], check=False)
    return 0


def _replace_database(url: str, database: str) -> str:
    parsed = urlsplit(url)
    path = f"/{database}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


if __name__ == "__main__":
    raise SystemExit(main())
