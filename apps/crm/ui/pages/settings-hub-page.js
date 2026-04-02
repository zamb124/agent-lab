import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

export class SettingsHubPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                height: 100%;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
            }
            .section {
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hero { display: flex; align-items: center; gap: var(--space-3); }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .hero-subtitle { color: var(--text-secondary); font-size: var(--text-sm); }
            .cards-grid { display: grid; gap: var(--space-4); grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); }
            .settings-card {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                padding: var(--space-5);
                background: var(--crm-surface-muted);
                cursor: pointer;
                transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast), box-shadow var(--duration-fast);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .settings-card:hover {
                border-color: var(--crm-selected-stroke);
                background: var(--crm-selected-bg);
                transform: translateY(-2px);
                box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            }
            .card-icon-wrap {
                width: 48px; height: 48px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--crm-surface-elevated);
                border: 1px solid var(--crm-stroke);
                color: var(--text-secondary);
            }
            .settings-card:hover .card-icon-wrap { border-color: var(--crm-selected-stroke); color: var(--crm-selected-text); }
            .card-title { color: var(--text-primary); font-size: var(--text-base); font-weight: 600; }
            .card-description { color: var(--text-secondary); font-size: var(--text-sm); line-height: 1.5; }
            .card-arrow { color: var(--text-tertiary); align-self: flex-end; transition: transform var(--duration-fast); }
            .settings-card:hover .card-arrow { transform: translateX(4px); color: var(--text-primary); }
            @media (max-width: 767px) {
                .hero-title { display: none; }
                .cards-grid { grid-template-columns: 1fr; }
            }
        `,
    ];

    _navigateTo(sectionId) {
        CRMStore.setCurrentView(sectionId);
    }

    _settingsSections() {
        return [
            {
                id: 'templates',
                icon: 'settings',
                title: this.i18n.t('settings_hub.card_templates_title'),
                description: this.i18n.t('settings_hub.card_templates_description'),
            },
            {
                id: 'spaces',
                icon: 'folder',
                title: this.i18n.t('settings_hub.card_spaces_title'),
                description: this.i18n.t('settings_hub.card_spaces_description'),
            },
        ];
    }

    render() {
        const sections = this._settingsSections();
        return html`
            <div class="container">
                <div class="section">
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <platform-icon name="settings" size="18"></platform-icon>
                                ${this.i18n.t('settings_hub.hero_title')}
                            </div>
                            <div class="hero-subtitle">${this.i18n.t('settings_hub.hero_subtitle')}</div>
                        </div>
                    </div>
                    <div class="cards-grid">
                        ${sections.map((section) => html`
                            <div class="settings-card" @click=${() => this._navigateTo(section.id)}>
                                <div class="card-icon-wrap">
                                    <platform-icon name=${section.icon} size="24"></platform-icon>
                                </div>
                                <div class="card-title">${section.title}</div>
                                <div class="card-description">${section.description}</div>
                                <div class="card-arrow">
                                    <platform-icon name="arrow-right" size="16"></platform-icon>
                                </div>
                            </div>
                        `)}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('settings-hub-page', SettingsHubPage);
