const THEMES = new Set(['light', 'dark', 'auto']);
const LOCALES = new Set(['ru', 'en', 'auto']);

function requireHost(element) {
    if (!(element instanceof HTMLElement)) {
        throw new Error('linnexFlowUI: host element is required');
    }
    return element;
}

function flowUiElement(host) {
    const root = host.shadowRoot;
    if (!root) {
        throw new Error('linnexFlowUI: host shadowRoot is required');
    }
    const el = root.querySelector('platform-flow-ui');
    if (!el) {
        throw new Error('linnexFlowUI: platform-flow-ui is required');
    }
    return el;
}

function patchHostConfig(host, patch) {
    const current = host.config;
    if (!current || typeof current !== 'object') {
        throw new Error('linnexFlowUI: host config is required');
    }
    host.config = { ...current, ...patch };
}

export function createLinnexFlowUI({ element, embedId, presentation }) {
    const host = requireHost(element);
    if (presentation !== 'drawer' && presentation !== 'page') {
        throw new Error(`linnexFlowUI: invalid presentation ${JSON.stringify(presentation)}`);
    }
    if (typeof embedId !== 'string') {
        throw new Error('linnexFlowUI: embedId must be a string');
    }

    return {
        get element() {
            return host;
        },
        get embedId() {
            return embedId;
        },
        get presentation() {
            return presentation;
        },
        setTheme(theme) {
            if (typeof theme !== 'string' || !THEMES.has(theme)) {
                throw new Error('linnexFlowUI.setTheme: theme must be light, dark, or auto');
            }
            patchHostConfig(host, { theme });
            flowUiElement(host).theme = theme;
        },
        setLocale(locale) {
            if (typeof locale !== 'string' || !LOCALES.has(locale)) {
                throw new Error('linnexFlowUI.setLocale: locale must be ru, en, or auto');
            }
            patchHostConfig(host, { locale });
            flowUiElement(host).locale = locale;
        },
        setLauncherVisible(visible) {
            if (presentation !== 'drawer') {
                throw new Error('linnexFlowUI.setLauncherVisible: only drawer presentation');
            }
            if (typeof visible !== 'boolean') {
                throw new Error('linnexFlowUI.setLauncherVisible: visible must be boolean');
            }
            patchHostConfig(host, { showLauncher: visible });
        },
        setToggleEventName(name) {
            if (typeof name !== 'string' || name.trim() === '') {
                throw new Error('linnexFlowUI.setToggleEventName: name must be a non-empty string');
            }
            patchHostConfig(host, { toggleEventName: name.trim() });
        },
        setAssistantTitle(title) {
            if (typeof title !== 'string' || title.trim() === '') {
                throw new Error('linnexFlowUI.setAssistantTitle: title must be a non-empty string');
            }
            const next = title.trim();
            patchHostConfig(host, { assistantTitle: next });
            flowUiElement(host).assistantTitle = next;
        },
        setMetadataHooks(extraMetadataProvider) {
            if (typeof extraMetadataProvider !== 'function') {
                throw new Error('linnexFlowUI.setMetadataHooks: extraMetadataProvider must be a function');
            }
            patchHostConfig(host, { getExtraMetadataVariables: extraMetadataProvider });
            flowUiElement(host).getExtraMetadataVariables = extraMetadataProvider;
        },
        setAuthProvider(authProvider) {
            if (typeof authProvider !== 'function') {
                throw new Error('linnexFlowUI.setAuthProvider: authProvider must be a function');
            }
            patchHostConfig(host, { getRequestHeaders: authProvider });
            flowUiElement(host).getRequestHeaders = authProvider;
        },
    };
}

export function assignLinnexFlowUI(api) {
    if (globalThis.linnexFlowUI) {
        throw new Error('Linnex Flow UI embed is already mounted');
    }
    globalThis.linnexFlowUI = api;
}
