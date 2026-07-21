#!/bin/sh
set -eu

model_root="${1:-models}"
model_name="vosk-model-small-ru-0.22"
model_dir="$model_root/$model_name"

if [ -d "$model_dir" ]; then
    exit 0
fi

mkdir -p "$model_root"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
curl -fsSL "https://alphacephei.com/vosk/models/$model_name.zip" -o "$tmp_dir/model.zip"
unzip -q "$tmp_dir/model.zip" -d "$tmp_dir"
mv "$tmp_dir/$model_name" "$model_dir"
