/**
 * dashboard-quick-actions — секция «Быстрые действия» на /dashboard.
 *
 * Container: список действий объявлен локально, рендерим
 * пресентейшнл-карточки и привязываем helpers базы (navigate / openModal)
 * к событию `activate`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './dashboard-quick-action-card.js';

const ACTIONS = Object.freeze([
    Object.freeze({ id: 'invite',   icon: 'user',     tone: 'accent',  titleKey: 'console_home.quick_invite_title',   descKey: 'console_home.quick_invite_desc'   }),
    Object.freeze({ id: 'api_key',  icon: 'key',      tone: 'info',    titleKey: 'console_home.quick_api_title',      descKey: 'console_home.quick_api_desc'      }),
    Object.freeze({ id: 'embed',    icon: 'chat',     tone: 'success', titleKey: 'console_home.quick_embed_title',    descKey: 'console_home.quick_embed_desc'    }),
    Object.freeze({ id: 'topup',    icon: 'chart',    tone: 'warning', titleKey: 'console_home.quick_topup_title',    descKey: 'console_home.quick_topup_desc'    }),
    Object.freeze({ id: 'settings', icon: 'settings', tone: 'accent',  titleKey: 'console_home.quick_settings_title', descKey: 'console_home.quick_settings_desc' }),
]);

export class DashboardQuickActions extends PlatformElement {
    static i18nNamespace = 'frontend';

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .header { margin-bottom: var(--space-5); }
            .title {
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                gap: var(--space-4);
            }
        `,
    ];

    _activate(actionId) {
        if (actionId === 'invite') {
            this.navigate('team');
            return;
        }
        if (actionId === 'api_key') {
            this.openModal('frontend.api_key_create');
            return;
        }
        if (actionId === 'embed') {
            this.openModal('frontend.embed_create');
            return;
        }
        if (actionId === 'topup') {
            this.openModal('frontend.billing_topup');
            return;
        }
        if (actionId === 'settings') {
            this.navigate('settings');
            return;
        }
        throw new Error(`dashboard-quick-actions: unknown action "${actionId}"`);
    }

    render() {
        return html`
            <div class="header">
                <h2 class="title">${this.t('console_home.quick_actions_title')}</h2>
            </div>
            <div class="grid">
                ${ACTIONS.map((a) => html`
                    <dashboard-quick-action-card
                        icon=${a.icon}
                        tone=${a.tone}
                        title=${this.t(a.titleKey)}
                        description=${this.t(a.descKey)}
                        @activate=${() => this._activate(a.id)}
                    ></dashboard-quick-action-card>
                `)}
            </div>
        `;
    }
}

customElements.define('dashboard-quick-actions', DashboardQuickActions);
