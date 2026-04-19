/**
 * platform-user-chip — компактное представление пользователя по `user_id`.
 *
 * Источник данных:
 *   - state.auth.user (если userId совпадает с текущим пользователем);
 *   - state.team.members (участники активной компании).
 *
 * Чип сам триггерит загрузку списка участников при первом монтировании, если
 * команда ещё не загружена и пользователь аутентифицирован. Это даёт ровно один
 * GET /api/team/members на сервис, lookup которого закрывает все чипы на странице.
 *
 * Если member не найден (бывший участник, service-account, чужая компания) —
 * чип рендерит сокращённый id с подписью user_chip.unknown и не реагирует на клик.
 *
 * Клик (interactive=true и пользователь найден) открывает core-модалку
 * platform.user_info (см. platform-user-info-modal.js).
 *
 * i18n namespace: 'platform'.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';

const ALLOWED_SIZES = new Set(['sm', 'md']);

export class PlatformUserChip extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        userId: { type: String, attribute: 'user-id' },
        size: { type: String },
        interactive: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2, 8px);
                max-width: 100%;
                min-width: 0;
            }

            .chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2, 8px);
                padding: 2px 8px 2px 2px;
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-full, 999px);
                color: var(--text-primary);
                font: inherit;
                cursor: default;
                max-width: 100%;
                min-width: 0;
                text-align: left;
                transition: background var(--duration-fast, 0.15s) ease,
                            border-color var(--duration-fast, 0.15s) ease;
            }

            .chip.interactive {
                cursor: pointer;
            }

            .chip.interactive:hover,
            .chip.interactive:focus-visible {
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.06));
                border-color: var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                outline: none;
            }

            .avatar {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background: var(--accent-subtle, rgba(99, 102, 241, 0.18));
                color: var(--accent, #6366f1);
                font-size: var(--text-xs, 12px);
                font-weight: var(--font-semibold, 600);
                overflow: hidden;
            }

            .avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                border-radius: 50%;
            }

            .body {
                display: inline-flex;
                flex-direction: column;
                min-width: 0;
                line-height: 1.2;
            }

            .name {
                color: var(--text-primary);
                font-size: var(--text-sm, 14px);
                font-weight: var(--font-medium, 500);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .email {
                color: var(--text-tertiary, rgba(255, 255, 255, 0.55));
                font-size: var(--text-xs, 12px);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .unknown .name {
                color: var(--text-tertiary, rgba(255, 255, 255, 0.55));
                font-style: italic;
            }

            :host([size="md"]) .avatar {
                width: 32px;
                height: 32px;
                font-size: var(--text-sm, 14px);
            }
        `,
    ];

    constructor() {
        super();
        this.userId = '';
        this.size = 'sm';
        this.interactive = true;
        this._teamSel = this.select((s) => s.team);
        this._authSel = this.select((s) => s.auth);
        this._loadDispatched = false;
    }

    updated(changed) {
        super.updated(changed);
        if (!ALLOWED_SIZES.has(this.size)) {
            throw new Error(`platform-user-chip: invalid size "${this.size}" (allowed: sm | md)`);
        }
        const auth = this._authSel.value;
        const team = this._teamSel.value;
        if (
            !this._loadDispatched
            && auth.status === 'authenticated'
            && team.members.length === 0
            && team.loading === false
        ) {
            this._loadDispatched = true;
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    _resolveUser() {
        const userId = this.userId;
        if (typeof userId !== 'string' || userId.length === 0) {
            throw new Error('platform-user-chip: user-id required (non-empty string)');
        }
        const auth = this._authSel.value;
        const currentUser = auth.user;
        if (currentUser) {
            const currentId = (currentUser.raw && currentUser.raw.user_id) || currentUser.id;
            if (currentId === userId) {
                const raw = currentUser.raw || {};
                return {
                    user_id: userId,
                    name: currentUser.name || raw.name || this.t('user_chip.you'),
                    email: Array.isArray(raw.emails) && raw.emails.length > 0 ? raw.emails[0] : null,
                    avatar_url: typeof raw.avatar_url === 'string' && raw.avatar_url.length > 0 ? raw.avatar_url : null,
                    is_self: true,
                };
            }
        }
        const team = this._teamSel.value;
        const member = team.members.find((m) => m.user_id === userId);
        if (member) {
            return {
                user_id: member.user_id,
                name: member.name,
                email: member.email,
                avatar_url: member.avatar_url,
                is_self: false,
            };
        }
        return null;
    }

    _onClick() {
        if (!this.interactive) return;
        const user = this._resolveUser();
        if (!user) return;
        this.openModal('platform.user_info', { userId: user.user_id });
    }

    _onKeydown(event) {
        if (!this.interactive) return;
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this._onClick();
        }
    }

    _renderAvatar(user) {
        if (user.avatar_url) {
            return html`<span class="avatar"><img src=${user.avatar_url} alt=${user.name} /></span>`;
        }
        const letter = user.name && user.name.length > 0 ? user.name.trim().charAt(0).toUpperCase() : '?';
        return html`<span class="avatar">${letter}</span>`;
    }

    render() {
        const user = this._resolveUser();
        if (!user) {
            const shortId = this.userId.length > 12 ? `${this.userId.slice(0, 12)}…` : this.userId;
            return html`
                <span class="chip unknown" title=${this.userId}>
                    <span class="avatar">?</span>
                    <span class="body">
                        <span class="name">${this.t('user_chip.unknown')}</span>
                        <span class="email">${shortId}</span>
                    </span>
                </span>
            `;
        }
        const interactive = this.interactive;
        const showEmail = this.size === 'md' && user.email;
        return html`
            <button
                type="button"
                class=${`chip ${interactive ? 'interactive' : ''}`}
                ?disabled=${!interactive}
                title=${user.name}
                @click=${this._onClick}
                @keydown=${this._onKeydown}
            >
                ${this._renderAvatar(user)}
                <span class="body">
                    <span class="name">${user.name}</span>
                    ${showEmail ? html`<span class="email">${user.email}</span>` : null}
                </span>
            </button>
        `;
    }
}

customElements.define('platform-user-chip', PlatformUserChip);
