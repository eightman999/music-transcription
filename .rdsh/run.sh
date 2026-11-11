#!/bin/bash
# 使い方: .rdsh/run.sh <task名>   (.rdsh/tasks/<task名>.md を Mistral に渡して headless 実行する)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export UV_CACHE_DIR="$ROOT/.uv-cache"
T="$1"
rdsh headless --patch .rdsh/mistral.patch.yml - < ".rdsh/tasks/$T.md" > ".rdsh/logs/$T.out" 2> ".rdsh/logs/$T.err"
echo "exit=$?"
tail -${2:-70} ".rdsh/logs/$T.out"
