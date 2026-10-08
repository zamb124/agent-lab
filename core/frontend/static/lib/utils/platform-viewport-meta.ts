/**
 * Канон meta viewport для веб-UI (без pinch/double-tap zoom).
 * Дублирует строку `PLATFORM_MOBILE_VIEWPORT_CONTENT` в `core/frontend/viewport.py` — при смене править оба.
 */
export const PLATFORM_MOBILE_VIEWPORT_CONTENT =
    'width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no, viewport-fit=cover';
