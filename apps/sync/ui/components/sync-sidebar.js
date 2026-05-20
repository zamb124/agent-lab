/**
 * SyncSidebar — навигация Sync на каноничной оболочке `platform-service-sidebar`.
 *
 * Контент списка чатов вынесен в `<sync-chat-list>` (используется и в
 * `sync-shell-page` на мобиле) — сайдбар и главная страница идентичны по UX.
 *
 * Активное «пространство» выбирается тем же глобальным селектом
 * платформенного namespace, что и в CRM. Создание namespace — в CRM
 * (`crm.namespace`-modal); sync редактирует только `Namespace.sync_settings`
 * через карандаш на выбранном namespace (`sync.namespace_settings`).
 *
 * Слоты `<platform-service-sidebar>`:
 *   - header: header из <sync-chat-list> (через slot 'header' внутри sync-chat-list).
 *   - default (nav): body из <sync-chat-list>.
 *   - footer: <platform-user block>.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    sidebarStyles,
    sidebarNavItemStyles,
    sidebarSectionStyles,
} from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import './sync-chat-list.js';

export class SyncSidebar extends PlatformElement {
    static i18nNamespace = 'sync';

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        sidebarSectionStyles,
        css`
            :host {
                display: block;
                height: 100%;
                --sidebar-nav-inline: var(--space-1);
            }

            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--accent-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }

            .user-section {
                display: flex;
                flex-direction: column;
                gap: 0;
                width: 100%;
                min-width: 0;
                padding: var(--space-3) var(--sidebar-nav-inline) 0;
                margin-top: 0;
                box-sizing: border-box;
            }

            platform-service-sidebar[collapsed] sync-chat-list { display: none; }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
    }

    _onAdhocCallStarted() {
        this.renderRoot?.querySelector('platform-service-sidebar')?.closeMobile?.();
    }

    render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/sync_logo.svg"
                logo-text="Sync"
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <sync-chat-list
                    mode="sidebar"
                    @adhoc-call-started=${this._onAdhocCallStarted}
                ></sync-chat-list>
                <div slot="footer" class="user-section">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('sync-sidebar', SyncSidebar);
