/**
 * Якорный скролл лендинга: секции с id живут в shadow DOM landing-page,
 * поэтому при переходе с других страниц цель передаётся через sessionStorage.
 */
export const LANDING_SECTION_TARGET_STORAGE_KEY = 'platform:landing_section_target';

const ALLOWED_SECTION_IDS = new Set(['about', 'abilities']);

export function isAllowedLandingScrollSectionId(sectionId) {
    return typeof sectionId === 'string' && ALLOWED_SECTION_IDS.has(sectionId);
}

export function storePendingLandingSectionTarget(sectionId) {
    if (!isAllowedLandingScrollSectionId(sectionId)) {
        throw new Error(`landing_section_scroll: invalid sectionId "${sectionId}"`);
    }
    sessionStorage.setItem(LANDING_SECTION_TARGET_STORAGE_KEY, sectionId);
}

export function takePendingLandingSectionTarget() {
    const raw = sessionStorage.getItem(LANDING_SECTION_TARGET_STORAGE_KEY);
    sessionStorage.removeItem(LANDING_SECTION_TARGET_STORAGE_KEY);
    if (raw === null || raw === '') {
        return null;
    }
    if (!isAllowedLandingScrollSectionId(raw)) {
        return null;
    }
    return raw;
}
