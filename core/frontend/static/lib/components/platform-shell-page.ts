/**
 * Полноэкранные страницы: 404 и ошибка сервера (единый glass-стиль платформы).
 */
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-button.js';

export class PlatformShellPage extends PlatformElement {
    static override properties: PropertyDeclarations = {
        kind: { type: String },
        homeHref: { type: String, attribute: 'home-href' },
    };

    declare kind: string;
    declare homeHref: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: var(--app-vh, 100vh);
                width: 100%;
                padding: max(var(--space-6), env(safe-area-inset-top, 0px))
                    max(var(--space-6), env(safe-area-inset-right, 0px))
                    max(var(--space-6), env(safe-area-inset-bottom, 0px))
                    max(var(--space-6), env(safe-area-inset-left, 0px));
                box-sizing: border-box;
                background: var(--bg-gradient);
            }

            .panel {
                position: relative;
                width: 100%;
                max-width: 440px;
                padding: var(--space-8);
                border-radius: var(--radius-2xl);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                -webkit-backdrop-filter: blur(var(--glass-blur-strong));
                box-shadow: var(--glass-shadow-medium),
                    var(--glass-inner-glow-subtle);
                text-align: center;
            }

            .code {
                font-family: var(--font-sans);
                letter-spacing: var(--tracking-tight);
                font-size: 4rem;
                font-weight: 700;
                line-height: 1;
                margin: 0 0 var(--space-4);
                color: var(--accent);
                text-shadow: 0 0 40px rgba(153, 166, 249, 0.35);
            }

            h1 {
                margin: 0 0 var(--space-3);
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            p {
                margin: 0 0 var(--space-6);
                font-size: var(--text-sm);
                line-height: 1.55;
                color: var(--text-secondary);
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                justify-content: center;
            }
        `,
    ];

    constructor() {
        super();
        this.kind = 'not-found';
        this.homeHref = '/';
    }

    override render(): TemplateResult {
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

    _goHome(): void {
        window.location.href = this.homeHref || '/';
    }
}

customElements.define('platform-shell-page', PlatformShellPage);
