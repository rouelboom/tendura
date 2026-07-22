#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
output="${1:-${repo_dir}/dist/tendura-alice.zip}"
stage_dir="$(mktemp -d)"

cleanup() {
    rm -rf "${stage_dir}"
}
trap cleanup EXIT

mkdir -p "${stage_dir}/tendura/application"
mkdir -p "${stage_dir}/tendura/alice"
mkdir -p "${stage_dir}/tendura/core"
mkdir -p "${stage_dir}/tendura/training_endurance"

cp "${repo_dir}/alice_function.py" "${stage_dir}/"
cp "${repo_dir}/tendura/__init__.py" "${repo_dir}/tendura/config.py" "${stage_dir}/tendura/"
cp "${repo_dir}/tendura/application/"*.py "${stage_dir}/tendura/application/"
cp "${repo_dir}/tendura/alice/"*.py "${stage_dir}/tendura/alice/"
cp "${repo_dir}/tendura/core/__init__.py" "${repo_dir}/tendura/core/models.py" "${stage_dir}/tendura/core/"
cp "${repo_dir}/tendura/training_endurance/"*.py "${stage_dir}/tendura/training_endurance/"
cp "${script_dir}/requirements.txt" "${stage_dir}/requirements.txt"

mkdir -p "$(dirname "${output}")"
temp_archive="${stage_dir}/tendura-alice.zip"
(
    cd "${stage_dir}"
    zip -q -r "${temp_archive}" alice_function.py requirements.txt tendura
)
mv "${temp_archive}" "${output}"
echo "${output}"
