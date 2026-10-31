import { LitElement, css, html } from 'lit';
import '../components/platform-flow-ui.js';

/**
 * Full-viewport embed host for EmbedConfig.presentation=page.
 * Same platform-flow-ui runtime as drawer; no FAB / floating panel.
 */
export interface FlowUiPageHostConfig {
    baseUrl?: unknown;
    embedId?: unknown;
    flowId?: unknown;
    branchId?: unknown;
    contextId?: unknown;
    companyId?: unknown;
    voiceBaseUrl?: unknown;
    platformUiOrigin?: unknown;
    credentials?: unknown;
    profile?: unknown;
    theme?: unknown;
    locale?: unknown;
    assistantTitle?: unknown;
    getRequestHeaders?: unknown;
    getExtraMetadataVariables?: unknown;
}

export class FlowUIPageHost extends LitElement {
    declare config: FlowUiPageHostConfig;

    static override properties = {
        config: { attribute: false },
    };

    static override styles = css`
        :host {
            position: fixed;
            inset: 0;
            z-index: 2147483000;
            display: block;
            width: 100vw;
            height: 100dvh;
            background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
            font-family: system-ui;
        }
        platform-flow-ui {
            display: block;
            width: 100%;
            height: 100%;
            min-height: 100%;
        }
    `;

    constructor() {
        super();
        this.config = {};
    }

    override render() {
        const c = this.config;
        if (!c || typeof c !== 'object') {
            throw new Error('flow-ui-page-host: config is required');
        }
        if (typeof c.baseUrl !== 'string' || c.baseUrl.trim() === '') {
            throw new Error('flow-ui-page-host: config.baseUrl is required');
        }
        const companyId = typeof c.companyId === 'string' ? c.companyId : '';
        const voiceBaseUrl = typeof c.voiceBaseUrl === 'string' ? c.voiceBaseUrl : '';
        const platformUiOrigin = typeof c.platformUiOrigin === 'string' ? c.platformUiOrigin.trim().replace(/\/+$/, '') : '';
        if (platformUiOrigin !== '') {
            this.setAttribute('platform-ui-origin', platformUiOrigin);
        }
        let credentials = 'include';
        if (typeof c.credentials === 'string' && c.credentials.trim() !== '') {
            credentials = c.credentials;
        }
        return html`<platform-flow-ui
            embed-id=${typeof c.embedId === 'string' ? c.embedId : ''}
            flow-id=${typeof c.flowId === 'string' ? c.flowId : ''}
            branch-id=${c.branchId || 'default'}
            base-url=${c.baseUrl}
            context-id=${typeof c.contextId === 'string' ? c.contextId : ''}
            company-id=${companyId}
            voice-base-url=${voiceBaseUrl}
            platform-ui-origin=${platformUiOrigin}
            display="page"
            profile=${c.profile || 'embed_public'}
            theme=${c.theme || 'auto'}
            locale=${c.locale || 'ru'}
            credentials=${credentials}
            assistant-title=${typeof c.assistantTitle === 'string' ? c.assistantTitle : ''}
            .getRequestHeaders=${c.getRequestHeaders}
            .getExtraMetadataVariables=${c.getExtraMetadataVariables}
        ></platform-flow-ui>`;
    }
}

if (!customElements.get('flow-ui-page-host')) {
    customElements.define('flow-ui-page-host', FlowUIPageHost);
}
