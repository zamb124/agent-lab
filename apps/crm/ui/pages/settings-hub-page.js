/**
 * SettingsHubPage — точка входа в настройки CRM:
 *
 *   - templates           — каталог шаблонов пространств.
 *   - namespace_imports   — задачи импорта знаний в пространства.
 *   - relationship_types  — типы связей.
 *
 * Сами разделы рендерятся отдельными страницами; здесь — карточный навигатор.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';

const CARDS = [
    { route: 'namespaces',             icon: 'folder',   key: 'card_namespaces' },
    { route: 'templates',          icon: 'layers',   key: 'card_templates' },
    { route: 'namespace_imports',  icon: 'workflow', key: 'card_namespace_imports' },
    { route: 'relationship_types', icon: 'network',  key: 'card_relationship_types' },
];

export class CRMSettingsHubPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
                gap: var(--space-4);
                padding: var(--space-4);
            }

            .card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: border-color var(--duration-fast),
                            background var(--duration-fast),
                            transform var(--duration-fast),
                            box-shadow var(--duration-fast);
                color: var(--text-primary);
                text-align: left;
                font: inherit;
            }

            .card:hover {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
                transform: translateY(-2px);
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
            }

            .card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }

            .card-icon {
                width: 48px;
                height: 48px;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
                display: flex;
                align-items: center;
                justify-content: center;
                transition: border-color var(--duration-fast),
                            color var(--duration-fast);
            }

            .card:hover .card-icon {
                border-color: var(--accent);
                color: var(--accent);
            }

            .card-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                margin: 0;
            }

            .card-description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
                margin: 0;
            }

            .card-arrow {
                color: var(--text-tertiary);
                align-self: flex-end;
                transition: transform var(--duration-fast),
                            color var(--duration-fast);
            }

            .card:hover .card-arrow {
                transform: translateX(4px);
                color: var(--text-primary);
            }

            @media (max-width: 767px) {
                .grid {
                    grid-template-columns: 1fr;
                    padding: var(--space-3);
                    gap: var(--space-3);
                }
                .card {
                    padding: var(--space-4);
                }
            }
        `,
    ];

    render() {
        return html`
            <page-header
                title=${this.t('settings_hub_page.title')}
                subtitle=${this.t('settings_hub_page.subtitle')}
            ></page-header>
            <div class="scroll">
                <div class="grid">
                    ${CARDS.map((card) => html`
                        <button class="card" @click=${() => this.navigate(card.route)}>
                            <div class="card-icon">
                                <platform-icon name=${card.icon} size="24"></platform-icon>
                            </div>
                            <h3 class="card-title">${this.t(`settings_hub_page.${card.key}_title`)}</h3>
                            <p class="card-description">${this.t(`settings_hub_page.${card.key}_description`)}</p>
                            <div class="card-arrow">
                                <platform-icon name="arrow-right" size="16"></platform-icon>
                            </div>
                        </button>
                    `)}
                </div>
            </div>
        `;
    }
}

customElements.define('crm-settings-hub-page', CRMSettingsHubPage);
