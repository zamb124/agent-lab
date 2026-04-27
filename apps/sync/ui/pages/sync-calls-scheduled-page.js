import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { resolveNonEmptyString } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/platform-button.js';
import '../components/sync-chat-header.js';

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
        this._links = this.useResource('sync/call_links_scheduled', { autoload: true });
    }

    _onCreate() {
        this.openModal('sync.call_link_create', null);
    }

    _onEdit(linkToken) {
        this.openModal('sync.call_link_edit', { linkToken });
    }

    render() {
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
                ${this._links.items.length === 0 ? html`
                    <p style="color: var(--text-secondary);">${this.t('calls_scheduled.empty')}</p>
                ` : html`
                    <ul>
                        ${this._links.items.map((link) => html`
                            <li class="item" @click=${() => this._onEdit(link.link_token)}>
                                <span>${resolveNonEmptyString(link.title, link.link_token)}</span>
                                <span class="meta">${link.scheduled_at ? new Date(link.scheduled_at).toLocaleString() : ''}</span>
                            </li>
                        `)}
                    </ul>
                `}
            </div>
        `;
    }
}

customElements.define('sync-calls-scheduled-page', SyncCallsScheduledPage);
