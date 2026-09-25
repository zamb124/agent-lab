const PUBLIC_SEARCH_TRANSITION_STORAGE_KEY = 'platform:public_search_landing_transition';
const PUBLIC_SEARCH_TRANSITION_TTL_MS = 5000;

function _requireNonEmptyString(value, label) {
    if (typeof value !== 'string' || value.trim() === '') {
        throw new Error(`${label} must be a non-empty string`);
    }
    return value.trim();
}

function _requireSearchMode(value, label) {
    const mode = _requireNonEmptyString(value, label);
    if (mode !== 'quick' && mode !== 'deep' && mode !== 'research') {
        throw new Error(`${label} is invalid`);
    }
    return mode;
}

function _requireTransitionPayload(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error('public search transition payload must be object');
    }
    const source = _requireNonEmptyString(value.source, 'transition.source');
    if (source !== 'landing') {
        throw new Error('transition.source is invalid');
    }
    const createdAt = value.created_at;
    if (typeof createdAt !== 'number' || !Number.isFinite(createdAt)) {
        throw new Error('transition.created_at must be finite number');
    }
    return {
        source,
        query: _requireNonEmptyString(value.query, 'transition.query'),
        mode: _requireSearchMode(value.mode, 'transition.mode'),
        created_at: createdAt,
    };
}

export function markPublicSearchLandingTransition(query, mode) {
    const payload = {
        source: 'landing',
        query: _requireNonEmptyString(query, 'query'),
        mode: _requireSearchMode(mode, 'mode'),
        created_at: Date.now(),
    };
    sessionStorage.setItem(PUBLIC_SEARCH_TRANSITION_STORAGE_KEY, JSON.stringify(payload));
}

export function takePublicSearchLandingTransition(query, mode) {
    const expectedQuery = _requireNonEmptyString(query, 'query');
    const expectedMode = _requireSearchMode(mode, 'mode');
    const raw = sessionStorage.getItem(PUBLIC_SEARCH_TRANSITION_STORAGE_KEY);
    if (raw === null) {
        return false;
    }
    sessionStorage.removeItem(PUBLIC_SEARCH_TRANSITION_STORAGE_KEY);
    const payload = _requireTransitionPayload(JSON.parse(raw));
    return (
        payload.query === expectedQuery
        && payload.mode === expectedMode
        && Date.now() - payload.created_at <= PUBLIC_SEARCH_TRANSITION_TTL_MS
    );
}
