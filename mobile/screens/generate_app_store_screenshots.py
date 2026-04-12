#!/usr/bin/env python3
"""
Генерация PNG фиксированных размеров для App Store Connect из исходников.

Исходники: mobile/screens/source/ (iPhone + iPad), mobile/screens/source_watch/ (Watch),
mobile/screens/source_mac/ (Mac, опционально).
Результат: mobile/screens/generated/<имя_набора>/01.png, 02.png, ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}

# iPhone + iPad 12.9" / 13" — размеры из требований App Store Connect
PHONE_TABLET_TARGETS: list[tuple[int, int, str]] = [
    (1242, 2688, "iphone_ipad_1242x2688"),
    (2688, 1242, "iphone_ipad_2688x1242"),
    (1284, 2778, "iphone_ipad_1284x2778"),
    (2778, 1284, "iphone_ipad_2778x1284"),
    (2064, 2752, "iphone_ipad_2064x2752"),
    (2752, 2064, "iphone_ipad_2752x2064"),
    (2048, 2732, "iphone_ipad_2048x2732"),
    (2732, 2048, "iphone_ipad_2732x2048"),
]

WATCH_TARGETS: list[tuple[int, int, str]] = [
    (422, 514, "watch_ultra3_422x514"),
    (410, 502, "watch_ultra3_410x502"),
    (416, 496, "watch_series11_416x496"),
    (396, 484, "watch_series9_396x484"),
    (368, 448, "watch_series6_368x448"),
    (312, 390, "watch_series3_312x390"),
]

# Mac App Store — размеры из подсказки App Store Connect
MAC_TARGETS: list[tuple[int, int, str]] = [
    (1280, 800, "mac_1280x800"),
    (1440, 900, "mac_1440x900"),
    (2560, 1600, "mac_2560x1600"),
    (2880, 1800, "mac_2880x1800"),
]

ASC_SCREENSHOT_MAX = 10


def _list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files: list[Path] = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix in IMAGE_EXTENSIONS:
            files.append(p)
    files.sort(key=lambda x: x.name.lower())
    return files


def _list_images_flat_screens_root(screens_root: Path) -> list[Path]:
    """
    PNG/JPEG прямо в mobile/screens/ (не в подпапках), если пользователь положил файлы рядом со скриптом.
    """
    skip_names = {"generated"}
    files: list[Path] = []
    for p in screens_root.iterdir():
        if p.is_dir() and p.name in skip_names:
            continue
        if p.is_file() and p.suffix in IMAGE_EXTENSIONS:
            files.append(p)
    files.sort(key=lambda x: x.name.lower())
    return files


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[3] if image.mode == "RGBA" else None)
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _fit_to_size(image: Image.Image, width: int, height: int) -> Image.Image:
    rgb = _to_rgb(image)
    return ImageOps.fit(
        rgb,
        (width, height),
        method=Image.Resampling.LANCZOS,
        bleed=0.0,
        centering=(0.5, 0.5),
    )


def _write_png(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _generate_for_targets(
    sources: list[Path],
    targets: list[tuple[int, int, str]],
    out_root: Path,
    label: str,
) -> None:
    if len(sources) == 0:
        return
    if len(sources) > ASC_SCREENSHOT_MAX:
        print(
            f"Предупреждение ({label}): файлов {len(sources)} — в App Store Connect "
            f"обычно не больше {ASC_SCREENSHOT_MAX} скриншотов на слот.",
            file=sys.stderr,
        )
    for width, height, folder_name in targets:
        dest_dir = out_root / folder_name
        for index, src in enumerate(sources, start=1):
            with Image.open(src) as im:
                fitted = _fit_to_size(im, width, height)
            out_name = f"{index:02d}.png"
            _write_png(dest_dir / out_name, fitted)
        print(f"{label}: {len(sources)} файлов -> {dest_dir} ({width}x{height})")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Ресайз скриншотов под размеры App Store Connect (PNG).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=script_dir / "source",
        help="Папка с исходниками для iPhone/iPad (по умолчанию: ./source рядом со скриптом)",
    )
    parser.add_argument(
        "--source-watch",
        type=Path,
        default=script_dir / "source_watch",
        help="Папка с исходниками для Apple Watch",
    )
    parser.add_argument(
        "--source-mac",
        type=Path,
        default=script_dir / "source_mac",
        help="Папка с исходниками для Mac (по умолчанию: ./source_mac)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=script_dir / "generated",
        help="Корень выходных каталогов (по умолчанию: ./generated)",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    source_watch = args.source_watch.resolve()
    source_mac = args.source_mac.resolve()
    out_root = args.out.resolve()

    phone_tablet = _list_images(source)
    if len(phone_tablet) == 0:
        phone_tablet = _list_images_flat_screens_root(script_dir)
    if len(phone_tablet) == 0:
        raise SystemExit(
            f"Нет изображений: положите PNG/JPEG в {source} или прямо в {script_dir}, затем запустите снова."
        )

    watch_list = _list_images(source_watch)
    if len(watch_list) == 0:
        watch_list = phone_tablet
        print(
            "Watch: в source_watch нет картинок — для слотов Watch используются те же файлы, "
            "что и для iPhone/iPad (уменьшение под размеры часов). "
            f"Отдельные кадры часов: положите PNG в {source_watch} и запустите снова.",
            file=sys.stderr,
        )

    mac_list = _list_images(source_mac)
    if len(mac_list) == 0:
        mac_list = phone_tablet
        print(
            "Mac: в source_mac нет картинок — для Mac App Store используются те же файлы, "
            "что и для iPhone/iPad (масштаб под широкие слоты). "
            f"Отдельные кадры с десктопа: положите PNG в {source_mac} и запустите снова.",
            file=sys.stderr,
        )

    out_root.mkdir(parents=True, exist_ok=True)

    _generate_for_targets(phone_tablet, PHONE_TABLET_TARGETS, out_root, "iPhone/iPad")
    _generate_for_targets(watch_list, WATCH_TARGETS, out_root, "Watch")
    _generate_for_targets(mac_list, MAC_TARGETS, out_root, "Mac")

    print(f"Готово. Выход: {out_root}")


if __name__ == "__main__":
    main()
