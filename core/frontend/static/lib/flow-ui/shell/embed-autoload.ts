import { isPlainRecord } from '../../events/payload.js';
import { assignLinnexFlowUI, createLinnexFlowUI } from './embed-host-api.js';
import { FlowUIDrawer } from './drawer.js';
import { FlowUIPageHost, type FlowUiPageHostConfig } from './page-host.js';
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

function requirePageHost(element: HTMLElement): FlowUIPageHost {
    if (!(element instanceof FlowUIPageHost)) {
        throw new Error('Linnex Flow UI embed: flow-ui-page-host is not registered');
    }
    return element;
}

function requireDrawer(element: HTMLElement): FlowUIDrawer {
    if (!(element instanceof FlowUIDrawer)) {
        throw new Error('Linnex Flow UI embed: flow-ui-drawer is not registered');
    }
    return element;
}

function isPageHostConfig(value: unknown): value is FlowUiPageHostConfig {
    return isPlainRecord(value) && typeof value.baseUrl === 'string' && value.baseUrl.length > 0;
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
        const pageHost = requirePageHost(document.createElement('flow-ui-page-host'));
        applyPlatformUiOrigin(pageHost, hostConfig.platformUiOrigin);
        if (!isPageHostConfig(hostConfig)) {
            throw new Error('Linnex Flow UI embed: page host config requires baseUrl');
        }
        pageHost.config = hostConfig;
        document.body.append(pageHost);
        publishHost(pageHost, hostConfig.embedId, 'page');
        return;
    }

    const drawer = requireDrawer(document.createElement('flow-ui-drawer'));
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
    globalThis.dispatchEvent(new CustomEvent('linnex-flow-ui-error', {
        detail: Object.freeze({
            message: error instanceof Error ? error.message : String(error),
        }),
    }));
    throw error;
});
