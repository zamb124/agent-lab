/**
 * sync-chat-header — шапка чата.
 *
 * Источники: useResource('sync/channels'), useResource('sync/presence'),
 * useResource('sync/call_ui') (для свёрнутого баннера активного звонка).
 *
 * Действия: invite call, открыть members-modal, settings-modal.
 * Mobile: кнопка sidebar (UI_SIDEBAR_OPEN_REQUESTED).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { buildChatSubtitle, channelDisplayTitle } from './_helpers/sync-channel-display.js';

export class SyncChatHeader extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: var(--space-3) var(--space-4);
            border-bottom: 1px solid var(--glass-border);
            background: var(--glass-solid);
            min-height: 56px;
        }
        .menu-btn {
            display: none;
            background: transparent;
            border: none;
            color: var(--text-primary);
            padding: var(--space-1);
            cursor: pointer;
        }
        @media (max-width: 767px) {
            .menu-btn { display: inline-flex; }
        }
        .text {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-width: 0;
        }
        .title {
            font-weight: 600;
            font-size: var(--text-base);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .subtitle {
            font-size: var(--text-xs);
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .actions {
            display: flex;
            align-items: center;
            gap: var(--space-2);
        }
        .call-banner {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-1) var(--space-3);
            background: var(--accent);
            color: white;
            border-radius: var(--radius-md);
            cursor: pointer;
            font-size: var(--text-sm);
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._channels = this.useResource('sync/channels', { autoload: true });
        this._presenceSel = this.select((s) => s.syncPresence);
        this._callUiSel = this.select((s) => s.syncCallUi);
        this._callInvite = this.useOp('sync/calls_invite');
    }

    _onMenuClick() {
        this.openSidebar();
    }

    _onInviteCall() {
        if (!this.channelId) return;
        this._callInvite.run({ body: { channel_id: this.channelId } });
    }

    _onMembers() {
        if (!this.channelId) return;
        this.openModal('sync.channel_members_add', { channelId: this.channelId });
    }

    _onSettings() {
        if (!this.channelId) return;
        this.openModal('sync.channel_edit', { channelId: this.channelId });
    }

    _onExpandCall() {
        this.dispatch('sync/call_ui/overlay_expanded', null);
    }

    render() {
        const channel = this._channels.byId[this.channelId];
        if (!channel) {
            return html`<div class="text"><div class="title">${this.channelId}</div></div>`;
        }
        const presence = this._presenceSel.value;
        const typingByChannel = (presence && presence.typingByChannel) ? presence.typingByChannel : null;
        const presenceByUserId = (presence && presence.presenceByUserId) ? presence.presenceByUserId : null;
        const callUi = this._callUiSel.value;
        const title = channelDisplayTitle(channel);
        const subtitle = buildChatSubtitle({
            channel,
            typingByChannel,
            presenceByUserId,
            t: (k, vars) => this.t(k, vars),
        });
        const callMinimizedHere = Boolean(
            callUi && callUi.activeCall
            && callUi.activeCall.channel_id === this.channelId
            && callUi.overlayMinimized
        );
        return html`
            <button class="menu-btn" @click=${this._onMenuClick} title=${this.t('chat_header.menu')}>
                <platform-icon name="menu" size="20"></platform-icon>
            </button>
            <div class="text">
                <div class="title">${title}</div>
                ${subtitle ? html`<div class="subtitle">${subtitle}</div>` : ''}
            </div>
            <div class="actions">
                ${callMinimizedHere ? html`
                    <span class="call-banner" @click=${this._onExpandCall}>
                        <platform-icon name="phone" size="14"></platform-icon>
                        ${this.t('chat_header.call_minimized')}
                    </span>
                ` : ''}
                <platform-button variant="ghost" @click=${this._onInviteCall} title=${this.t('chat_header.action_call')}>
                    <platform-icon name="phone" size="18"></platform-icon>
                </platform-button>
                <platform-button variant="ghost" @click=${this._onMembers} title=${this.t('chat_header.action_members')}>
                    <platform-icon name="users" size="18"></platform-icon>
                </platform-button>
                <platform-button variant="ghost" @click=${this._onSettings} title=${this.t('chat_header.action_settings')}>
                    <platform-icon name="settings" size="18"></platform-icon>
                </platform-button>
            </div>
        `;
    }
}

customElements.define('sync-chat-header', SyncChatHeader);
