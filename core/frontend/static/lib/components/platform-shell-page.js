/**
 * Полноэкранные страницы: 404 и ошибка сервера (единый glass-стиль платформы).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-button.js';

export class PlatformShellPage extends PlatformElement {
    static properties = {
        kind: { type: String },
        homeHref: { type: String, attribute: 'home-href' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: var(--app-vh, 100vh);
                width: 100%;
                padding: max(var(--space-6, 24px), env(safe-area-inset-top, 0px))
                    max(var(--space-6, 24px), env(safe-area-inset-right, 0px))
                    max(var(--space-6, 24px), env(safe-area-inset-bottom, 0px))
                    max(var(--space-6, 24px), env(safe-area-inset-left, 0px));
                box-sizing: border-box;
                background: var(--bg-gradient, linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%));
            }

            .panel {
                position: relative;
                width: 100%;
                max-width: 440px;
                padding: var(--space-8, 32px);
                border-radius: var(--radius-2xl, 24px);
                background: var(--glass-solid-medium, rgba(255, 255, 255, 0.06));
                border: 1px solid var(--glass-border-medium, rgba(255, 255, 255, 0.12));
                backdrop-filter: blur(var(--glass-blur-strong, 20px));
                -webkit-backdrop-filter: blur(var(--glass-blur-strong, 20px));
                box-shadow: var(--glass-shadow-medium, 0 8px 32px rgba(0, 0, 0, 0.35)),
                    var(--glass-inner-glow-subtle, inset 0 1px 0 rgba(255, 255, 255, 0.06));
                text-align: center;
            }

            .code {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 4rem;
                font-weight: 700;
                line-height: 1;
                margin: 0 0 var(--space-4, 16px);
                color: var(--accent);
                text-shadow: 0 0 40px rgba(153, 166, 249, 0.35);
            }

            h1 {
                margin: 0 0 var(--space-3, 12px);
                font-size: var(--text-xl, 1.25rem);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
            }

            p {
                margin: 0 0 var(--space-6, 24px);
                font-size: var(--text-sm, 0.875rem);
                line-height: 1.55;
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3, 12px);
                justify-content: center;
            }
        `,
    ];

    constructor() {
        super();
        this.kind = 'not-found';
        this.homeHref = '/';
    }

    render() {
        const is500 = this.kind === 'server-error';
        const title = is500 ? 'Сервис временно недоступен' : 'Страница не найдена';
        const text = is500
            ? 'Не удалось связаться с сервером. Попробуйте обновить страницу или зайти позже.'
            : 'Такого адреса на платформе нет. Проверьте ссылку или вернитесь на главную.';
        const code = is500 ? '500' : '404';

        return html`
            <div class="panel">
                <div class="code">${code}</div>
                <h1>${title}</h1>
                <p>${text}</p>
                <div class="actions">
                    <platform-button variant="primary" @click=${() => this._goHome()}>
                        На главную
                    </platform-button>
                    ${!is500
                        ? html`
                              <platform-button variant="secondary" @click=${() => window.location.reload()}>
                                  Обновить
                              </platform-button>
                          `
                        : html`
                              <platform-button variant="secondary" @click=${() => window.location.reload()}>
                                  Повторить
                              </platform-button>
                          `}
                </div>
            </div>
        `;
    }

    _goHome() {
        window.location.href = this.homeHref || '/';
    }
}

customElements.define('platform-shell-page', PlatformShellPage);
