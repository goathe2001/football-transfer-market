#!/usr/bin/env bash
# Download the transfermarkt-datasets DuckDB file (github.com/dcaribou/transfermarkt-datasets).
# The file is large and refreshed weekly, so it is not committed to git (see .gitignore).
set -euo pipefail
cd "$(dirname "$0")"
curl -L -o transfermarkt.duckdb \
  https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfermarkt-datasets.duckdb
echo "Saved to data/transfermarkt.duckdb"
