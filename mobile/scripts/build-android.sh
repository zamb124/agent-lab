#!/usr/bin/env bash
set -euo pipefail
# Сборка Android AAB для Google Play.
# Перед запуском задайте ANDROID_KEYSTORE_PATH / ANDROID_KEYSTORE_PASSWORD /
# ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD (либо humanitec*-свойства в ~/.gradle/gradle.properties).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANDROID_DIR="$ROOT/android"
if [[ ! -d "$ANDROID_DIR" ]]; then
  echo "Нет каталога Android: $ANDROID_DIR. Сначала: npm run cap:android:init" >&2
  exit 1
fi

cd "$ROOT"
echo "[1/2] cap sync android"
npx cap sync android

cd "$ANDROID_DIR"
echo "[2/2] gradle bundleRelease"
./gradlew bundleRelease

OUT="$ANDROID_DIR/app/build/outputs/bundle/release/app-release.aab"
if [[ -f "$OUT" ]]; then
  echo "AAB готов: $OUT"
fi
