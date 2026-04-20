/**
 * sync-call-incoming-modal — баннер входящего звонка (фикс. позиция в углу).
 *
 * Не диалог поверх scrim'а: появляется как уведомление в верхнем правом углу
 * экрана. Управляется stack'ом модалок (kind = 'sync.call_incoming'), но
 * визуально — overlay-баннер, поэтому базовый класс PlatformElement, а не
 * PlatformModal.
 *
 * Контракт со стеком: stack ставит `_modalId`, `_modalKind`, props и
 * `open = true`; close() диспатчит UI_MODAL_CLOSE с `_modalId`, reducer
 * убирает запись и stack снимает элемент из DOM.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';

export class SyncCallIncomingModal extends PlatformElement {
    static modalKind = 'sync.call_incoming';
    static i18nNamespace = 'sync';

    static properties = {
        open: { type: Boolean, reflect: true },
        callId: { type: String },
        callType: { type: String },
        channelId: { type: String },
        callerUserId: { type: String },
        callerDisplayName: { type: String },
        channelDisplayName: { type: String },
    };

    static styles = css`
        :host {
            position: fixed;
            top: var(--space-4);
            right: var(--space-4);
            z-index: 9999;
            display: none;
        }
        :host([open]) { display: block; }
        .card {
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            padding: var(--space-4);
            min-width: 320px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }
        .head { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
        .meta { color: var(--text-secondary); font-size: var(--text-xs); margin-bottom: var(--space-3); }
        .actions { display: flex; gap: var(--space-2); }
        .accept { background: #10b981; color: white; }
        .decline { background: var(--color-danger, #ef4444); color: white; }
    `;

    constructor() {
        super();
        this.callId = '';
        this.callType = 'video';
        this.channelId = '';
        this.callerUserId = '';
        this.callerDisplayName = '';
        this.channelDisplayName = '';
        this._modalId = '';
        this._modalKind = '';
        this._accept = this.useOp('sync/calls_accept');
        this._decline = this.useOp('sync/calls_decline');
    }

    connectedCallback() {
        super.connectedCallback();
        this._ringtone = new Audio('/static/core/assets/sounds/call-ringtone.mp3');
        this._ringtone.loop = true;
        this._ringtone.play().catch(() => { /* requires user gesture, swallow */ });
    }

    disconnectedCallback() {
        if (this._ringtone) {
            this._ringtone.pause();
            this._ringtone = null;
        }
        super.disconnectedCallback();
    }

    close() {
        if (typeof this._modalId !== 'string' || this._modalId.length === 0) {
            throw new Error('SyncCallIncomingModal.close: _modalId is required');
        }
        this.closeModal({ id: this._modalId });
    }

    async _onAccept() {
        if (!this.callId) return;
        await this._accept.run({ call_id: this.callId });
        this.dispatch('sync/call_ui/incoming_dismissed', null);
        this.dispatch('sync/call_ui/overlay_opened', {
            call_id: this.callId,
            call_type: this.callType,
            channel_id: this.channelId,
        });
        this.close();
    }

    async _onDecline() {
        if (!this.callId) return;
        await this._decline.run({ call_id: this.callId });
        this.dispatch('sync/call_ui/incoming_dismissed', null);
        this.close();
    }

    _resolveCallerName() {
        if (typeof this.callerDisplayName === 'string' && this.callerDisplayName !== '') return this.callerDisplayName;
        if (typeof this.callerUserId === 'string' && this.callerUserId !== '') return this.callerUserId;
        return this.t('call_incoming.unknown_caller');
    }

    render() {
        const callerName = this._resolveCallerName();
        const channelLabel = typeof this.channelDisplayName === 'string' ? this.channelDisplayName : '';
        return html`
            <div class="card">
                <div class="head">
                    ${this.callerUserId ? html`
                        <platform-user-chip user-id=${this.callerUserId} size="md" ?interactive=${false}></platform-user-chip>
                    ` : html`<platform-icon name="user" size="32"></platform-icon>`}
                    <div>
                        <div style="font-weight: 600;">${callerName}</div>
                        <div class="meta">${channelLabel}</div>
                    </div>
                </div>
                <div class="meta">${this.t('call_incoming.subtitle')}</div>
                <div class="actions">
                    <platform-button class="decline" @click=${this._onDecline}>
                        ${this.t('call_incoming.action_decline')}
                    </platform-button>
                    <platform-button class="accept" @click=${this._onAccept}>
                        ${this.t('call_incoming.action_accept')}
                    </platform-button>
                </div>
            </div>
        `;
    }
}

customElements.define('sync-call-incoming-modal', SyncCallIncomingModal);
registerModalKind(SyncCallIncomingModal.modalKind, 'sync-call-incoming-modal');
