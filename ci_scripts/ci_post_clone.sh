#!/bin/sh
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/mobile"
npm ci
cd ios/App
pod install
