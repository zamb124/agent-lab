/**
 * Модальное окно трейсинга
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class TracingModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 1000px;
            }
            
            .tracing-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 400px;
            }
            
            .tracing-tree {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            
            .tracing-span {
                display: flex;
                flex-direction: column;
            }
            
            .span-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .span-header:hover {
                background: var(--glass-solid-medium);
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }
            
            .span-info {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                flex: 1;
            }
            
            .span-icon {
                font-size: var(--text-lg);
                flex-shrink: 0;
            }
            
            .span-status {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            
            .span-status.ok {
                background: var(--success);
            }
            
            .span-status.error {
                background: var(--error);
            }
            
            .span-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                flex: 1;
            }
            
            .span-duration {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            
            .span-toggle {
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-medium);
                border: none;
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
                flex-shrink: 0;
            }
            
            .span-toggle:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }
            
            .span-children {
                display: none;
                flex-direction: column;
                gap: var(--space-1);
                margin-left: var(--space-6);
                margin-top: var(--space-1);
            }
            
            .span-children.expanded {
                display: flex;
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
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
        taskId: { type: String },
        spans: { type: Array },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.title = 'Tracing';
        this.flowId = '';
        this.taskId = '';
        this.spans = [];
        this.loading = false;
    }

    async showModal() {
        super.showModal();
        await this._loadTraces();
    }

    async _loadTraces() {
        this.loading = true;
        try {
            if (!this.taskId) {
                console.error('Missing taskId for tracing loading');
                this.spans = [];
                this.loading = false;
                return;
            }

            const data = await this.a2a.get(`/api/v1/traces/task/${this.taskId}`);
            
            if (data.spans && data.spans.length > 0) {
                this.spans = data.spans;
            } else {
                this.spans = [];
            }
        } catch (error) {
            console.error('Error loading traces:', error);
            this.spans = [];
        }
        this.loading = false;
    }

    _getSpanIcon(operationName) {
        if (operationName.startsWith('flow.')) return '📊';
        if (operationName.startsWith('llm_node.')) return '🤖';
        if (operationName.startsWith('agent.')) return '🤖';
        if (operationName.startsWith('node.')) return '📦';
        if (operationName.startsWith('llm.')) return '🔵';
        if (operationName.startsWith('tool.')) return '🔧';
        if (operationName.startsWith('react.iteration')) return '🔄';
        if (operationName.startsWith('interrupt.')) return '⏸️';
        if (operationName.startsWith('request.')) return '🌐';
        return '📝';
    }

    _toggleSpanChildren(e, spanId) {
        e.stopPropagation();
        const spanEl = this.shadowRoot.querySelector(`[data-span-id="${spanId}"]`);
        if (!spanEl) return;

        const childrenEl = spanEl.querySelector('.span-children');
        const toggleBtn = spanEl.querySelector('.span-toggle');
        
        if (childrenEl && toggleBtn) {
            childrenEl.classList.toggle('expanded');
            toggleBtn.textContent = childrenEl.classList.contains('expanded') ? '▼' : '▶';
        }
    }

    _showSpanDetails(span) {
        const modal = document.createElement('span-details-modal');
        modal.span = span;
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    _renderSpan(span) {
        const operationName = span.operation_name || 'unknown';
        const duration = span.duration_ms || 0;
        const status = span.status || 'OK';
        const hasChildren = span.children && span.children.length > 0;
        const icon = this._getSpanIcon(operationName);
        const statusClass = status === 'ERROR' ? 'error' : 'ok';

        return html`
            <div class="tracing-span" data-span-id="${span.span_id}">
                <div class="span-header" @click=${() => this._showSpanDetails(span)}>
                    <div class="span-info">
                        <span class="span-icon">${icon}</span>
                        <span class="span-status ${statusClass}"></span>
                        <span class="span-name">${operationName}</span>
                        <span class="span-duration">${duration}ms</span>
                    </div>
                    ${hasChildren ? html`
                        <button class="span-toggle" @click=${(e) => this._toggleSpanChildren(e, span.span_id)}>
                            ▶
                        </button>
                    ` : ''}
                </div>
                ${hasChildren ? html`
                    <div class="span-children">
                        ${span.children.map(child => this._renderSpan(child))}
                    </div>
                ` : ''}
            </div>
        `;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="empty-state">
                    <platform-spinner variant="ai" size="48"></platform-spinner>
                    <p>Загрузка трейсинга...</p>
                </div>
            `;
        }

        if (this.spans.length === 0) {
            return html`
                <div class="empty-state">
                    <platform-icon name="terminal" size="48"></platform-icon>
                    <p>Нет данных трейсинга</p>
                    <p style="font-size: var(--text-sm);">Трейсы появятся после выполнения задач</p>
                </div>
            `;
        }

        return html`
            <div class="tracing-container">
                <div class="tracing-tree">
                    ${this.spans.map(span => this._renderSpan(span))}
                </div>
            </div>
        `;
    }
}

customElements.define('tracing-modal', TracingModal);
