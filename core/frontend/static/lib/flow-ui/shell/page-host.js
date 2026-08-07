import { LitElement, css, html } from '../../lit-shim.js';
import '../components/platform-flow-ui.js';

/**
 * Full-viewport embed host for EmbedConfig.presentation=page.
 * Same platform-flow-ui runtime as drawer; no FAB / floating panel.
 */
export class FlowUIPageHost extends LitElement {
    static properties = {
        config: { attribute: false },
    };

    static styles = css`
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

    render() {
        const c = this.config;
        if (!c || typeof c !== 'object') {
            throw new Error('flow-ui-page-host: config is required');
        }
        if (typeof c.baseUrl !== 'string' || c.baseUrl.trim() === '') {
            throw new Error('flow-ui-page-host: config.baseUrl is required');
        }
        return html`<platform-flow-ui
            embed-id=${c.embedId || ''}
            flow-id=${c.flowId || ''}
            branch-id=${c.branchId || 'default'}
            base-url=${c.baseUrl}
            context-id=${c.contextId || ''}
            display="page"
            profile=${c.profile || 'embed_public'}
            theme=${c.theme || 'auto'}
            locale=${c.locale || 'ru'}
            .getRequestHeaders=${c.getRequestHeaders}
        ></platform-flow-ui>`;
    }
}

if (!customElements.get('flow-ui-page-host')) {
    customElements.define('flow-ui-page-host', FlowUIPageHost);
}
