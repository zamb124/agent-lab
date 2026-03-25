/**
 * Строка канала: аватар, название, тип, превью последнего сообщения — как в сайдбаре.
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';

export class SyncChannelRow extends PlatformElement {
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

            button.nav-item.nav-item--mention:not(.active) {
                border-color: rgba(234, 179, 8, 0.45);
                background: rgba(234, 179, 8, 0.12);
            }

            :host([in-nav-wrap]) button.nav-item.nav-item--mention:not(.active) {
                box-shadow: inset 3px 0 0 rgba(234, 179, 8, 0.85);
            }

            /* Внутри .nav-row-wrap сайдбара фон и рамка только у обёртки, не у кнопки */
            :host([in-nav-wrap]) button.nav-item {
                border: none;
            }

            :host([in-nav-wrap]) button.nav-item:hover {
                background: transparent;
                border-color: transparent;
                color: var(--text-primary);
            }

            :host([in-nav-wrap]) button.nav-item.active {
                background: transparent;
                border-color: transparent;
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
            :host([icon-only]) .nav-item-preview,
            :host([icon-only]) .nav-item-type {
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

            .nav-item-type {
                font-size: 10px;
                color: var(--text-tertiary);
                flex-shrink: 0;
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

            .entity-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                flex-shrink: 0;
                object-fit: cover;
            }

            .entity-avatar-initials {
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
        channel: { type: Object },
        active: { type: Boolean },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
        inNavRowWrap: { type: Boolean, attribute: 'in-nav-wrap', reflect: true },
    };

    constructor() {
        super();
        this.channel = null;
        this.active = false;
        this.iconOnly = false;
        this.inNavRowWrap = false;
    }

    _channelAvatar(ch) {
        if (ch.type === 'direct' && ch.peer) {
            const p = ch.peer;
            if (typeof p.avatar_url === 'string' && p.avatar_url !== '') {
                return html`<img class="entity-avatar" src=${p.avatar_url} alt="" />`;
            }
            const title = SyncStore.channelDisplayTitle(ch);
            const initial = (title.trim().slice(0, 1) || '?').toUpperCase();
            const hue = hueFromString(p.user_id);
            return html`
                <span class="entity-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
            `;
        }
        const url = ch.avatar_url;
        if (typeof url === 'string' && url !== '') {
            return html`<img class="entity-avatar" src=${url} alt="" />`;
        }
        const label = SyncStore.channelDisplayTitle(ch);
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = hueFromString(ch.id);
        return html`
            <span class="entity-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    _rowMeta(ch) {
        if (!ch) {
            return { preview: '', unread: 0 };
        }
        const preview = typeof ch.last_message_preview === 'string' ? ch.last_message_preview : '';
        const unread = typeof ch.unread_count === 'number' ? ch.unread_count : 0;
        return { preview, unread };
    }

    _rowSecondary(ch, rowMeta) {
        const myId = this.auth?.user?.id;
        if (typeof myId === 'string' && myId !== '') {
            const typingLine = SyncStore.getTypingIndicatorLine(ch.id, null, myId);
            if (typingLine !== '') {
                return { text: typingLine, isTyping: true };
            }
        }
        const preview = typeof rowMeta.preview === 'string' ? rowMeta.preview : '';
        return { text: preview, isTyping: false };
    }

    render() {
        const ch = this.channel;
        if (!ch) {
            return html``;
        }
        const rowMeta = this._rowMeta(ch);
        const sec = this._rowSecondary(ch, rowMeta);
        const title = SyncStore.channelDisplayTitle(ch);
        const mentionUnread =
            typeof ch.mention_unread_count === 'number' ? ch.mention_unread_count : 0;
        const btnClass = classMap({
            'nav-item': true,
            active: this.active,
            'nav-item--mention': mentionUnread > 0,
        });
        return html`
            <button type="button" class=${btnClass}>
                <div class="nav-item-main">
                    ${this._channelAvatar(ch)}
                    <div class="nav-item-inner">
                        <div class="nav-item-title-row">
                            <span class="nav-item-label">${title}</span>
                            <span class="nav-item-type">${SyncStore.channelRowMetaLabel(ch)}</span>
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

customElements.define('sync-channel-row', SyncChannelRow);
