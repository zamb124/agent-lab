/**
 * Модальное окно просмотра State
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class StateModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 800px;
            }
            
            .state-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 400px;
            }
            
            .state-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .state-content {
                padding: var(--space-4);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                white-space: pre-wrap;
                word-break: break-word;
                max-height: 500px;
                overflow-y: auto;
                line-height: 1.5;
            }
            
            .state-metadata {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: var(--space-3);
            }
            
            .metadata-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .metadata-label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .metadata-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
            }
            
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                min-height: 300px;
                color: var(--text-tertiary);
                text-align: center;
                gap: var(--space-3);
            }
            
            .empty-state-icon {
                opacity: 0.5;
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        contextId: { type: String },
        taskId: { type: String },
        flowId: { type: String },
        state: { type: Object },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.contextId = '';
        this.taskId = '';
        this.flowId = '';
        this.state = null;
        this.loading = false;
    }

    renderHeader() {
        return this.i18n.t('state_modal.modal_title');
    }

    async showModal() {
        super.showModal();
        await this._loadState();
    }

    async _loadState() {
        this.loading = true;
        try {
            if (!this.contextId || !this.flowId) {
                console.error('Missing contextId or flowId for state loading');
                this.state = null;
                this.loading = false;
                return;
            }

            const params = new URLSearchParams({
                context_id: this.contextId,
                flow_id: this.flowId
            });
            
            this.state = await this.a2a.get(`/api/v1/tasks/state?${params}`);
        } catch (error) {
            console.error('Error loading state:', error);
            this.state = null;
        }
        this.loading = false;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="empty-state">
                    <platform-spinner variant="ai" size="48"></platform-spinner>
                    <p>${this.i18n.t('state_modal.loading')}</p>
                </div>
            `;
        }

        if (!this.state) {
            return html`
                <div class="empty-state">
                    <platform-icon name="database" size="48" class="empty-state-icon"></platform-icon>
                    <p>${this.i18n.t('state_modal.empty_no_data')}</p>
                    <p style="font-size: var(--text-sm);">${this.i18n.t('state_modal.empty_hint')}</p>
                </div>
            `;
        }

        return html`
            <div class="state-container">
                <div class="state-metadata">
                    <div class="metadata-item">
                        <span class="metadata-label">Context ID</span>
                        <span class="metadata-value">${this.contextId}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="metadata-label">Task ID</span>
                        <span class="metadata-value">${this.taskId || 'N/A'}</span>
                    </div>
                </div>
                
                <div class="state-section">
                    <div class="section-title">State Data</div>
                    <div class="state-content">
                        ${JSON.stringify(this.state, null, 2)}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('state-modal', StateModal);

