/**
 * FlowsSidebar — список flow; оболочка platform-service-sidebar.
 */
import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { FlowsStore } from '../../store/flows.store.js';
import { setUrlParam, removeUrlParams } from '../../utils/url-sync.js';
import { canManageOperatorWorkbench } from '../../utils/operator-workbench-access.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/layout/sidebar-section.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
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

            platform-service-sidebar {
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
                box-shadow: 0 2px 6px rgba(153, 166, 249, 0.2);
                transition: all var(--duration-normal) var(--easing-default);
            }

            .create-btn:hover {
                background: var(--accent-hover);
                transform: scale(1.1);
                box-shadow: 0 3px 8px rgba(153, 166, 249, 0.3);
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

            platform-service-sidebar[collapsed] .footer-links {
                display: flex;
                flex-direction: column;
                align-items: center;
            }

            platform-service-sidebar[collapsed] .footer-link {
                width: 36px;
                height: 36px;
                padding: 0;
                justify-content: center;
            }

            platform-service-sidebar[collapsed] .footer-link span {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._onFlowsAuthChange = () => this.requestUpdate();
        this.state = this.use(s => ({
            flows: s.flows.list,
            currentFlowId: s.flows.currentId,
            expandedFlows: s.ui.expandedFlows,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        FlowsStore.loadFlows(this.a2a);
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onFlowsAuthChange);
    }

    disconnectedCallback() {
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._onFlowsAuthChange);
        super.disconnectedCallback();
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar');
    }

    toggleMobile() {
        this._shell()?.toggleMobile();
    }

    closeMobile() {
        this._shell()?.closeMobile();
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
        this._openEditor(flowId, null);
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
                removeUrlParams('session', 'edit');
                this.closeMobile();
                break;
            case 'edit':
                this._openEditor(flowId, skillId);
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

    _openEditor(flowId, skillId) {
        const modal = document.createElement('flow-edit-modal');
        modal.flowId = flowId;
        if (skillId) modal.skillId = skillId;
        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.setAttribute('open', ''));

        setUrlParam('edit', '1');
        if (skillId) setUrlParam('skill', skillId);

        modal.addEventListener('close', () => {
            modal.remove();
            removeUrlParams('edit');
        });
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
        const operatorEntry = canManageOperatorWorkbench(this.auth)
            ? html`
                  <a class="footer-link" href="/flows/operator">
                      <platform-icon name="users" size="16"></platform-icon>
                      <span>${this.i18n.t('flows_sidebar.footer_operator_tasks')}</span>
                  </a>
              `
            : null;
        const footerLinks = html`
            ${operatorEntry}
            <button type="button" class="footer-link" @click=${this._openSessions}>
                <platform-icon name="chat" size="16"></platform-icon>
                <span>${this.i18n.t('flows_sidebar.footer_sessions')}</span>
            </button>
            <button type="button" class="footer-link" @click=${this._openMCPServers}>
                <platform-icon name="cloud" size="16"></platform-icon>
                <span>${this.i18n.t('flows_sidebar.footer_mcp')}</span>
            </button>
            <button type="button" class="footer-link" @click=${this._openVariables}>
                <platform-icon name="key" size="16"></platform-icon>
                <span>${this.i18n.t('flows_sidebar.footer_vars')}</span>
            </button>
        `;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/agents_logo.svg"
                logo-text="Flows"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => {
                    this.collapsed = e.detail.collapsed;
                }}
                @mobile-change=${(e) => {
                    this.mobileOpen = e.detail.open;
                }}
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
                    <div class="footer-links">${footerLinks}</div>
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/flows" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('flows-sidebar', FlowsSidebar);
