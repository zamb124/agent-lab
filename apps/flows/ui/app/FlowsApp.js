/**
 * FlowsApp - главное приложение Flows Builder
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { A2AService } from '../services/a2a.service.js';
import { FlowsStore } from '../store/flows.store.js';
import '../components/sidebar/flows-sidebar.js';

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

            @media (max-width: 768px) {
                platform-chat {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                }
            }
        `
    ];

    static properties = {
        ...PlatformApp.properties,
    };

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
        
        const urlParts = window.location.pathname.split('/');
        const flowIdFromUrl = urlParts[urlParts.length - 1];
        
        if (flowIdFromUrl && flowIdFromUrl !== 'flows') {
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
                    <div class="loading-text">Загрузка Flows Builder...</div>
                </div>
            `;
        }

        if (!this._isAuthenticated) {
            return html`
                <div class="loading-container">
                    <div class="loading-text">Redirecting to authentication...</div>
                </div>
            `;
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
