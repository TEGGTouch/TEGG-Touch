#!/usr/bin/env bash
set -Eeuo pipefail
test "${CI_COMMIT_REF_NAME:?Missing branch}" = main
git fetch origin main --tags
test "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)"
python3 deploy/archive.py

