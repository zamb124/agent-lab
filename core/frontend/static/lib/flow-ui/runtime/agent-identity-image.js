/**
 * Картинка агента для chrome/drawer: блок ``agent_identity`` документа, затем
 * ``flow_identity.image_url`` ответа interface, иначе логотип бренда.
 */

import { PLATFORM_FILES_DOWNLOAD_PATH_RE } from '../../utils/platform-files-url.js';
import { brandLogoSrc, platformStaticSrc } from '../shell/brand-logo.js';
import { iterBlocks } from './flow-ui-store.js';

function nonemptyString(value) {
    if (value === null || value === undefined) return null;
    if (typeof value !== 'string') throw new Error('flow-ui: image_url must be a string');
    const trimmed = value.trim();
    return trimmed === '' ? null : trimmed;
}

/** ``image_url`` первого блока ``agent_identity`` документа (несовпадающие значения — ошибка). */
export function agentIdentityImageUrlFromDocument(document) {
    if (document === null || document === undefined) return null;
    if (typeof document !== 'object' || !Array.isArray(document.pages)) {
        throw new Error('flow-ui: document.pages must be an array');
    }
    let found = null;
    for (const page of document.pages) {
        for (const block of iterBlocks(page.blocks)) {
            if (block.type !== 'agent_identity') continue;
            const url = nonemptyString(block.image_url);
            if (url === null) continue;
            if (found !== null && found !== url) throw new Error('flow-ui: agent_identity image_url conflict');
            found = url;
        }
    }
    return found;
}

export function flowUIMediaSrc(platformUiOrigin, raw) {
    if (typeof raw !== 'string' || raw.trim() === '') throw new Error('flowUIMediaSrc: raw URL required');
    const value = raw.trim();
    const schemeMatch = value.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
    if (schemeMatch) {
        const scheme = schemeMatch[1].toLowerCase();
        if (scheme !== 'http' && scheme !== 'https') throw new Error(`flowUIMediaSrc: blocked scheme ${scheme}`);
        return value;
    }
    if (!value.startsWith('/')) {
        throw new Error(`flowUIMediaSrc: expected absolute path or http(s) URL, got ${JSON.stringify(value)}`);
    }
    if (value.startsWith('/static/core/')) return platformStaticSrc(platformUiOrigin, value);
    if (!PLATFORM_FILES_DOWNLOAD_PATH_RE.test(value)) throw new Error(`flowUIMediaSrc: unsupported path ${JSON.stringify(value)}`);
    if (typeof platformUiOrigin !== 'string' || platformUiOrigin.trim() === '') return value;
    return `${platformUiOrigin.trim().replace(/\/+$/, '')}${value}`;
}

/**
 * @param {{ document?: object | null, flowIdentity?: object | null, imageUrl?: string | null, platformUiOrigin?: string }} options
 */
export function resolveAgentIdentityImageSrc({ document = null, flowIdentity = null, imageUrl = null, platformUiOrigin = '' } = {}) {
    const raw = nonemptyString(imageUrl)
        ?? agentIdentityImageUrlFromDocument(document)
        ?? nonemptyString(flowIdentity && typeof flowIdentity === 'object' ? flowIdentity.image_url : null);
    if (raw === null) return brandLogoSrc(platformUiOrigin);
    return flowUIMediaSrc(platformUiOrigin, raw);
}
