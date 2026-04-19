"""
Сборка иконок Humanitec для PWA, iOS и Android (Capacitor + Google Play).

Источник логотипа: core/frontend/static/assets/service_logos/frontend_logo.svg.
Фон: #1a1a2e (как background_color в PWA manifest и Splash Screen на iOS/Android).

Запуск из корня репо: uv run python scripts/generate_humanitec_pwa_icons.py
Зависимость: skia-python (группа dev в pyproject.toml).
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
ANDROID_RES = ROOT / "mobile/android/app/src/main/res"
PLAY_DIR = ROOT / "mobile/screens"

BACKGROUND = (26 / 255, 26 / 255, 46 / 255, 1.0)
BACKGROUND_HEX = "#1A1A2E"
ACCENT_HEX = "#16213E"

ANDROID_MIPMAP_DENSITIES: list[tuple[str, int]] = [
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
]

# Adaptive-icon foreground: 108dp, безопасная зона по центру 66dp.
# Множитель 108/48 = 2.25 относительно базового mipmap-mdpi 48px.
ANDROID_ADAPTIVE_FOREGROUND: list[tuple[str, int]] = [
    ("mipmap-mdpi", 108),
    ("mipmap-hdpi", 162),
    ("mipmap-xhdpi", 216),
    ("mipmap-xxhdpi", 324),
    ("mipmap-xxxhdpi", 432),
]


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


def render_round_png(logo_bytes: bytes, size: int) -> bytes:
    """Круглая иконка для ic_launcher_round.png (Android)."""
    surface = skia.Surface(size, size)
    with surface as canvas:
        canvas.clear(skia.Color4f(0, 0, 0, 0))
        path = skia.Path()
        path.addCircle(size / 2.0, size / 2.0, size / 2.0)
        canvas.clipPath(path, skia.ClipOp.kIntersect, True)
        canvas.clear(skia.Color4f(*BACKGROUND))
        inner = max(1, int(size * 0.78))
        offset = (size - inner) // 2
        scale = inner / 40.0
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


def render_adaptive_foreground_png(logo_bytes: bytes, size: int) -> bytes:
    """
    Foreground adaptive-icon (Android): прозрачный фон, логотип по центру в безопасной зоне 66/108.
    Сам фон рисует drawable из ic_launcher_background.
    """
    safe_ratio = 66.0 / 108.0
    inner = max(1, int(size * safe_ratio))
    offset = (size - inner) // 2
    scale = inner / 40.0

    surface = skia.Surface(size, size)
    with surface as canvas:
        canvas.clear(skia.Color4f(0, 0, 0, 0))
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


def render_play_feature_graphic(logo_bytes: bytes) -> bytes:
    """
    Feature Graphic для Google Play (1024×500): тёмный градиент + крупный знак слева,
    «Humanitec» — справа белым шрифтом по центру по вертикали.
    """
    width, height = 1024, 500
    surface = skia.Surface(width, height)
    with surface as canvas:
        gradient = skia.GradientShader.MakeLinear(
            points=[skia.Point(0, 0), skia.Point(width, height)],
            colors=[
                skia.Color(int(BACKGROUND_HEX[1:3], 16), int(BACKGROUND_HEX[3:5], 16), int(BACKGROUND_HEX[5:7], 16), 255),
                skia.Color(int(ACCENT_HEX[1:3], 16), int(ACCENT_HEX[3:5], 16), int(ACCENT_HEX[5:7], 16), 255),
            ],
        )
        bg_paint = skia.Paint(Shader=gradient, AntiAlias=True)
        canvas.drawRect(skia.Rect.MakeWH(width, height), bg_paint)

        logo_size = 320
        logo_offset_x = 96
        logo_offset_y = (height - logo_size) // 2
        dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(logo_bytes))
        if dom is None:
            raise RuntimeError("Skia не разобрал frontend_logo.svg")
        dom.setContainerSize(skia.Size(40, 40))
        canvas.save()
        canvas.translate(float(logo_offset_x), float(logo_offset_y))
        scale = logo_size / 40.0
        canvas.scale(scale, scale)
        dom.render(canvas)
        canvas.restore()

        font = skia.Font(skia.Typeface("Helvetica", skia.FontStyle.Bold()), 96)
        text_paint = skia.Paint(AntiAlias=True, Color=skia.ColorWHITE)
        canvas.drawString("Humanitec", 480, 280, font, text_paint)

        sub_font = skia.Font(skia.Typeface("Helvetica"), 36)
        sub_paint = skia.Paint(AntiAlias=True, Color=skia.Color(220, 220, 230, 255))
        canvas.drawString("AI-агенты для бизнеса", 480, 340, sub_font, sub_paint)
    data = surface.makeImageSnapshot().encodeToData(skia.kPNG, 100)
    return data.bytes()


def write_android_resources(logo_bytes: bytes) -> None:
    if not ANDROID_RES.is_dir():
        return

    # ic_launcher.png и ic_launcher_round.png по плотностям
    for folder, size in ANDROID_MIPMAP_DENSITIES:
        target = ANDROID_RES / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / "ic_launcher.png").write_bytes(render_png(logo_bytes, size, maskable=False))
        (target / "ic_launcher_round.png").write_bytes(render_round_png(logo_bytes, size))

    # foreground для adaptive-icon
    for folder, size in ANDROID_ADAPTIVE_FOREGROUND:
        target = ANDROID_RES / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / "ic_launcher_foreground.png").write_bytes(
            render_adaptive_foreground_png(logo_bytes, size)
        )

    # Цвет фона adaptive-icon — наш бренд
    values_dir = ANDROID_RES / "values"
    values_dir.mkdir(parents=True, exist_ok=True)
    (values_dir / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{BACKGROUND_HEX}</color>\n'
        "</resources>\n",
        encoding="utf-8",
    )

    # adaptive-icon XML: foreground PNG (без vector drawable, чтобы не зависеть от svg инструментов)
    adaptive_dir = ANDROID_RES / "mipmap-anydpi-v26"
    adaptive_dir.mkdir(parents=True, exist_ok=True)
    adaptive_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        "</adaptive-icon>\n"
    )
    (adaptive_dir / "ic_launcher.xml").write_text(adaptive_xml, encoding="utf-8")
    (adaptive_dir / "ic_launcher_round.xml").write_text(adaptive_xml, encoding="utf-8")


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

    write_android_resources(logo_bytes)

    PLAY_DIR.mkdir(parents=True, exist_ok=True)
    (PLAY_DIR / "play_icon_512.png").write_bytes(render_png(logo_bytes, 512, maskable=False))
    (PLAY_DIR / "play_feature_graphic_1024x500.png").write_bytes(
        render_play_feature_graphic(logo_bytes)
    )

    print(f"OK: {ICONS_DIR}")
    print(f"OK: {IOS_ICON}")
    print(f"OK: {ANDROID_RES} (mipmap-* + values + mipmap-anydpi-v26)")
    print(f"OK: {PLAY_DIR}/play_icon_512.png и play_feature_graphic_1024x500.png")


if __name__ == "__main__":
    main()
