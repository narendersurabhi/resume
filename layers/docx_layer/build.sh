#!/usr/bin/env bash
set -euo pipefail
LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$LAYER_DIR/python"
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

# x86_64. For ARM use image/tag ending with -arm64 and Architecture.ARM_64 in CDK.
docker run --rm -v "$LAYER_DIR":/opt/layer \
  --entrypoint /bin/bash \
  public.ecr.aws/lambda/python:3.12 \
  -lc '
    python -m pip install --upgrade pip &&
    pip install --no-cache-dir --only-binary=:all: \
      -t /opt/layer/python \
      python-docx==1.1.2 lxml==5.2.1
  '

echo "Layer contents:"
find "$OUT_DIR" -maxdepth 2 -type d -print
