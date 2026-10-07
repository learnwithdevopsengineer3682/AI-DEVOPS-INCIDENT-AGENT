#!/usr/bin/env bash
set -euo pipefail
curl -sS -X POST "http://localhost:8000/admin/release-pool"
echo
