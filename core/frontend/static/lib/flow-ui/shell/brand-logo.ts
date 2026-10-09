export const BRAND_LOGO_PATH = '/static/core/assets/service_logos/linnex_spinner_logo.png';

export function platformStaticSrc(platformUiOrigin: string | null | undefined, assetPath: string): string {
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

export function brandLogoSrc(platformUiOrigin: string | null | undefined): string {
    return platformStaticSrc(platformUiOrigin, BRAND_LOGO_PATH);
}
