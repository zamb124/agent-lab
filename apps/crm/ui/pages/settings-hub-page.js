import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

const SETTINGS_SECTIONS = [
    {
        id: 'templates',
        title: 'Шаблоны пространств',
        description: 'Создание и редактирование шаблонов для новых пространств. Полный контроль типов сущностей, полей и промптов.',
        icon: 'settings',
    },
    {
        id: 'spaces',
        title: 'Настройки пространств',
        description: 'Управление типами и описаниями текущих пространств компании. Безопасное добавление и редактирование.',
        icon: 'folder',
    },
];

export class SettingsHubPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container { display: flex; flex-direction: column; gap: var(--space-4); height: 100%; overflow-y: auto; padding: var(--space-2); }
            .section { background: var(--crm-surface); border: 1px solid var(--crm-stroke); border-radius: var(--radius-xl); padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
            .hero { display: flex; align-items: center; gap: var(--space-3); }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .hero-subtitle { color: var(--text-secondary); font-size: var(--text-sm); }
            .menu-btn { width: 32px; height: 32px; display: none; align-items: center; justify-content: center; border-radius: var(--radius-md); background: var(--crm-surface-muted); border: 1px solid var(--crm-stroke); color: var(--text-primary); cursor: pointer; }
            .cards-grid { display: grid; gap: var(--space-4); grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
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
            @media (max-width: 767px) { .menu-btn { display: inline-flex; } }
        `,
    ];

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', { bubbles: true, composed: true }));
    }

    _navigateTo(sectionId) {
        CRMStore.setCurrentView(sectionId);
    }

    render() {
        return html`
            <div class="container">
                <div class="section">
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <button class="menu-btn" @click=${this._openSidebar} title="Открыть меню">
                                    <platform-icon name="menu" size="18"></platform-icon>
                                </button>
                                <platform-icon name="settings" size="18"></platform-icon>
                                Настройки CRM
                            </div>
                            <div class="hero-subtitle">Выберите раздел для настройки</div>
                        </div>
                    </div>
                    <div class="cards-grid">
                        ${SETTINGS_SECTIONS.map((section) => html`
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
