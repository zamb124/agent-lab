"""
Генерация объединённых JSON переводов для статической отдачи через nginx.

Читает core/i18n/translations/{locale}/*.json, мержит в один объект
(ключ верхнего уровня = имя файла без .json, файлы с префиксом _ пропускаются),
записывает результат в {output}/{locale}.json.

Использование:
    python -m scripts.build_i18n                          # -> core/i18n/generated/
    python -m scripts.build_i18n --output /app/static/i18n
"""

import argparse
import json
from pathlib import Path
from typing import Any

SUPPORTED_LOCALES = ("ru", "en")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_ROOT = PROJECT_ROOT / "core" / "i18n" / "translations"


def merge_locale(locale: str) -> dict[str, Any]:
    locale_dir = TRANSLATIONS_ROOT / locale
    if not locale_dir.is_dir():
        raise FileNotFoundError(f"Директория переводов не найдена: {locale_dir}")

    merged: dict[str, Any] = {}
    for file_path in sorted(locale_dir.glob("*.json")):
        namespace = file_path.stem
        if namespace.startswith("_"):
            continue
        with open(file_path, encoding="utf-8") as f:
            merged[namespace] = json.load(f)

    return merged


def build(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for locale in SUPPORTED_LOCALES:
        merged = merge_locale(locale)
        out_path = output_dir / f"{locale}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{locale}: {len(merged)} namespaces -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка объединённых JSON переводов")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "core" / "i18n" / "generated",
        help="Директория для записи результатов (по умолчанию core/i18n/generated/)",
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
