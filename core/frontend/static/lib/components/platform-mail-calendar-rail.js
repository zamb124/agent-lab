/**
 * Общий левый rail почты и календаря: аватары ящиков, switcher Mail/Calendar, settings.
 * Один layout (vertical left) на desktop и mobile — mail и calendar единообразны.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import { MAIL_EVENTS } from '../events/reducers/mail.js';
import { initialsFromName } from '../utils/hash-string.js';
import { resolvePaletteColor } from '../utils/color-palette.js';

export class PlatformMailCalendarRail extends PlatformElement {
    static i18nNamespace = 'mail';

    static properties = {
        surface: { type: String, reflect: true },
        showSettings: { type: Boolean, attribute: 'show-settings' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                align-items: center;
                width: var(--mail-rail-width, 64px);
                min-height: 0;
                padding: var(--space-4) var(--space-2);
                padding-top: max(var(--space-4), env(safe-area-inset-top, 0px));
                gap: var(--space-2);
                background: var(--bg-surface);
                border-right: 1px solid var(--border-subtle);
                box-sizing: border-box;
            }
            .rail-spacer {
                flex: 1;
                min-height: var(--space-2);
            }
            .rail-switch {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-1);
                padding-top: var(--space-2);
                border-top: 1px solid var(--border-subtle);
                width: 100%;
            }
            .rail-btn {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-primary);
                cursor: pointer;
                display: grid;
                place-items: center;
                position: relative;
                font-size: 0.75rem;
                font-weight: 600;
                flex-shrink: 0;
                transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
            }
            .rail-btn:hover {
                background: var(--accent-subtle);
            }
            .rail-btn.surface-active {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .rail-avatar {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: #fff;
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.02em;
            }
            .rail-btn.mailbox-active .rail-avatar {
                box-shadow: 0 0 0 2px var(--bg-surface), 0 0 0 4px var(--accent);
            }
            .rail-role-mark {
                position: absolute;
                right: 4px;
                bottom: 4px;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--accent);
                border: 2px solid var(--bg-surface);
            }
        `,
    ];

    constructor() {
        super();
        this.surface = 'mail';
        this.showSettings = false;
        this._mailSelect = this.select((s) => s.mail);
    }

    _selectMailbox(mailboxBindingId) {
        if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
            throw new Error('platform-mail-calendar-rail: mailbox_binding_id required');
        }
        this.dispatch(MAIL_EVENTS.MAILBOX_SELECT, { mailbox_binding_id: mailboxBindingId });
    }

    _switchSurface(nextSurface) {
        if (nextSurface !== 'mail' && nextSurface !== 'calendar') {
            throw new Error(`platform-mail-calendar-rail: unknown surface=${nextSurface}`);
        }
        if (nextSurface === this.surface) {
            return;
        }
        const nextKind = nextSurface === 'mail' ? 'platform.mail' : 'platform.calendar';
        // Мгновенная замена пары поверхностей — без close/open exit+enter (мерцание).
        this.openModal(nextKind, {}, {
            replaceKinds: ['platform.mail', 'platform.calendar'],
            skipEnterMotion: true,
        });
    }

    _onSettingsClick() {
        this.dispatchEvent(new CustomEvent('settings-click', { bubbles: true, composed: true }));
    }

    _avatarColor(binding) {
        const key = typeof binding.calendar_color === 'string' && binding.calendar_color.trim()
            ? binding.calendar_color.trim()
            : 'default';
        return resolvePaletteColor(key);
    }

    connectedCallback() {
        super.connectedCallback();
        this.setAttribute('role', 'navigation');
        this.setAttribute('aria-label', this.t('title'));
    }

    render() {
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail.bindings) ? mail.bindings : [];
        return html`
            ${bindings.map((binding) => {
                const initials = initialsFromName(binding.local_part);
                const active = binding.mailbox_binding_id === mail.activeMailboxBindingId;
                const bg = this._avatarColor(binding);
                const isRole = binding.kind === 'role';
                const title = isRole
                    ? `${binding.email_address} (${this.t('binding_kind_role')})`
                    : binding.email_address;
                return html`
                    <button
                        class="rail-btn ${active ? 'mailbox-active' : ''}"
                        type="button"
                        title=${title}
                        @click=${() => this._selectMailbox(binding.mailbox_binding_id)}
                    >
                        <span class="rail-avatar" style="background: ${bg};">${initials}</span>
                        ${isRole ? html`<span class="rail-role-mark" aria-hidden="true"></span>` : nothing}
                    </button>
                `;
            })}
            <div class="rail-switch">
                <button
                    class="rail-btn ${this.surface === 'mail' ? 'surface-active' : ''}"
                    type="button"
                    title=${this.t('rail_mail')}
                    aria-label=${this.t('rail_mail')}
                    @click=${() => this._switchSurface('mail')}
                >
                    <platform-icon name="mail" size="18"></platform-icon>
                </button>
                <button
                    class="rail-btn ${this.surface === 'calendar' ? 'surface-active' : ''}"
                    type="button"
                    title=${this.t('rail_calendar')}
                    aria-label=${this.t('rail_calendar')}
                    @click=${() => this._switchSurface('calendar')}
                >
                    <platform-icon name="calendar" size="18"></platform-icon>
                </button>
            </div>
            ${this.showSettings
                ? html`
                    <button
                        class="rail-btn"
                        type="button"
                        title=${this.t('settings')}
                        @click=${() => this._onSettingsClick()}
                    >
                        <platform-icon name="settings" size="18"></platform-icon>
                    </button>
                `
                : nothing}
            <div class="rail-spacer"></div>
        `;
    }
}

customElements.define('platform-mail-calendar-rail', PlatformMailCalendarRail);
