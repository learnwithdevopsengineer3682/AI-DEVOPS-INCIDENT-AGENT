#!/usr/bin/env bash
set -euo pipefail
echo "Holding all 3 application DB-pool connections..."
curl -sS -X POST "http://localhost:8000/admin/hold-pool?count=3"
echo
echo "Pool stats:"
curl -sS "http://localhost:8000/debug/pool"
echo
