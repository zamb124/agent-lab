/**
 * CTA лендинга — кнопка призыва к действию.
 *
 * Открывает каноничную модалку заявки через openModal(FrontendLeadFormModal).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendLeadFormModal } from '../../modals/lead-form-modal.js';
import '@platform/lib/components/platform-icon.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class LandingCta extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 120px 20px;
                position: relative;
                overflow: hidden;
            }

            .blur-bg-primary {
                position: absolute;
                width: 1000px;
                height: 800px;
                background: color-mix(in srgb, var(--accent) 60%, transparent);
                filter: blur(150px);
                border-radius: 50%;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                pointer-events: none;
                z-index: 0;
            }

            .blur-bg-white {
                position: absolute;
                width: 1200px;
                height: 400px;
                background: var(--glass-border-strong);
                filter: blur(100px);
                bottom: 0;
                right: -300px;
                pointer-events: none;
                z-index: 0;
            }

            .cta-container {
                max-width: 800px;
                margin: 0 auto;
                text-align: center;
                position: relative;
                z-index: 1;
            }

            .cta-title {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 40px;
                font-weight: 500;
                line-height: 1.2;
                color: var(--text-on-accent);
                margin: 0 0 32px 0;
            }

            .cta-button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                padding: 20px 48px;
                background: var(--marketing-product-accent);
                color: var(--text-secondary);
                border: none;
                border-radius: 40px;
                font-family: var(--font-sans);
                font-weight: 500;
                font-size: 20px;
                cursor: pointer;
                transition:
                    transform 0.25s ease,
                    box-shadow 0.25s ease,
                    background 0.25s ease;
                box-shadow:
                    0 10px 40px color-mix(in srgb, var(--accent) 45%, transparent),
                    0 0 0 1px var(--glass-tint-strong) inset;
            }

            .cta-button:hover {
                background: var(--accent);
                transform: translateY(-3px);
                box-shadow:
                    0 16px 48px color-mix(in srgb, var(--accent) 55%, transparent),
                    0 0 0 1px var(--glass-tint-strong) inset;
            }

            .cta-button platform-icon {
                flex-shrink: 0;
                color: inherit;
            }

            @media (min-width: 768px) {
                :host {
                    padding: 150px 40px;
                }

                .cta-title {
                    font-size: 56px;
                    margin-bottom: 48px;
                }

                .cta-button {
                    font-size: 22px;
                    padding: 22px 56px;
                }
            }

            @media (min-width: 1440px) {
                :host {
                    padding: 180px 80px;
                }

                .cta-title {
                    font-size: 72px;
                }

                .cta-button {
                    font-size: 24px;
                    padding: 24px 64px;
                }
            }

            @media (prefers-reduced-motion: reduce) {
                .cta-button:hover {
                    transform: none;
                }
            }
        `,
    ];

    openRequestModal() {
        this.openModal(FrontendLeadFormModal);
    }

    override render(): TemplateResult {
        const t = (key: string) => (this.t(key) || key);
        return html`
            <div class="blur-bg-primary"></div>
            <div class="blur-bg-white"></div>

            <div class="cta-container">
                <h2 class="cta-title">${t('cta.title_plain')}</h2>

                <button type="button" class="cta-button" @click=${() => this.openRequestModal()}>
                    <platform-icon name="send" size="22"></platform-icon>
                    <span>${t('cta.button')}</span>
                </button>
            </div>
        `;
    }
}

customElements.define('landing-cta', LandingCta);
