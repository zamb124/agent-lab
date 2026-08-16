export const LINNEX_FLOW_UI_TOGGLE_EVENT = 'linnex-flow-ui-toggle';

export function datasetString(script, camelKey) {
    const value = script.dataset[camelKey];
    return typeof value === 'string' ? value : '';
}

export function resolveCredentials(script) {
    const raw = datasetString(script, 'useCredentials');
    if (raw === 'false') return 'omit';
    return 'include';
}

export function resolvePresentation(script) {
    const raw = (script.dataset.presentation || 'drawer').trim().toLowerCase();
    if (raw === 'page') return 'page';
    if (raw === 'drawer') return 'drawer';
    throw new Error(`Linnex Flow UI embed: invalid data-presentation ${JSON.stringify(raw)}`);
}

export function resolveLauncherPosition(script) {
    const raw = (script.dataset.position || 'bottom-right').trim().toLowerCase();
    if (raw === 'bottom-left') return 'bottom-left';
    return 'bottom-right';
}

export function resolveToggleEventName(script) {
    const name = datasetString(script, 'toggleEventName').trim();
    if (name === '') return LINNEX_FLOW_UI_TOGGLE_EVENT;
    return name;
}

export function resolveShowLauncher(script) {
    return datasetString(script, 'showLauncher') !== 'false';
}

export async function bearerFor(script) {
    const staticBearer = script.dataset.staticBearer;
    if (typeof staticBearer === 'string' && staticBearer.trim() !== '') {
        return staticBearer;
    }
    const endpoint = script.dataset.tokenUrl;
    if (typeof endpoint !== 'string' || endpoint.trim() === '') {
        throw new Error('Linnex Flow UI embed requires data-token-url');
    }
    const expiresRaw = script.dataset.tokenExpiresSeconds;
    const expiresInSeconds = expiresRaw === undefined || expiresRaw === ''
        ? 300
        : Number(expiresRaw);
    if (!Number.isFinite(expiresInSeconds) || expiresInSeconds <= 0) {
        throw new Error('Linnex Flow UI embed: invalid data-token-expires-seconds');
    }
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            embed_id: script.dataset.embedId,
            origin: globalThis.location.origin,
            expires_in_seconds: expiresInSeconds,
        }),
    });
    if (!response.ok) throw new Error(`Linnex Flow UI token: HTTP ${response.status}`);
    const payload = await response.json();
    if (typeof payload?.token !== 'string' || payload.token.trim() === '') {
        throw new Error('Linnex Flow UI token response has no token');
    }
    return payload.token;
}

export function buildHostConfig(script, token, flowsBaseUrl) {
    const platformUiOrigin = datasetString(script, 'platformUiOrigin').trim().replace(/\/+$/, '');
    const branchId = datasetString(script, 'branchId');
    const theme = datasetString(script, 'theme');
    const locale = datasetString(script, 'locale');
    return {
        embedId: datasetString(script, 'embedId'),
        flowId: datasetString(script, 'flowId'),
        branchId: branchId === '' ? 'default' : branchId,
        baseUrl: flowsBaseUrl,
        contextId: datasetString(script, 'contextId'),
        theme: theme === '' ? 'auto' : theme,
        locale: locale === '' ? 'auto' : locale,
        profile: 'embed_public',
        companyId: datasetString(script, 'companyId'),
        voiceBaseUrl: datasetString(script, 'voiceBaseUrl'),
        platformUiOrigin,
        credentials: resolveCredentials(script),
        toggleEventName: resolveToggleEventName(script),
        getRequestHeaders: () => ({ Authorization: `Bearer ${token}` }),
    };
}
