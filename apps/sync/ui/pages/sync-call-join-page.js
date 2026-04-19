/**
 * sync-call-join-page — гостевая страница входа в звонок по ссылке.
 *
 * REST-only (transport: 'http' факторов call_join_*) — гостевой WS не нужен,
 * страница работает без cookie auth. После accept'а — открывает
 * sync.call_overlay модалку с гостевыми токенами LiveKit.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/platform-button.js';

export class SyncCallJoinPage extends PlatformPage {
    static properties = {
        linkToken: { type: String },
        _guestName: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            padding: var(--space-6);
        }
        .card { max-width: 420px; width: 100%; padding: var(--space-4); }
        h2 { margin: 0 0 var(--space-3); }
        input { width: 100%; padding: var(--space-2); margin: var(--space-2) 0; border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-solid); color: var(--text-primary); }
    `;

    constructor() {
        super();
        this.linkToken = '';
        this._guestName = '';
        this._infoOp = this.useOp('sync/call_join_info');
        this._acceptOp = this.useOp('sync/call_join_accept');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('linkToken') && this.linkToken && !this._infoOp.lastResult) {
            this._infoOp.run({ link_token: this.linkToken });
        }
    }

    async _onJoin() {
        await this._acceptOp.run({
            link_token: this.linkToken,
            guest_name: this._guestName.trim(),
        });
        const accepted = this._acceptOp.lastResult;
        if (!accepted || !accepted.call_id) return;
        const callType = (typeof accepted.call_type === 'string' && accepted.call_type !== '')
            ? accepted.call_type
            : 'video';
        this.openModal('sync.call_overlay', {
            callId: accepted.call_id,
            callType,
            channelId: '',
        });
    }

    _resolveTitle(info) {
        if (info && typeof info.title === 'string' && info.title !== '') return info.title;
        return this.t('call_join.title');
    }

    render() {
        const info = this._infoOp.lastResult;
        const title = this._resolveTitle(info);
        return html`
            <glass-card class="card">
                <h2>${title}</h2>
                <input
                    placeholder=${this.t('call_join.guest_name_placeholder')}
                    .value=${this._guestName}
                    @input=${(e) => { this._guestName = e.target.value; }}
                />
                <platform-button variant="primary" @click=${this._onJoin}>
                    ${this.t('call_join.action_join')}
                </platform-button>
            </glass-card>
        `;
    }
}

customElements.define('sync-call-join-page', SyncCallJoinPage);
