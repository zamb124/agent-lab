export const FLOW_UI_VIEWPORT_PROFILES = Object.freeze({
    'mobile-compact': Object.freeze({ css_width: 390, css_height: 844, device_pixel_ratio: 2, band: 'compact' }),
    'tablet-medium': Object.freeze({ css_width: 768, css_height: 1024, device_pixel_ratio: 2, band: 'medium' }),
    'desktop-wide': Object.freeze({ css_width: 1440, css_height: 960, device_pixel_ratio: 1, band: 'wide' }),
    'embed-inline': Object.freeze({ css_width: 420, css_height: 680, device_pixel_ratio: 1, band: 'compact' }),
});

export function containerBand(width) {
    if (width < 600) return 'compact';
    if (width < 960) return 'medium';
    return 'wide';
}
