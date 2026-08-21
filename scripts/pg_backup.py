"""Create a PostgreSQL custom-format backup for CYBER AI.

The script shells out to `pg_dump` so pgvector data and schema objects are
captured by PostgreSQL's native tooling. Credentials are supplied by the
DATABASE_URL/PG* environment used by pg_dump, not embedded here.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL backup.")
    parser.add_argument("--database-url", required=True, help="PostgreSQL connection URL.")
    parser.add_argument("--output", required=True, help="Path to write the .dump file.")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(output),
            args.database_url,
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
