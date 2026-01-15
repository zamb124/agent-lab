/**
 * AgentsApp - Главное приложение Agents Builder
 */
import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { A2AService } from '../services/a2a.service.js';
import { AgentsStore } from '../store/agents.store.js';
import '../components/sidebar/agents-sidebar.js';

export class AgentsApp extends PlatformApp {
    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                width: 100vw;
                height: 100vh;
                overflow: hidden;
                background: var(--bg-gradient);
            }

            agents-sidebar {
                flex-shrink: 0;
                height: 100%;
            }

            platform-chat {
                flex: 1;
                min-width: 0;
                height: calc(100vh - 2rem);
                margin: 1rem;
                margin-left: 0.5rem;
            }

            @media (max-width: 768px) {
                platform-chat {
                    margin: 0;
                    height: 100vh;
                }
            }
        `
    ];

    static properties = {
        ...PlatformApp.properties,
    };

    constructor() {
        super();
        this._handleToast = this._handleToast.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener(AppEvents.TOAST_SHOW, this._handleToast);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener(AppEvents.TOAST_SHOW, this._handleToast);
    }

    _handleToast(e) {
        const { type, message, duration } = e.detail;
        const toast = document.createElement('glass-toast');
        toast.type = type;
        toast.message = message;
        toast.duration = duration;
        document.body.appendChild(toast);
    }

    _toggleMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('agents-sidebar');
        sidebar?.toggleMobile();
    }

    _closeMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('agents-sidebar');
        sidebar?.closeMobile();
    }

    setupStore() {
        return AgentsStore;
    }

    getBaseUrl() {
        return '/agents';
    }

    async initServices() {
        await super.initServices();
        
        ServiceRegistry.register('a2a', new A2AService('/agents'));
        
        this.state = this.use(s => {
            const currentAgent = s.agents.list.find(a => a.agent_id === s.agents.currentId);
            const currentSkill = currentAgent?.skills?.[s.app.currentSkillId];
            return {
                currentAgentId: s.agents.currentId,
                currentAgentName: currentAgent?.name || '',
                currentSkillId: s.app.currentSkillId,
                currentSkillName: currentSkill?.name || '',
            };
        });
        
        const urlParts = window.location.pathname.split('/');
        const agentIdFromUrl = urlParts[urlParts.length - 1];
        
        if (agentIdFromUrl && agentIdFromUrl !== 'agents') {
            AgentsStore.setCurrentAgent(agentIdFromUrl);
        }
    }

    async checkAuth() {
        try {
            const response = await this.auth.validateToken();
            return response !== null;
        } catch (error) {
            console.error('[AgentsApp] Auth check failed:', error);
            return false;
        }
    }

    render() {
        if (!this._servicesInitialized || !this._authChecked) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Загрузка Agents Builder...</div>
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

        const { currentAgentId, currentAgentName, currentSkillId, currentSkillName } = this.state.value;

        return html`
            <agents-sidebar></agents-sidebar>
            <platform-chat 
                .agentId=${currentAgentId}
                .agentName=${currentAgentName}
                .skillId=${currentSkillId || ''}
                .skillName=${currentSkillName}
            ></platform-chat>
        `;
    }
}

customElements.define('agents-app', AgentsApp);
