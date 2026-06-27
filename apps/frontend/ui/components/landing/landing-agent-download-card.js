/**
 * Плавающая карточка загрузки HumanitecAgent на лендинге.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import '@platform/lib/components/platform-icon.js';

const DISMISS_STORAGE_KEY = platformStorageKey('frontend', 'landing.agent_download_card.dismissed');

export class LandingAgentDownloadCard extends PlatformElement {
    static i18nNamespace = 'landing';

    static properties = {
        _dismissed: { state: true, type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .shell {
                position: fixed;
                top: calc(132px + var(--platform-safe-top, 0px));
                right: clamp(24px, 3.5vw, 56px);
                z-index: 95;
                width: min(320px, calc(100vw - 48px));
                box-sizing: border-box;
            }

            .card-wrap {
                position: relative;
            }

            .card {
                position: relative;
                display: flex;
                align-items: center;
                gap: 14px;
                width: 100%;
                padding: 14px 36px 14px 14px;
                border-radius: 18px;
                border: 1px solid var(--landing-panel-border-strong, rgba(255, 255, 255, 0.16));
                background:
                    radial-gradient(circle at top right, rgba(87, 104, 254, 0.22), transparent 58%),
                    var(--landing-dropdown-bg, rgba(15, 15, 15, 0.9));
                backdrop-filter: blur(16px);
                box-shadow:
                    var(--landing-elevated-shadow, 0 16px 48px rgba(0, 0, 0, 0.42)),
                    inset 0 1px 0 rgba(255, 255, 255, 0.06);
                color: inherit;
                text-decoration: none;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                box-sizing: border-box;
            }

            .card:hover {
                transform: translateY(-2px);
                border-color: rgba(87, 104, 254, 0.55);
                box-shadow:
                    0 20px 56px rgba(87, 104, 254, 0.18),
                    0 16px 48px rgba(0, 0, 0, 0.42),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
            }

            .close {
                position: absolute;
                top: 8px;
                right: 8px;
                z-index: 2;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                padding: 0;
                border: none;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.08);
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.72));
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .close:hover {
                background: rgba(255, 255, 255, 0.14);
                color: var(--landing-secondary, #e8e8e8);
            }

            .icon-wrap {
                flex: 0 0 auto;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border-radius: 14px;
                background: rgba(87, 104, 254, 0.16);
                border: 1px solid rgba(87, 104, 254, 0.28);
                color: var(--landing-primary, #5768fe);
            }

            .copy {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }

            .title {
                margin: 0;
                font-family: 'Fira Sans', sans-serif;
                font-size: 15px;
                font-weight: 600;
                line-height: 1.25;
                color: var(--landing-secondary, #e8e8e8);
            }

            .subtitle {
                margin: 0;
                font-family: 'Fira Sans', sans-serif;
                font-size: 12px;
                line-height: 1.35;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.68));
            }

            .chevron {
                flex: 0 0 auto;
                color: var(--landing-primary, #5768fe);
                opacity: 0.85;
            }

            @media (max-width: 768px) {
                .shell {
                    top: calc(112px + var(--platform-safe-top, 0px));
                    right: 16px;
                    width: min(280px, calc(100vw - 32px));
                }

                .card {
                    gap: 10px;
                    padding: 12px 34px 12px 12px;
                    border-radius: 16px;
                }

                .close {
                    top: 6px;
                    right: 6px;
                    width: 22px;
                    height: 22px;
                }

                .icon-wrap {
                    width: 38px;
                    height: 38px;
                    border-radius: 12px;
                }

                .title {
                    font-size: 14px;
                }

                .subtitle {
                    font-size: 11px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._dismissed = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window === 'undefined') {
            return;
        }
        this._dismissed = window.localStorage.getItem(DISMISS_STORAGE_KEY) === '1';
    }

    _dismiss(event) {
        event.preventDefault();
        event.stopPropagation();
        this._dismissed = true;
        window.localStorage.setItem(DISMISS_STORAGE_KEY, '1');
    }

    render() {
        if (this._dismissed) {
            return html``;
        }

        return html`
            <div class="shell">
                <div class="card-wrap">
                    <button
                        type="button"
                        class="close"
                        aria-label=${this.t('hero.download_agent_close_aria')}
                        @click=${this._dismiss}
                    >
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                    <a
                        class="card"
                        href="/agent"
                        aria-label=${this.t('hero.download_agent_aria')}
                    >
                        <span class="icon-wrap" aria-hidden="true">
                            <platform-icon name="download" size="20"></platform-icon>
                        </span>
                        <span class="copy">
                            <p class="title">${this.t('hero.download_agent_button')}</p>
                            <p class="subtitle">${this.t('hero.download_agent_subtitle')}</p>
                        </span>
                        <platform-icon class="chevron" name="chevron-right" size="18" aria-hidden="true"></platform-icon>
                    </a>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-agent-download-card', LandingAgentDownloadCard);
