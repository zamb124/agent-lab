"""
Сборка PWA / iOS иконок Humanitec: знак из frontend_logo.svg на тёмном фоне (#1a1a2e, как в manifest).

Запуск из корня репо: uv run python scripts/generate_humanitec_pwa_icons.py
Требуется зависимость: skia-python (группа dev в pyproject.toml).
"""

from __future__ import annotations

from pathlib import Path

import skia

ROOT = Path(__file__).resolve().parents[1]
LOGO_SVG = ROOT / "core/frontend/static/assets/service_logos/frontend_logo.svg"
ICONS_DIR = ROOT / "core/frontend/static/pwa/icons"
IOS_ICON = (
    ROOT
    / "mobile/ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png"
)

BACKGROUND = (26 / 255, 26 / 255, 46 / 255, 1.0)


def render_png(logo_bytes: bytes, size: int, *, maskable: bool) -> bytes:
    if maskable:
        inner = max(1, int(size * 0.62))
    else:
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


def main() -> None:
    if not LOGO_SVG.is_file():
        raise FileNotFoundError(f"Нет логотипа: {LOGO_SVG}")
    logo_bytes = LOGO_SVG.read_bytes()

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    for s in (72, 96, 128, 144, 152, 180, 192, 384, 512):
        path = ICONS_DIR / f"icon-{s}x{s}.png"
        path.write_bytes(render_png(logo_bytes, s, maskable=False))

    for s in (192, 512):
        path = ICONS_DIR / f"maskable-{s}x{s}.png"
        path.write_bytes(render_png(logo_bytes, s, maskable=True))

    (ICONS_DIR / "badge-72x72.png").write_bytes(render_png(logo_bytes, 72, maskable=False))

    IOS_ICON.parent.mkdir(parents=True, exist_ok=True)
    IOS_ICON.write_bytes(render_png(logo_bytes, 1024, maskable=False))

    print(f"OK: {ICONS_DIR}, {IOS_ICON}")


if __name__ == "__main__":
    main()
