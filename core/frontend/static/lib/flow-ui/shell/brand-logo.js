export const BRAND_LOGO_PATH = '/static/core/assets/service_logos/linnex_spinner_logo.png';

export function platformStaticSrc(platformUiOrigin, assetPath) {
    if (typeof assetPath !== 'string' || !assetPath.startsWith('/static/core/')) {
        throw new Error(
            `platformStaticSrc: assetPath must start with /static/core/, got ${JSON.stringify(assetPath)}`,
        );
    }
    if (typeof platformUiOrigin !== 'string' || platformUiOrigin.trim() === '') {
        return assetPath;
    }
    return `${platformUiOrigin.trim().replace(/\/+$/, '')}${assetPath}`;
}

export function brandLogoSrc(platformUiOrigin) {
    return platformStaticSrc(platformUiOrigin, BRAND_LOGO_PATH);
}
