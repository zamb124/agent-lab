"""
Единое значение meta viewport для веб-UI платформы (мобильные: без pinch/double-tap zoom).
Статические index.html дублируют эту строку в атрибуте content — при смене править и их.
"""

PLATFORM_MOBILE_VIEWPORT_CONTENT: str = (
    "width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, "
    "user-scalable=no, viewport-fit=cover"
)
