"""Принудительная нормализация CRLF -> LF для vendor/goose working tree.

git checkout-index --force -c core.autocrlf=false -c core.eol=lf на Windows-
раннере GitHub Actions не гарантирует LF на диске (checkout-machinery Git for
Windows отличается от macOS/Linux) — LF-based base-патч не матчится ни по
одному файлу. Здесь делается детерминированная побайтовая нормализация по
всем файлам, отслеживаемым git в vendor/goose, минуя любые допущения о
поведении checkout/reset на конкретной платформе.

Список путей (NUL-separated, относительно vendor_dir) читается из stdin —
вызывающий передаёт `git ls-files -z`.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    vendor_dir = sys.argv[1]
    raw_paths = sys.stdin.buffer.read().split(b"\x00")
    for raw_rel in raw_paths:
        if not raw_rel:
            continue
        rel = raw_rel.decode("utf-8")
        path = os.path.join(vendor_dir, rel)
        if os.path.islink(path):
            continue
        with open(path, "rb") as file_handle:
            content = file_handle.read()
        if b"\x00" in content or b"\r\n" not in content:
            continue
        with open(path, "wb") as file_handle:
            _ = file_handle.write(content.replace(b"\r\n", b"\n"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
