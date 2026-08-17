import { PLATFORM_FILES_DOWNLOAD_PATH_RE } from '../../utils/platform-files-url.js';
import { brandLogoSrc, platformStaticSrc } from '../shell/brand-logo.js';

function nonemptyString(value) {
    if (typeof value !== 'string') {
        return null;
    }
    const trimmed = value.trim();
    return trimmed === '' ? null : trimmed;
}

function componentImageUrl(component) {
    if (component == null) {
        return null;
    }
    if (typeof component !== 'object') {
        throw new Error('flow-ui: AgentIdentity component must be an object');
    }
    const properties = component.properties;
    if (properties == null) {
        return null;
    }
    if (typeof properties !== 'object') {
        throw new Error('flow-ui: AgentIdentity.properties must be an object');
    }
    if (!Object.prototype.hasOwnProperty.call(properties, 'image_url')) {
        return null;
    }
    const raw = properties.image_url;
    if (raw == null) {
        return null;
    }
    if (typeof raw !== 'string') {
        throw new Error('flow-ui: AgentIdentity.image_url must be a string');
    }
    return nonemptyString(raw);
}

export function agentIdentityImageUrlFromComponents(components) {
    if (components == null) {
        return null;
    }
    if (typeof components !== 'object') {
        throw new Error('flow-ui: AgentIdentity components must be an object');
    }
    let found = null;
    for (const component of Object.values(components)) {
        if (!component || typeof component !== 'object' || component.type !== 'AgentIdentity') {
            continue;
        }
        const url = componentImageUrl(component);
        if (url === null) {
            continue;
        }
        if (found !== null && found !== url) {
            throw new Error('flow-ui: AgentIdentity image_url conflict');
        }
        found = url;
    }
    return found;
}

export function agentIdentityImageUrlFromDocument(document) {
    if (document == null) {
        return null;
    }
    const surfaces = document.surfaces;
    if (surfaces == null) {
        return null;
    }
    if (typeof surfaces !== 'object') {
        throw new Error('flow-ui: document.surfaces must be an object');
    }
    let found = null;
    for (const surface of Object.values(surfaces)) {
        const fromSurface = agentIdentityImageUrlFromComponents(surface?.components);
        if (fromSurface === null) {
            continue;
        }
        if (found !== null && found !== fromSurface) {
            throw new Error('flow-ui: AgentIdentity image_url conflict');
        }
        found = fromSurface;
    }
    return found;
}

export function agentIdentityImageUrlFromProfile(profile) {
    if (profile == null) {
        return null;
    }
    const identity = profile.flow_identity;
    if (identity == null) {
        return null;
    }
    const raw = identity.image_url;
    if (raw == null) {
        return null;
    }
    if (typeof raw !== 'string') {
        throw new Error('flow-ui: flow_identity.image_url must be a string');
    }
    return nonemptyString(raw);
}

export function resolveAgentIdentityRawImageUrl({
    component,
    surface,
    document,
    profile,
    imageUrl,
} = {}) {
    const fromComponent = componentImageUrl(component);
    if (fromComponent !== null) {
        return fromComponent;
    }
    const fromSurface = surface
        ? agentIdentityImageUrlFromComponents(surface.components)
        : null;
    if (fromSurface !== null) {
        return fromSurface;
    }
    const fromDocument = agentIdentityImageUrlFromDocument(document);
    if (fromDocument !== null) {
        return fromDocument;
    }
    if (imageUrl != null) {
        if (typeof imageUrl !== 'string') {
            throw new Error('flow-ui: imageUrl must be a string');
        }
        const fromExplicit = nonemptyString(imageUrl);
        if (fromExplicit !== null) {
            return fromExplicit;
        }
    }
    return agentIdentityImageUrlFromProfile(profile);
}

export function flowUIMediaSrc(platformUiOrigin, raw) {
    if (typeof raw !== 'string' || raw.trim() === '') {
        throw new Error('flowUIMediaSrc: raw URL required');
    }
    const value = raw.trim();
    const schemeMatch = value.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
    if (schemeMatch) {
        const scheme = schemeMatch[1].toLowerCase();
        if (scheme !== 'http' && scheme !== 'https') {
            throw new Error(`flowUIMediaSrc: blocked scheme ${scheme}`);
        }
        return value;
    }
    if (!value.startsWith('/')) {
        throw new Error(`flowUIMediaSrc: expected absolute path or http(s) URL, got ${JSON.stringify(value)}`);
    }
    if (value.startsWith('/static/core/')) {
        return platformStaticSrc(platformUiOrigin, value);
    }
    if (!PLATFORM_FILES_DOWNLOAD_PATH_RE.test(value)) {
        throw new Error(`flowUIMediaSrc: unsupported path ${JSON.stringify(value)}`);
    }
    if (typeof platformUiOrigin !== 'string' || platformUiOrigin.trim() === '') {
        return value;
    }
    return `${platformUiOrigin.trim().replace(/\/+$/, '')}${value}`;
}

export function resolveAgentIdentityImageSrc({
    component,
    surface,
    document,
    profile,
    imageUrl,
    platformUiOrigin,
} = {}) {
    const raw = resolveAgentIdentityRawImageUrl({
        component,
        surface,
        document,
        profile,
        imageUrl,
    });
    if (raw === null) {
        return brandLogoSrc(platformUiOrigin);
    }
    return flowUIMediaSrc(platformUiOrigin, raw);
}
