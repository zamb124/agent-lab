const THEMES = new Set(['light', 'dark', 'auto']);
const LOCALES = new Set(['ru', 'en', 'auto']);

/** ``platform-flow-ui`` внутри shadow-хоста: свойства, которыми управляет embed API. */
interface FlowUiElementLike extends HTMLElement {
    theme: string;
    locale: string;
    assistantTitle: string;
    getExtraMetadataVariables: unknown;
    getRequestHeaders: unknown;
}

interface FlowUiEmbedHost extends HTMLElement {
    config: Record<string, unknown>;
}

export type LinnexFlowUIPresentation = 'drawer' | 'page';

export interface LinnexFlowUIApi {
    readonly element: HTMLElement;
    readonly embedId: string;
    readonly presentation: LinnexFlowUIPresentation;
    setTheme(theme: unknown): void;
    setLocale(locale: unknown): void;
    setLauncherVisible(visible: unknown): void;
    setToggleEventName(name: unknown): void;
    setAssistantTitle(title: unknown): void;
    setMetadataHooks(extraMetadataProvider: unknown): void;
    setAuthProvider(authProvider: unknown): void;
}

declare global {
    // eslint-disable-next-line no-var
    var linnexFlowUI: LinnexFlowUIApi | undefined;
}

function requireHost(element: unknown): FlowUiEmbedHost {
    if (!(element instanceof HTMLElement)) {
        throw new Error('linnexFlowUI: host element is required');
    }
    return element as FlowUiEmbedHost;
}

function flowUiElement(host: HTMLElement): FlowUiElementLike {
    const root = host.shadowRoot;
    if (!root) {
        throw new Error('linnexFlowUI: host shadowRoot is required');
    }
    const el = root.querySelector('platform-flow-ui');
    if (!el) {
        throw new Error('linnexFlowUI: platform-flow-ui is required');
    }
    return el as FlowUiElementLike;
}

function patchHostConfig(host: FlowUiEmbedHost, patch: Record<string, unknown>) {
    const current = host.config;
    if (!current || typeof current !== 'object') {
        throw new Error('linnexFlowUI: host config is required');
    }
    host.config = { ...current, ...patch };
}

export function createLinnexFlowUI({ element, embedId, presentation }: {
    element: unknown;
    embedId: unknown;
    presentation: unknown;
}): LinnexFlowUIApi {
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
        setTheme(theme: unknown) {
            if (typeof theme !== 'string' || !THEMES.has(theme)) {
                throw new Error('linnexFlowUI.setTheme: theme must be light, dark, or auto');
            }
            patchHostConfig(host, { theme });
            flowUiElement(host).theme = theme;
        },
        setLocale(locale: unknown) {
            if (typeof locale !== 'string' || !LOCALES.has(locale)) {
                throw new Error('linnexFlowUI.setLocale: locale must be ru, en, or auto');
            }
            patchHostConfig(host, { locale });
            flowUiElement(host).locale = locale;
        },
        setLauncherVisible(visible: unknown) {
            if (presentation !== 'drawer') {
                throw new Error('linnexFlowUI.setLauncherVisible: only drawer presentation');
            }
            if (typeof visible !== 'boolean') {
                throw new Error('linnexFlowUI.setLauncherVisible: visible must be boolean');
            }
            patchHostConfig(host, { showLauncher: visible });
        },
        setToggleEventName(name: unknown) {
            if (typeof name !== 'string' || name.trim() === '') {
                throw new Error('linnexFlowUI.setToggleEventName: name must be a non-empty string');
            }
            patchHostConfig(host, { toggleEventName: name.trim() });
        },
        setAssistantTitle(title: unknown) {
            if (typeof title !== 'string' || title.trim() === '') {
                throw new Error('linnexFlowUI.setAssistantTitle: title must be a non-empty string');
            }
            const next = title.trim();
            patchHostConfig(host, { assistantTitle: next });
            flowUiElement(host).assistantTitle = next;
        },
        setMetadataHooks(extraMetadataProvider: unknown) {
            if (typeof extraMetadataProvider !== 'function') {
                throw new Error('linnexFlowUI.setMetadataHooks: extraMetadataProvider must be a function');
            }
            patchHostConfig(host, { getExtraMetadataVariables: extraMetadataProvider });
            flowUiElement(host).getExtraMetadataVariables = extraMetadataProvider;
        },
        setAuthProvider(authProvider: unknown) {
            if (typeof authProvider !== 'function') {
                throw new Error('linnexFlowUI.setAuthProvider: authProvider must be a function');
            }
            patchHostConfig(host, { getRequestHeaders: authProvider });
            flowUiElement(host).getRequestHeaders = authProvider;
        },
    };
}

export function assignLinnexFlowUI(api: LinnexFlowUIApi): void {
    if (globalThis.linnexFlowUI) {
        throw new Error('Linnex Flow UI embed is already mounted');
    }
    globalThis.linnexFlowUI = api;
}
