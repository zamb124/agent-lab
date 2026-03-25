/**
 * Строка участника компании для открытия DM: аватар, онлайн-точка, превью / печатает / presence.
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';

export class SyncDirectMemberRow extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }

            button.nav-item {
                position: relative;
                box-sizing: border-box;
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                cursor: pointer;
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                width: 100%;
                text-align: left;
                transition: all var(--duration-fast);
                margin-bottom: 0;
            }

            button.nav-item:hover {
                background: var(--glass-solid-subtle);
                border-color: var(--glass-border-subtle);
                color: var(--text-primary);
            }

            button.nav-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            :host([icon-only]) button.nav-item {
                justify-content: center;
                align-items: center;
                padding: var(--space-2) var(--space-1);
            }

            :host([icon-only]) .nav-item-main {
                flex: 0 0 auto;
                min-width: 0;
            }

            :host([icon-only]) .nav-item-inner,
            :host([icon-only]) .nav-item-label,
            :host([icon-only]) .nav-item-preview {
                display: none !important;
            }

            :host([icon-only]) .nav-item-unread {
                position: absolute;
                top: 4px;
                right: 4px;
                min-width: 8px;
                min-height: 8px;
                width: 8px;
                height: 8px;
                padding: 0;
                font-size: 0;
                border-radius: 50%;
                margin: 0;
            }

            .nav-item-label {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }

            .nav-item-inner {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .nav-item-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .nav-item-preview {
                font-size: 11px;
                color: var(--text-tertiary);
                line-height: 1.3;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .nav-item-preview.is-typing {
                color: var(--accent);
            }

            .nav-item-unread {
                font-size: 11px;
                font-weight: var(--font-semibold);
                color: #fff;
                background: var(--accent);
                border-radius: var(--radius-full);
                min-width: 18px;
                padding: 1px 6px;
                text-align: center;
                flex-shrink: 0;
                margin-left: auto;
                align-self: flex-start;
            }

            .avatar-wrap {
                position: relative;
                flex-shrink: 0;
                width: 28px;
                height: 28px;
            }

            .peer-online-dot {
                position: absolute;
                bottom: 0;
                right: 0;
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: #22c55e;
                border: 2px solid var(--glass-solid-strong);
                box-sizing: border-box;
            }

            .peer-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                object-fit: cover;
            }

            .peer-avatar-initials {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: var(--font-semibold);
                color: #fff;
            }

            .nav-item-main {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
            }
        `,
    ];

    static properties = {
        member: { type: Object },
        active: { type: Boolean },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
        _peerPresenceByUserId: { state: true },
        _typingPeersByChannel: { state: true },
    };

    constructor() {
        super();
        this.member = null;
        this.active = false;
        this.iconOnly = false;
        const s = SyncStore.state;
        this._peerPresenceByUserId = s.peerPresenceByUserId ?? {};
        this._typingPeersByChannel = s.typingPeersByChannel ?? {};
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe((state) => {
            this._peerPresenceByUserId = state.peerPresenceByUserId ?? {};
            this._typingPeersByChannel = state.typingPeersByChannel ?? {};
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _peerOnline(userId) {
        if (typeof userId !== 'string' || userId === '') return false;
        const row = (this._peerPresenceByUserId ?? {})[userId];
        return !!(row && row.online);
    }

    _memberAvatar(member) {
        if (member.avatar_url) {
            return html`<img class="peer-avatar" src=${member.avatar_url} alt="" />`;
        }
        const label = typeof member.name === 'string' ? member.name : member.user_id;
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = hueFromString(member.user_id);
        return html`
            <span class="peer-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    _memberAvatarBlock(member) {
        const inner = this._memberAvatar(member);
        const on = this._peerOnline(member.user_id);
        return html`
            <div class="avatar-wrap">
                ${inner}
                ${on ? html`<span class="peer-online-dot" title="Онлайн" aria-hidden="true"></span>` : ''}
            </div>
        `;
    }

    _channelRowMeta(channel) {
        if (!channel) {
            return { preview: '', unread: 0 };
        }
        const preview = typeof channel.last_message_preview === 'string' ? channel.last_message_preview : '';
        const unread = typeof channel.unread_count === 'number' ? channel.unread_count : 0;
        return { preview, unread };
    }

    _directRowSecondary(member, dmCh, rowMeta) {
        const myId = ServiceRegistry.auth?.user?.id;
        if (typeof myId === 'string' && myId !== '' && dmCh) {
            const typingLine = SyncStore.getTypingIndicatorLine(dmCh.id, null, myId);
            if (typingLine !== '') {
                return { text: typingLine, isTyping: true };
            }
        }
        const preview = typeof rowMeta.preview === 'string' ? rowMeta.preview : '';
        if (preview !== '') {
            return { text: preview, isTyping: false };
        }
        return { text: SyncStore.getPeerPresenceSubtitle(member.user_id), isTyping: false };
    }

    render() {
        const member = this.member;
        if (!member) {
            return html``;
        }
        const dmCh = SyncStore.findDirectChannelForPeer(member.user_id);
        const rowMeta = this._channelRowMeta(dmCh);
        const sec = this._directRowSecondary(member, dmCh, rowMeta);
        const displayName = typeof member.name === 'string' && member.name !== '' ? member.name : member.user_id;
        const btnClass = classMap({
            'nav-item': true,
            active: this.active,
        });
        return html`
            <button type="button" class=${btnClass}>
                <div class="nav-item-main">
                    ${this._memberAvatarBlock(member)}
                    <div class="nav-item-inner">
                        <div class="nav-item-title-row">
                            <span class="nav-item-label">${displayName}</span>
                        </div>
                        ${sec.text
                            ? html`<span class="nav-item-preview ${sec.isTyping ? 'is-typing' : ''}">${sec.text}</span>`
                            : ''}
                    </div>
                </div>
                ${rowMeta.unread > 0 ? html`<span class="nav-item-unread">${rowMeta.unread}</span>` : ''}
            </button>
        `;
    }
}

customElements.define('sync-direct-member-row', SyncDirectMemberRow);
