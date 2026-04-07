/**
 * IntegrationBadges — плавающие шарики подключённых интеграций.
 *
 * Каждый бейдж — круг с первой буквой service, цвет по provider.
 * Клик открывает popover с названием и кнопкой «Отключить».
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const PROVIDER_COLORS = {
    google: '#4285F4',
    yandex: '#FC3F1D',
};

export class IntegrationBadges extends PlatformElement {
    static properties = {
        _credentials: { state: true },
        _openPopover: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                pointer-events: all;
            }

            .badges {
                display: flex;
                gap: 4px;
                align-items: center;
            }

            .badge {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: 600;
                color: #fff;
                cursor: pointer;
                border: none;
                padding: 0;
                position: relative;
                transition: transform 0.15s ease, box-shadow 0.15s ease;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
            }

            .badge:hover {
                transform: scale(1.15);
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
            }

            .popover-anchor {
                position: relative;
            }

            .popover {
                position: absolute;
                top: calc(100% + 6px);
                right: 0;
                min-width: 180px;
                background: var(--color-bg-primary, #fff);
                border: 1px solid var(--color-border, #e0e0e0);
                border-radius: var(--radius-2, 8px);
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
                padding: var(--space-3, 12px);
                z-index: 100;
                display: flex;
                flex-direction: column;
                gap: var(--space-2, 8px);
            }

            .popover-title {
                font-size: 13px;
                font-weight: 500;
                color: var(--color-text-primary, #333);
            }

            .popover-disconnect {
                background: none;
                border: 1px solid var(--color-danger, #e53935);
                color: var(--color-danger, #e53935);
                border-radius: var(--radius-1, 4px);
                padding: 4px 12px;
                font-size: 12px;
                cursor: pointer;
                transition: background 0.15s ease, color 0.15s ease;
            }

            .popover-disconnect:hover {
                background: var(--color-danger, #e53935);
                color: #fff;
            }
        `,
    ];

    constructor() {
        super();
        this._credentials = [];
        this._openPopover = null;
        this._onClickOutside = this._onClickOutside.bind(this);
        this._onCredentialsChanged = this._onCredentialsChanged.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadCredentials();
        document.addEventListener('click', this._onClickOutside);
        window.addEventListener('integration-credentials-changed', this._onCredentialsChanged);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onClickOutside);
        window.removeEventListener('integration-credentials-changed', this._onCredentialsChanged);
    }

    async _loadCredentials() {
        const items = await this.a2a.listIntegrationCredentials();
        this._credentials = Array.isArray(items) ? items : [];
    }

    _onCredentialsChanged() {
        this._loadCredentials();
    }

    _onClickOutside(e) {
        if (this._openPopover !== null && !e.composedPath().includes(this)) {
            this._openPopover = null;
        }
    }

    _togglePopover(key, e) {
        e.stopPropagation();
        this._openPopover = this._openPopover === key ? null : key;
    }

    async _disconnect(provider, service) {
        await this.a2a.deleteIntegrationCredential(provider, service);
        this._credentials = this._credentials.filter(
            (c) => !(c.provider === provider && c.service === service),
        );
        this._openPopover = null;
    }

    render() {
        if (!this._credentials.length) return nothing;

        return html`
            <div class="badges">
                ${this._credentials.map((c) => {
                    const key = `${c.provider}:${c.service}`;
                    const letter = (c.service || '?')[0].toUpperCase();
                    const bg = PROVIDER_COLORS[c.provider] || 'var(--color-secondary, #666)';
                    const title = this.i18n.t('chat_widget.integration_badge_title', {
                        provider: c.provider,
                        service: c.service,
                    });

                    return html`
                        <div class="popover-anchor">
                            <button
                                class="badge"
                                style="background:${bg}"
                                title="${title}"
                                @click=${(e) => this._togglePopover(key, e)}
                            >
                                ${letter}
                            </button>
                            ${this._openPopover === key
                                ? html`
                                      <div class="popover" @click=${(e) => e.stopPropagation()}>
                                          <div class="popover-title">${c.provider} / ${c.service}</div>
                                          <button
                                              class="popover-disconnect"
                                              @click=${() => this._disconnect(c.provider, c.service)}
                                          >
                                              ${this.i18n.t('chat_widget.integration_disconnect')}
                                          </button>
                                      </div>
                                  `
                                : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('integration-badges', IntegrationBadges);
