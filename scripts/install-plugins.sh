#!/usr/bin/env bash

set -e

echo "Installing q8s plugins..."

for dir in plugins/*; do
  if [ -f "$dir/pyproject.toml" ]; then
    echo "→ Installing $dir"
    pip install -e "$dir"
  fi
done

echo "Done."
