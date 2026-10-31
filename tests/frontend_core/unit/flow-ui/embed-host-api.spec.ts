import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { prop } from '../../helpers/prop.js';

if (typeof globalThis.HTMLElement !== 'function') {
    Object.defineProperty(globalThis, 'HTMLElement', {
        value: class HTMLElement {
            config: Record<string, unknown> = {};
        },
        configurable: true,
        writable: true,
    });
}

class FlowUiStub extends HTMLElement {
    theme = 'auto';
    locale = 'auto';
    assistantTitle = '';
    getExtraMetadataVariables?: () => Record<string, unknown>;
    getRequestHeaders?: () => Record<string, string>;
}

class HostElement extends HTMLElement {
    config: Record<string, unknown>;
    flowUi: FlowUiStub;
    presentation: string;

    constructor(presentation = 'drawer') {
        super();
        this.config = {
            theme: 'auto',
            locale: 'auto',
            showLauncher: true,
            toggleEventName: 'linnex-flow-ui-toggle',
        };
        this.flowUi = new FlowUiStub();
        Object.defineProperty(this, 'shadowRoot', {
            value: {
                querySelector: (selector: string) => {
                    if (selector !== 'platform-flow-ui') {
                        return null;
                    }
                    return this.flowUi;
                },
            },
            configurable: true,
        });
        this.presentation = presentation;
    }
}

describe('window.linnexFlowUI host API', () => {
    let hostApi: typeof import('../../../../core/frontend/static/lib/flow-ui/shell/embed-host-api.js');

    beforeAll(async () => {
        hostApi = await import(
            '../../../../core/frontend/static/lib/flow-ui/shell/embed-host-api.js'
        );
    });

    afterEach(() => {
        Reflect.deleteProperty(globalThis, 'linnexFlowUI');
    });

    function apiFor(presentation: 'drawer' | 'page' = 'drawer') {
        const element = new HostElement(presentation);
        return {
            element,
            api: hostApi.createLinnexFlowUI({
                element,
                embedId: 'emb_host',
                presentation,
            }),
        };
    }

    it('exposes element, embedId and presentation', () => {
        const { element, api } = apiFor();
        expect(api.element).toBe(element);
        expect(api.embedId).toBe('emb_host');
        expect(api.presentation).toBe('drawer');
    });

    it('setTheme mutates host and flow-ui', () => {
        const { element, api } = apiFor();
        api.setTheme('light');
        expect(element.config.theme).toBe('light');
        expect(element.flowUi.theme).toBe('light');
        expect(() => api.setTheme('neon')).toThrow(/light, dark, or auto/);
    });

    it('setLocale mutates host and flow-ui', () => {
        const { element, api } = apiFor();
        api.setLocale('en');
        expect(element.config.locale).toBe('en');
        expect(element.flowUi.locale).toBe('en');
        expect(() => api.setLocale('de')).toThrow(/ru, en, or auto/);
    });

    it('setLauncherVisible is drawer-only', () => {
        const drawer = apiFor('drawer');
        drawer.api.setLauncherVisible(false);
        expect(drawer.element.config.showLauncher).toBe(false);
        expect(() => drawer.api.setLauncherVisible('no')).toThrow(/boolean/);
        const page = apiFor('page');
        expect(() => page.api.setLauncherVisible(true)).toThrow(/only drawer/);
    });

    it('setToggleEventName rewrites config', () => {
        const { element, api } = apiFor();
        api.setToggleEventName('site-open-chat');
        expect(element.config.toggleEventName).toBe('site-open-chat');
        expect(() => api.setToggleEventName('  ')).toThrow(/non-empty string/);
    });

    it('setAssistantTitle overrides chrome title', () => {
        const { element, api } = apiFor();
        api.setAssistantTitle('Support');
        expect(element.config.assistantTitle).toBe('Support');
        expect(element.flowUi.assistantTitle).toBe('Support');
        expect(() => api.setAssistantTitle('')).toThrow(/non-empty string/);
    });

    it('setMetadataHooks and setAuthProvider assign functions', () => {
        const { element, api } = apiFor();
        const extra = () => ({ page_url: 'https://shop.example' });
        const auth = () => ({ Authorization: 'Bearer x' });
        api.setMetadataHooks(extra);
        api.setAuthProvider(auth);
        expect(element.config.getExtraMetadataVariables).toBe(extra);
        expect(element.flowUi.getExtraMetadataVariables).toBe(extra);
        expect(element.config.getRequestHeaders).toBe(auth);
        expect(element.flowUi.getRequestHeaders).toBe(auth);
        expect(() => api.setMetadataHooks(null)).toThrow(/function/);
        expect(() => api.setAuthProvider(null)).toThrow(/function/);
    });

    it('assignLinnexFlowUI rejects a second mount', () => {
        const { api } = apiFor();
        hostApi.assignLinnexFlowUI(api);
        expect(prop(globalThis, 'linnexFlowUI')).toBe(api);
        expect(() => hostApi.assignLinnexFlowUI(api)).toThrow(/already mounted/);
    });
});
