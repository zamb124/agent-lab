/**
 * FlowsSidebar - sidebar для Flows Builder
 * Использует platform-sidebar с поддержкой collapsed/mobile mode
 */
import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { FlowsStore } from '../../store/flows.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
import '@platform/lib/components/layout/sidebar-section.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import './flow-card.js';

export class FlowsSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }

            platform-sidebar {
                height: 100%;
            }

            .create-btn {
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: white;
                background: var(--accent);
                border: none;
                cursor: pointer;
                box-shadow: 0 2px 6px rgba(16, 185, 129, 0.2);
                transition: all var(--duration-normal) var(--easing-default);
            }

            .create-btn:hover {
                background: var(--accent-hover);
                transform: scale(1.1);
                box-shadow: 0 3px 8px rgba(16, 185, 129, 0.3);
            }

            sidebar-section {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }

            .flows-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
            }

            .footer-links {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .footer-link {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: none;
                text-decoration: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .footer-link:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            :host([collapsed]) .footer-links {
                display: flex;
                flex-direction: column;
                align-items: center;
            }

            :host([collapsed]) .footer-link {
                width: 36px;
                height: 36px;
                padding: 0;
                justify-content: center;
            }

            :host([collapsed]) .footer-link span {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;
        
        this.state = this.use(s => ({
            flows: s.flows.list,
            currentFlowId: s.flows.currentId,
            expandedFlows: s.ui.expandedFlows,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        FlowsStore.loadFlows(this.a2a);
    }

    toggleCollapse() {
        this.collapsed = !this.collapsed;
        this.emit('collapse-change', { collapsed: this.collapsed });
    }

    toggleMobile() {
        this.mobileOpen = !this.mobileOpen;
        this.emit('mobile-change', { open: this.mobileOpen });
    }

    closeMobile() {
        if (this.mobileOpen) {
            this.mobileOpen = false;
            this.emit('mobile-change', { open: false });
            window.dispatchEvent(new CustomEvent('platform-sidebar-mobile-change', {
                detail: { open: false },
            }));
        }
    }

    _createFlow() {
        const elementConstructor = customElements.get('flow-create-modal');
        
        if (!elementConstructor) {
            this.error(this.i18n.t('flows_sidebar.err_modal_not_loaded'));
            return;
        }
        
        const modal = new elementConstructor();
        document.body.appendChild(modal);
        
        requestAnimationFrame(() => {
            modal.setAttribute('open', '');
        });
        
        modal.addEventListener('template-selected', async (e) => {
            const { config } = e.detail;
            
            try {
                const createdFlow = await FlowsStore.createFlow(config, this.a2a);
                this.success(this.i18n.t('flows_sidebar.flow_created', { name: createdFlow.name }));
                
                setTimeout(() => {
                    this._editFlow(createdFlow.flow_id);
                }, 100);
            } catch (error) {
                this.error(this.i18n.t('flows_sidebar.err_create', { message: error.message }));
            }
        });
        
        modal.addEventListener('close', () => modal.remove());
    }

    _editFlow(flowId) {
        const modal = document.createElement('flow-edit-modal');
        modal.flowId = flowId;
        document.body.appendChild(modal);
        
        requestAnimationFrame(() => {
            modal.setAttribute('open', '');
        });
        
        modal.addEventListener('close', () => modal.remove());
    }

    _openSessions() {
        const modal = document.createElement('sessions-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openMCPServers() {
        const modal = document.createElement('mcp-servers-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openVariables() {
        const modal = document.createElement('variables-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _handleFlowAction(e) {
        const { action, flowId, skillId } = e.detail;
        
        switch (action) {
            case 'chat':
                if (skillId) {
                    FlowsStore.setCurrentFlowAndSkill(flowId, skillId);
                } else {
                    FlowsStore.setCurrentFlow(flowId);
                }
                this.closeMobile();
                break;
            case 'edit':
                if (skillId) {
                    const modal = document.createElement('flow-edit-modal');
                    modal.flowId = flowId;
                    modal.skillId = skillId;
                    document.body.appendChild(modal);
                    requestAnimationFrame(() => modal.setAttribute('open', ''));
                    modal.addEventListener('close', () => modal.remove());
                } else {
                    this._editFlow(flowId);
                }
                break;
            case 'delete':
                this._deleteFlow(flowId);
                break;
            case 'delete-skill':
                this._deleteSkill(flowId, skillId);
                break;
            case 'create-skill':
                this._createSkill(flowId);
                break;
            case 'toggle':
                FlowsStore.toggleExpandedFlow(flowId);
                break;
        }
    }

    async _deleteFlow(flowId) {
        const modal = document.createElement('confirm-modal');
        modal.title = this.i18n.t('flows_sidebar.delete_flow_title');
        modal.message = this.i18n.t('flows_sidebar.delete_flow_message', { id: flowId });
        modal.confirmText = this.i18n.t('context_menu.delete');
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await FlowsStore.deleteFlow(flowId, this.a2a);
            this.success(this.i18n.t('flows_sidebar.flow_deleted'));
        } catch (error) {
            this.error(this.i18n.t('flows_sidebar.err_delete', { message: error.message }));
            throw error;
        }
    }

    async _deleteSkill(flowId, skillId) {
        const modal = document.createElement('confirm-modal');
        modal.title = this.i18n.t('flows_sidebar.delete_skill_title');
        modal.message = this.i18n.t('flows_sidebar.delete_skill_message', { id: skillId });
        modal.confirmText = this.i18n.t('context_menu.delete');
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await FlowsStore.deleteSkill(flowId, skillId, this.a2a);
            this.success(this.i18n.t('flows_sidebar.skill_deleted'));
        } catch (error) {
            this.error(this.i18n.t('flows_sidebar.err_delete', { message: error.message }));
            throw error;
        }
    }

    _createSkill(flowId) {
        const modal = document.createElement('skill-create-modal');
        modal.flowId = flowId;
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
    }

    render() {
        const { flows, currentFlowId, expandedFlows } = this.state.value;

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/agents_logo.svg"
                logo-text="Flows"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => this.collapsed = e.detail.collapsed}
                @mobile-change=${(e) => this.mobileOpen = e.detail.open}
            >
                <sidebar-section title=${this.i18n.t('flows_sidebar.section_all_flows')} icon="folder" ?collapsed=${this.collapsed}>
                    <button 
                        slot="actions"
                        class="create-btn" 
                        title=${this.i18n.t('flows_sidebar.create_flow_tooltip')} 
                        @click=${this._createFlow}
                    >
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                    <div class="flows-list">
                        ${repeat(
                            flows,
                            (a) => a.flow_id,
                            (flowItem) => html`
                                <flow-card
                                    .flow=${flowItem}
                                    ?active=${flowItem.flow_id === currentFlowId}
                                    ?expanded=${!!expandedFlows[flowItem.flow_id]}
                                    ?collapsed=${this.collapsed}
                                    @flow-action=${this._handleFlowAction}
                                ></flow-card>
                            `
                        )}
                    </div>
                </sidebar-section>

                <div slot="footer">
                    <div class="footer-links">
                        <a class="footer-link" href="/documentation" target="_blank">
                            <platform-icon name="file" size="16"></platform-icon>
                            <span>Docs</span>
                        </a>
                        <button class="footer-link" @click=${this._openSessions}>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span>${this.i18n.t('flows_sidebar.footer_sessions')}</span>
                        </button>
                        <button class="footer-link" @click=${this._openMCPServers}>
                            <platform-icon name="cloud" size="16"></platform-icon>
                            <span>MCP</span>
                        </button>
                        <button class="footer-link" @click=${this._openVariables}>
                            <platform-icon name="key" size="16"></platform-icon>
                            <span>Vars</span>
                        </button>
                    </div>
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/flows" footer></platform-deployment-version>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('flows-sidebar', FlowsSidebar);
