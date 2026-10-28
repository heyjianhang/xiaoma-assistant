#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec uv run --directory apps/api uvicorn xiaoma.app:app --host 127.0.0.1 --port 2025 --no-access-log
