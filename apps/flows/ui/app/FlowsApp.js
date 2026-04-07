/**
 * FlowsApp - главное приложение Flows Builder
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { A2AService } from '../services/a2a.service.js';
import { FlowsStore } from '../store/flows.store.js';
import { canManageOperatorWorkbench } from '../utils/operator-workbench-access.js';
import '../components/sidebar/flows-sidebar.js';
import '../features/operator/operator-workbench-page.js';

export class FlowsApp extends PlatformApp {
    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }

            flows-sidebar {
                flex-shrink: 0;
                height: 100%;
            }

            platform-chat {
                flex: 1;
                min-width: 0;
                height: calc(var(--app-vh, 100vh) - 2rem);
                margin: 1rem;
                margin-left: 0.5rem;
            }

            operator-workbench-page {
                flex: 1;
                min-width: 0;
                height: calc(var(--app-vh, 100vh) - 2rem);
                margin: 1rem;
            }

            .operator-access-denied {
                text-align: center;
                max-width: 28rem;
                margin: 0 auto;
            }

            .operator-access-denied .denied-title {
                font-size: var(--text-lg);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }

            .operator-access-denied .denied-text {
                font-size: var(--text-sm);
                color: var(--text-muted);
                margin-bottom: var(--space-4);
            }

            .operator-access-denied .denied-link {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-medium);
                text-decoration: none;
            }

            .operator-access-denied .denied-link:hover {
                background: var(--glass-solid-medium);
            }

            @media (max-width: 768px) {
                platform-chat {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                }

                operator-workbench-page {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                }
            }
        `
    ];

    static properties = {
        ...PlatformApp.properties,
    };

    constructor() {
        super();
        this._onOperatorAuthChange = () => this.requestUpdate();
    }

    async connectedCallback() {
        await super.connectedCallback();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onOperatorAuthChange);
    }

    disconnectedCallback() {
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._onOperatorAuthChange);
        super.disconnectedCallback();
    }

    _toggleMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('flows-sidebar');
        sidebar?.toggleMobile();
    }

    _closeMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('flows-sidebar');
        sidebar?.closeMobile();
    }

    setupStore() {
        return FlowsStore;
    }

    getBaseUrl() {
        return '/flows';
    }

    async initServices() {
        await super.initServices();
        
        this.services.register('a2a', new A2AService('/flows'));
        
        this.state = this.use(s => {
            const currentFlow = s.flows.list.find(a => a.flow_id === s.flows.currentId);
            const currentSkill = currentFlow?.skills?.[s.app.currentSkillId];
            return {
                currentFlowId: s.flows.currentId,
                currentFlowName: currentFlow?.name || '',
                currentSkillId: s.app.currentSkillId,
                currentSkillName: currentSkill?.name || '',
            };
        });
        
        const path = window.location.pathname.replace(/\/$/, '') || '';
        this._operatorWorkbench = path.endsWith('/operator');
        const urlParts = window.location.pathname.split('/');
        const flowIdFromUrl = urlParts[urlParts.length - 1];
        
        if (!this._operatorWorkbench && flowIdFromUrl && flowIdFromUrl !== 'flows') {
            FlowsStore.setCurrentFlow(flowIdFromUrl);
        }
    }

    async checkAuth() {
        try {
            const response = await this.auth.validateToken();
            return response !== null;
        } catch (error) {
            console.error('[FlowsApp] Auth check failed:', error);
            return false;
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">${this.i18n.t('flows_app.loading')}</div>
                </div>
            `;
        }

        if (!this._isAuthenticated) {
            return html`
                <div class="loading-container">
                    <div class="loading-text">${this.i18n.t('flows_app.redirect_auth')}</div>
                </div>
            `;
        }

        if (this._operatorWorkbench) {
            if (!canManageOperatorWorkbench(this.auth)) {
                return html`
                    <div class="loading-container operator-access-denied">
                        <p class="denied-title">${this.i18n.t('flows_app.operator_denied_title')}</p>
                        <p class="denied-text">${this.i18n.t('flows_app.operator_denied_body')}</p>
                        <a class="denied-link" href="/flows/example_react">${this.i18n.t('flows_app.operator_denied_back')}</a>
                    </div>
                `;
            }
            return html`<operator-workbench-page></operator-workbench-page>`;
        }

        const { currentFlowId, currentFlowName, currentSkillId, currentSkillName } = this.state.value;

        return html`
            <flows-sidebar></flows-sidebar>
            <platform-chat 
                .flowId=${currentFlowId}
                .flowName=${currentFlowName}
                .skillId=${currentSkillId || ''}
                .skillName=${currentSkillName}
            ></platform-chat>
        `;
    }
}

customElements.define('flows-app', FlowsApp);
