import './drawer.js';
import './page-host.js';

function sourceScript() {
    const current = document.currentScript;
    if (current instanceof HTMLScriptElement) return current;
    const scripts = [...document.querySelectorAll('script[type="module"][data-embed-id], script[type="module"][data-flow-id]')];
    if (scripts.length === 0) {
        throw new Error('Linnex Flow UI embed: script tag not found');
    }
    return scripts[scripts.length - 1];
}

async function bearerFor(script) {
    if (script.dataset.staticBearer) return script.dataset.staticBearer;
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

function resolvePresentation(script) {
    const raw = (script.dataset.presentation || 'drawer').trim().toLowerCase();
    if (raw === 'page') return 'page';
    if (raw === 'drawer') return 'drawer';
    throw new Error(`Linnex Flow UI embed: invalid data-presentation ${JSON.stringify(raw)}`);
}

function resolveLauncherPosition(script) {
    const raw = (script.dataset.position || 'bottom-right').trim().toLowerCase();
    if (raw === 'bottom-left') return 'bottom-left';
    return 'bottom-right';
}

async function mount() {
    const script = sourceScript();
    if (!script.dataset.embedId && !script.dataset.flowId) {
        throw new Error('Linnex Flow UI embed requires data-embed-id or data-flow-id');
    }
    const token = await bearerFor(script);
    const flowsBaseUrl = script.dataset.flowsBaseUrl;
    if (typeof flowsBaseUrl !== 'string' || flowsBaseUrl.trim() === '') {
        throw new Error('Linnex Flow UI embed requires data-flows-base-url');
    }
    const presentation = resolvePresentation(script);
    const hostConfig = {
        embedId: script.dataset.embedId || '',
        flowId: script.dataset.flowId || '',
        branchId: script.dataset.branchId || 'default',
        baseUrl: flowsBaseUrl,
        contextId: script.dataset.contextId || '',
        theme: script.dataset.theme || 'auto',
        locale: script.dataset.locale || 'auto',
        profile: 'embed_public',
        getRequestHeaders: () => ({ Authorization: `Bearer ${token}` }),
    };

    if (presentation === 'page') {
        const pageHost = document.createElement('flow-ui-page-host');
        pageHost.config = hostConfig;
        document.body.append(pageHost);
        globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-mounted', {
            detail: Object.freeze({
                embedId: hostConfig.embedId,
                presentation: 'page',
            }),
        }));
        return;
    }

    const drawer = document.createElement('flow-ui-drawer');
    drawer.open = script.dataset.initialOpen === 'true';
    drawer.config = {
        ...hostConfig,
        showLauncher: script.dataset.showLauncher !== 'false',
        launcherPosition: resolveLauncherPosition(script),
    };
    document.body.append(drawer);
    globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-mounted', {
        detail: Object.freeze({
            embedId: drawer.config.embedId,
            presentation: 'drawer',
        }),
    }));
}

mount().catch((error) => {
    console.error('Linnex Flow UI embed failed', error);
    globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-error', {
        detail: Object.freeze({
            message: error instanceof Error ? error.message : String(error),
        }),
    }));
});
