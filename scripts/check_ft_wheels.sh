#!/usr/bin/env bash
# free-threaded wheel-gate: после `uv lock` проверяет что все non-ML
# зависимости имеют cp314t wheel (или собираются из sdist в чистом venv).
# ML-стек (HuggingFace, silero, pyannote) выведен в allowlist — он
# самовоскрешает GIL внутри provider_litserve/rag_worker (known limitation).

set -euo pipefail

cd "$(dirname "$0")/.."

ALLOW_SDIST_PATTERN='^(transformers|sentence-transformers|flagembedding|tokenizers|pyannote-audio|silero|silero-vad|psycopg|litserve)'

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

uv export --frozen --no-dev --no-default-groups \
  --group core --group agents --group worker-base --group crm --group sync \
  --no-annotate --no-header --no-emit-project \
  -o "$TMPDIR/req.txt"

grep -vE "$ALLOW_SDIST_PATTERN" "$TMPDIR/req.txt" > "$TMPDIR/req-strict.txt"

uv venv --python 3.14t "$TMPDIR/venv" >/dev/null
"$TMPDIR/venv/bin/python" -m pip install --quiet --upgrade pip
"$TMPDIR/venv/bin/python" -m pip install --only-binary=:all: -r "$TMPDIR/req-strict.txt"

echo "check-ft-wheels: OK"
