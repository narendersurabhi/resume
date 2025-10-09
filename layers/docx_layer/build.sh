#!/usr/bin/env bash
set -euo pipefail
LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$LAYER_DIR/python"
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

# x86_64 build; switch image to ...python:3.12-arm64 if your Lambda is ARM
docker run --rm -v "$LAYER_DIR":/opt/layer \
  public.ecr.aws/lambda/python:3.12 \
  /bin/bash -lc '
    python -m pip install --upgrade pip &&
    pip install --no-cache-dir --only-binary=:all: \
      -t /opt/layer/python \
      python-docx==1.1.2 lxml==5.2.1
  '
