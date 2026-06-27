"""
Генерация иконок HumanitecAgent для Electron desktop (.png, .ico, .icns).

Источник: core/frontend/static/assets/service_logos/frontend_logo.svg
Фон: #1A1A2E (как PWA).

Запуск: uv run python scripts/generate_humanitec_desktop_icons.py [output_dir]
"""

from __future__ import annotations

import io
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import skia
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LOGO_SVG = ROOT / "core/frontend/static/assets/service_logos/frontend_logo.svg"
DEFAULT_OUTPUT_DIR = ROOT / "apps/agent/desktop/branding/icons"

BACKGROUND = (26 / 255, 26 / 255, 46 / 255, 1.0)

ICNS_ICONSET_ENTRIES: list[tuple[str, int]] = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

ICO_SIZES: tuple[int, ...] = (16, 32, 48, 64, 128, 256)


def render_png(logo_bytes: bytes, size: int) -> bytes:
    inner = max(1, int(size * 0.78))
    offset = (size - inner) // 2
    scale = inner / 40.0

    surface = skia.Surface(size, size)
    with surface as canvas:
        canvas.clear(skia.Color4f(*BACKGROUND))
        dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(logo_bytes))
        if dom is None:
            raise RuntimeError("Skia не разобрал frontend_logo.svg")
        dom.setContainerSize(skia.Size(40, 40))
        canvas.save()
        canvas.translate(float(offset), float(offset))
        canvas.scale(scale, scale)
        dom.render(canvas)
        canvas.restore()
    data = surface.makeImageSnapshot().encodeToData(skia.kPNG, 100)
    return data.bytes()


def write_png_icon(logo_bytes: bytes, output_dir: Path) -> None:
    _ = output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "icon.png").write_bytes(render_png(logo_bytes, 512))


def write_ico_icon(logo_bytes: bytes, output_dir: Path) -> None:
    images: list[Image.Image] = []
    for size in ICO_SIZES:
        images.append(Image.open(io.BytesIO(render_png(logo_bytes, size))))
    output_path = output_dir / "icon.ico"
    images[0].save(
        output_path,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=images[1:],
    )


def write_icns_icon(logo_bytes: bytes, output_dir: Path) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("icon.icns generation requires macOS iconutil")
    _ = output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="humanitec-iconset-") as tmp_dir:
        iconset_dir = Path(tmp_dir) / "icon.iconset"
        iconset_dir.mkdir()
        for filename, size in ICNS_ICONSET_ENTRIES:
            (iconset_dir / filename).write_bytes(render_png(logo_bytes, size))
        icns_path = output_dir / "icon.icns"
        completed = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"iconutil failed: {detail}")


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    if not LOGO_SVG.is_file():
        raise FileNotFoundError(f"Нет логотипа: {LOGO_SVG}")
    logo_bytes = LOGO_SVG.read_bytes()

    write_png_icon(logo_bytes, output_dir)
    write_ico_icon(logo_bytes, output_dir)
    write_icns_icon(logo_bytes, output_dir)

    icns_path = output_dir / "icon.icns"
    icns_size = icns_path.stat().st_size
    if icns_size < 50_000:
        raise RuntimeError(
            f"icon.icns слишком мал ({icns_size} bytes), ожидается валидный ICNS > 50KB"
        )

    print(f"OK: {output_dir / 'icon.png'}")
    print(f"OK: {output_dir / 'icon.ico'}")
    print(f"OK: {icns_path} ({icns_size} bytes)")


if __name__ == "__main__":
    main()
