import './drawer.js';
import './page-host.js';
import { assignLinnexFlowUI, createLinnexFlowUI } from './embed-host-api.js';
import {
    bearerFor,
    buildHostConfig,
    resolveLauncherPosition,
    resolvePresentation,
    resolveShowLauncher,
} from './embed-script-config.js';

export {
    bearerFor,
    buildHostConfig,
    LINNEX_FLOW_UI_TOGGLE_EVENT,
    resolveCredentials,
    resolvePresentation,
    resolveToggleEventName,
} from './embed-script-config.js';
export { createLinnexFlowUI } from './embed-host-api.js';

interface EmbedConfigHost extends HTMLElement {
    config: Record<string, unknown>;
    open?: boolean;
}

function sourceScript(): HTMLOrSVGElement {
    const current = document.currentScript;
    if (current instanceof HTMLScriptElement) return current;
    const scripts = [...document.querySelectorAll('script[type="module"][data-embed-id], script[type="module"][data-flow-id]')];
    const script = scripts[scripts.length - 1];
    if (!(script instanceof HTMLElement || script instanceof SVGElement)) {
        throw new Error('Linnex Flow UI embed: script tag not found');
    }
    return script;
}

function applyPlatformUiOrigin(host: HTMLElement, origin: unknown) {
    if (typeof origin !== 'string' || origin === '') {
        return;
    }
    host.setAttribute('platform-ui-origin', origin);
}

function publishHost(element: HTMLElement, embedId: unknown, presentation: 'drawer' | 'page') {
    const api = createLinnexFlowUI({ element, embedId, presentation });
    assignLinnexFlowUI(api);
    globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-mounted', {
        detail: Object.freeze({
            embedId,
            presentation,
        }),
    }));
}

export async function mount() {
    if (globalThis.linnexFlowUI) {
        throw new Error('Linnex Flow UI embed is already mounted');
    }
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
    const hostConfig = buildHostConfig(script, token, flowsBaseUrl);

    if (presentation === 'page') {
        const pageHost = document.createElement('flow-ui-page-host') as EmbedConfigHost;
        applyPlatformUiOrigin(pageHost, hostConfig.platformUiOrigin);
        pageHost.config = hostConfig;
        document.body.append(pageHost);
        publishHost(pageHost, hostConfig.embedId, 'page');
        return;
    }

    const drawer = document.createElement('flow-ui-drawer') as EmbedConfigHost;
    applyPlatformUiOrigin(drawer, hostConfig.platformUiOrigin);
    drawer.open = script.dataset.initialOpen === 'true';
    drawer.config = {
        ...hostConfig,
        showLauncher: resolveShowLauncher(script),
        launcherPosition: resolveLauncherPosition(script),
    };
    document.body.append(drawer);
    publishHost(drawer, drawer.config.embedId, 'drawer');
}

mount().catch((error) => {
    console.error('Linnex Flow UI embed failed', error);
    globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-error', {
        detail: Object.freeze({
            message: error instanceof Error ? error.message : String(error),
        }),
    }));
});
