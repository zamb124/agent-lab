import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { resolveNonEmptyString } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/platform-button.js';
import '../components/sync-chat-header.js';

/**
 * sync-calls-scheduled-page — список запланированных встреч.
 *
 * `sync/call_links_scheduled` — WS createAsyncOp (см. calls.resource.js), поэтому используем
 * `useOp().run()` и читаем `lastResult` напрямую. На `connectedCallback` и на каждый
 * `WS_CONNECTED` дёргаем повторно (как `autoload` ресурса).
 */
export class SyncCallsScheduledPage extends PlatformPage {
    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            height: 100%;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: var(--space-4);
        }
        .actions-row {
            display: flex;
            justify-content: flex-end;
            margin-bottom: var(--space-3);
        }
        ul { list-style: none; padding: 0; margin: 0; }
        .item {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2);
            border-radius: var(--radius-sm);
            cursor: pointer;
        }
        .item:hover { background: var(--glass-hover); }
        .item .meta { color: var(--text-secondary); font-size: var(--text-xs); margin-left: auto; }
    `;

    constructor() {
        super();
        this._linksOp = this.useOp('sync/call_links_scheduled');
        this.useEvent('sync/call_links_scheduled/succeeded', () => this.requestUpdate());
        this.useEvent('sync/call_link_create/succeeded', () => { this._linksOp.run(this._defaultRangePayload()); });
        this.useEvent('sync/call_link_update/succeeded', () => { this._linksOp.run(this._defaultRangePayload()); });
        this.useEvent('sync/call_link_remove/succeeded', () => { this._linksOp.run(this._defaultRangePayload()); });
    }

    connectedCallback() {
        super.connectedCallback();
        this._linksOp.run(this._defaultRangePayload());
    }

    /**
     * CallsLinksListPayload требует обязательные start_at/end_at.
     * Окно: −30 дней .. +365 дней от now (UTC ISO). Этого хватает для отображения
     * прошедших и грядущих встреч на одном экране. При появлении фильтров (например,
     * «месяц») этот метод станет параметризованным.
     */
    _defaultRangePayload() {
        const now = Date.now();
        const start_at = new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString();
        const end_at = new Date(now + 365 * 24 * 60 * 60 * 1000).toISOString();
        return { start_at, end_at, limit: 200, offset: 0 };
    }

    _resolveItems() {
        const result = this._linksOp.lastResult;
        if (Array.isArray(result)) return result;
        if (result && Array.isArray(result.items)) return result.items;
        return [];
    }

    _onCreate() {
        this.openModal('sync.call_link_create', null);
    }

    _onEdit(linkToken) {
        this.openModal('sync.call_link_edit', { linkToken });
    }

    _formatScheduledAt(link) {
        const raw = typeof link.scheduled_start_at === 'string'
            ? link.scheduled_start_at
            : (typeof link.scheduled_at === 'string' ? link.scheduled_at : '');
        if (raw === '') return '';
        const d = new Date(raw);
        if (Number.isNaN(d.getTime())) return '';
        return d.toLocaleString();
    }

    render() {
        const items = this._resolveItems();
        return html`
            <sync-chat-header
                header-mode="list"
                .listTitle=${this.t('calls_scheduled.title')}
                .listSubtitle=${''}
            ></sync-chat-header>
            <div class="body">
                <div class="actions-row">
                    <platform-button variant="primary" @click=${this._onCreate}>${this.t('calls_scheduled.action_create')}</platform-button>
                </div>
                ${items.length === 0 ? html`
                    <p style="color: var(--text-secondary);">${this.t('calls_scheduled.empty')}</p>
                ` : html`
                    <ul>
                        ${items.map((link) => html`
                            <li class="item" @click=${() => this._onEdit(link.link_token)}>
                                <span>${resolveNonEmptyString(link.title, link.link_token)}</span>
                                <span class="meta">${this._formatScheduledAt(link)}</span>
                            </li>
                        `)}
                    </ul>
                `}
            </div>
        `;
    }
}

customElements.define('sync-calls-scheduled-page', SyncCallsScheduledPage);
