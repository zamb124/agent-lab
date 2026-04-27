"""
Единое значение meta viewport для веб-UI платформы (мобильные: без pinch/double-tap zoom).
Та же строка, что `PLATFORM_MOBILE_VIEWPORT_CONTENT` в
`core/frontend/static/lib/utils/platform-viewport-meta.js`; статические `apps/*/ui/index.html`
дублируют content — при смене править все три.
"""

PLATFORM_MOBILE_VIEWPORT_CONTENT: str = (
    "width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, "
    "user-scalable=no, viewport-fit=cover"
)
