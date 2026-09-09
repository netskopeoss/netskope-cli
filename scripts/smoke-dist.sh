#!/usr/bin/env bash
# Install the built wheel and sdist into clean environments and check the CLI runs.
#
# Both CI and the release workflow run this, so the artifact that reaches PyPI is
# tested the same way as every pull request's. The command count is the check that
# would have caught v1.4.6, where a vendored-click mismatch collapsed
# `netskope commands` to a single node while the package still imported fine.
#
# The sdist run matters separately: Homebrew installs it with pip's
# --no-binary=:all:, so a source build that fails is only visible through
# `brew install` a day after publishing.
#
# Usage: scripts/smoke-dist.sh [dist-dir]
set -euo pipefail

dist="${1:-dist}"
min_commands="${MIN_COMMANDS:-250}"

shopt -s nullglob
wheels=("$dist"/*.whl)
sdists=("$dist"/*.tar.gz)
shopt -u nullglob

if [ "${#wheels[@]}" -ne 1 ] || [ "${#sdists[@]}" -ne 1 ]; then
    echo "expected one wheel and one sdist in $dist/, found ${#wheels[@]} and ${#sdists[@]}" >&2
    exit 1
fi

smoke() {
    local label="$1" artifact="$2" venv count
    venv="$(mktemp -d)/venv"
    uv venv --quiet "$venv"
    uv pip install --quiet --python "$venv/bin/python" "$artifact"
    echo "$label: $("$venv/bin/netskope" --version)"
    count="$("$venv/bin/netskope" commands --flat | wc -l | tr -d '[:space:]')"
    if [ "$count" -le "$min_commands" ]; then
        echo "$label: command tree listed $count commands, expected more than $min_commands" >&2
        exit 1
    fi
    echo "$label: $count commands listed"
}

smoke wheel "${wheels[0]}"
smoke sdist "${sdists[0]}"
