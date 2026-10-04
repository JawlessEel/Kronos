#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/kronos-swift-test.XXXXXX")"
trap 'rm -f "$TEST_DIR/test"; rmdir "$TEST_DIR"' EXIT
swiftc "$ROOT/Shared/ForecastSnapshot.swift" "$ROOT/Tests/main.swift" -o "$TEST_DIR/test"
"$TEST_DIR/test"
