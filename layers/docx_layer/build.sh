#!/usr/bin/env bash
set -euo pipefail

LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$LAYER_DIR/python"
ZIP_PATH="$LAYER_DIR/layer.zip"

# Clean
rm -rf "$OUT_DIR" "$ZIP_PATH"
mkdir -p "$OUT_DIR"

# Build inside Lambda's Python 3.12 image (x86_64). For ARM, see note below.
docker run --rm -v "$LAYER_DIR":/opt/layer \
  --entrypoint /bin/bash public.ecr.aws/lambda/python:3.12 -lc '
    set -e
    python -m pip install --upgrade pip

    # 1) Force a manylinux wheel for lxml (no compiling)
    pip install --no-cache-dir --only-binary=:all: \
      -t /opt/layer/python \
      "lxml==5.2.1"

    # 2) Install pure-Python deps (allow sdists)
    pip install --no-cache-dir \
      -t /opt/layer/python \
      "python-docx==1.1.2" \
      "jinja2==3.1.4" \
      "six>=1.16.0" \
      "docxcompose>=1.3,<2.0" \
      "docxtpl==0.16.7"
  '

echo "Layer contents:"
find "$OUT_DIR" -maxdepth 2 -type d -print

# Zip with "python/" at the root of the archive
cd "$LAYER_DIR"
zip -r9 layer.zip python > /dev/null
echo "Created $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"
