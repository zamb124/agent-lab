/**
 * flows-browser-preview-modal — интерактивный viewer browser tool прямо внутри Flows UI.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

function asString(value: unknown) {
    return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function withThemeParam(rawUrl: any, theme: any) {
    const value = theme === 'light' ? 'light' : 'dark';
    const url = new URL(rawUrl, window.location.href);
    url.searchParams.set('theme', value);
    return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : url.toString();
}

export class FlowsBrowserPreviewModal extends PlatformModal {
    static modalKind = 'flows.browser_preview';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        viewerUrl: { type: String },
        sessionId: { type: String },
        currentUrl: { type: String },
        status: { type: String },
    }
    declare viewerUrl: string;
    declare sessionId: string;
    declare currentUrl: string;
    declare status: string;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            :host .modal.full .modal-content,
            :host .modal.fullscreen .modal-content {
                display: flex;
                flex-direction: column;
                min-height: 0;
                padding: 0;
                overflow: hidden;
            }

            :host .modal.full .modal-actions,
            :host .modal.fullscreen .modal-actions {
                display: none;
            }

            .browser-preview-frame {
                flex: 1 1 auto;
                width: 100%;
                min-height: min(760px, calc(100vh - 148px));
                border: 0;
                background: var(--bg-primary);
            }

            :host-context([data-theme="light"]) .browser-preview-frame {
                background: var(--bg-elevated);
            }

            .browser-preview-empty {
                flex: 1 1 auto;
                min-height: 360px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }

            .browser-preview-meta {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .browser-preview-meta platform-icon {
                color: var(--accent);
                flex-shrink: 0;
            }
        `,
    ];
    private _themeSel: SelectController<any>;
    private _onPreviewMessage: any;

    constructor() {
        super();
        this.size = 'full';
        this.viewerUrl = '';
        this.sessionId = '';
        this.currentUrl = '';
        this.status = '';
        this._themeSel = this.select((s) => (s.theme && (s.theme as Record<string, any>).mode === 'light' ? 'light' : 'dark'));
        this._onPreviewMessage = (event: Event) => {
            if ((event as Record<string, any>).origin !== window.location.origin) return;
            const payload = (event as Record<string, any>).data;
            if (!payload || typeof payload !== 'object') return;
            if (payload.type !== 'flows.browser_preview.finished') return;
            const finishedSessionId = typeof payload.sessionId === 'string' ? payload.sessionId : '';
            if (finishedSessionId !== '' && this.sessionId !== '' && finishedSessionId !== this.sessionId) {
                return;
            }
            this.close();
        };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        window.addEventListener('message', this._onPreviewMessage);
    }

    override disconnectedCallback(): void {
        window.removeEventListener('message', this._onPreviewMessage);
        super.disconnectedCallback();
    }

    override renderHeader() {
        return html`
            <span class="browser-preview-meta">
                <platform-icon name="monitor" size="18"></platform-icon>
                <span>${this.t('browser_preview_modal.title')}</span>
            </span>
        `;
    }

    override renderBody() {
        const viewerUrl = asString(this.viewerUrl);
        if (viewerUrl.length === 0) {
            return html`<div class="browser-preview-empty">${this.t('browser_preview_modal.empty_url')}</div>`;
        }
        const currentUrl = asString(this.currentUrl);
        const themedViewerUrl = withThemeParam(viewerUrl, this._themeSel.value);
        const title = currentUrl.length > 0
            ? this.t('browser_preview_modal.frame_title_with_url', { url: currentUrl })
            : this.t('browser_preview_modal.frame_title');
        return html`
            <iframe
                class="browser-preview-frame"
                src=${themedViewerUrl}
                title=${title}
                referrerpolicy="no-referrer"
                allow="clipboard-read; clipboard-write"
            ></iframe>
        `;
    }

    override renderFooter() {
        return nothing;
    }
}

customElements.define('flows-browser-preview-modal', FlowsBrowserPreviewModal);
registerModalKind(FlowsBrowserPreviewModal.modalKind, 'flows-browser-preview-modal');
