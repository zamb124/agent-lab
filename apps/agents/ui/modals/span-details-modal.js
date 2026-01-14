/**
 * Модальное окно с деталями span
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class SpanDetailsModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 800px;
            }
            
            .span-details-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 300px;
            }
            
            .span-detail-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .section-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .detail-row {
                display: flex;
                gap: var(--space-3);
                padding: var(--space-2);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .detail-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                min-width: 120px;
            }
            
            .detail-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                flex: 1;
                word-break: break-all;
            }
            
            .status-ok {
                color: var(--success);
            }
            
            .status-error {
                color: var(--error);
            }
            
            .attributes-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .attribute-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .attribute-key {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .attribute-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .state-snapshot-viewer {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .snapshot-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .snapshot-key {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .snapshot-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .raw-json-btn {
                padding: var(--space-2) var(--space-4);
                background: var(--glass-solid-medium);
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .raw-json-btn:hover {
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-subtle);
            }

            /* Responsive - Tablet */
            @media (max-width: 768px) {
                :host {
                    --modal-max-width: 95vw;
                }
                
                .detail-row {
                    flex-direction: column;
                    gap: var(--space-1);
                }
                
                .detail-label {
                    min-width: auto;
                }
            }

            /* Responsive - Mobile */
            @media (max-width: 480px) {
                .span-details-container {
                    gap: var(--space-3);
                    min-height: 200px;
                }
                
                .attribute-row,
                .snapshot-field {
                    padding: var(--space-2);
                }
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        span: { type: Object },
    };

    constructor() {
        super();
        this.title = 'Детали Span';
        this.span = null;
    }

    _showRawJson() {
        const modal = document.createElement('raw-json-modal');
        modal.data = this.span;
        modal.title = `Raw JSON: ${this.span.operation_name || 'unknown'}`;
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    renderHeader() {
        return this.title;
    }

    renderHeaderActions() {
        return html`
            <button class="header-btn" @click=${this._showRawJson} title="Показать Raw JSON">
                { }
            </button>
        `;
    }

    renderBody() {
        if (!this.span) {
            return html`<p>Нет данных span</p>`;
        }

        const operationName = this.span.operation_name || 'unknown';
        const kind = this.span.kind || 'UNKNOWN';
        const status = this.span.status || 'OK';
        const duration = this.span.duration_ms || 0;
        const startTime = this.span.start_time || '';
        const endTime = this.span.end_time || '';
        
        let attrs = this.span.attributes || {};
        if (typeof attrs === 'string') {
            try { attrs = JSON.parse(attrs); } catch { attrs = {}; }
        }
        if (typeof attrs !== 'object' || attrs === null || Array.isArray(attrs)) {
            attrs = {};
        }

        const snapshot = attrs['platform.state.snapshot'];
        let snapshotFields = [];
        if (snapshot) {
            try {
                const parsed = typeof snapshot === 'string' ? JSON.parse(snapshot) : snapshot;
                snapshotFields = Object.entries(parsed);
            } catch (e) {
                console.warn('Failed to parse snapshot:', e);
            }
        }

        const attrsWithoutSnapshot = { ...attrs };
        delete attrsWithoutSnapshot['platform.state.snapshot'];
        const attributesList = Object.entries(attrsWithoutSnapshot);

        return html`
            <div class="span-details-container">
                <div class="span-detail-section">
                    <h3 class="section-title">Основная информация</h3>
                    <div class="detail-row">
                        <span class="detail-label">Operation:</span>
                        <span class="detail-value">${operationName}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Kind:</span>
                        <span class="detail-value">${kind}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value status-${status.toLowerCase()}">${status}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Duration:</span>
                        <span class="detail-value">${duration}ms</span>
                    </div>
                    ${startTime ? html`
                        <div class="detail-row">
                            <span class="detail-label">Start Time:</span>
                            <span class="detail-value">${startTime}</span>
                        </div>
                    ` : ''}
                    ${endTime ? html`
                        <div class="detail-row">
                            <span class="detail-label">End Time:</span>
                            <span class="detail-value">${endTime}</span>
                        </div>
                    ` : ''}
                </div>

                ${attributesList.length > 0 ? html`
                    <div class="span-detail-section">
                        <h3 class="section-title">Атрибуты</h3>
                        <div class="attributes-list">
                            ${attributesList.map(([key, value]) => html`
                                <div class="attribute-row">
                                    <span class="attribute-key">${key}</span>
                                    <span class="attribute-value">${
                                        typeof value === 'object' 
                                            ? JSON.stringify(value, null, 2)
                                            : String(value)
                                    }</span>
                                </div>
                            `)}
                        </div>
                    </div>
                ` : ''}

                ${snapshotFields.length > 0 ? html`
                    <div class="span-detail-section">
                        <h3 class="section-title">State Snapshot</h3>
                        <div class="state-snapshot-viewer">
                            ${snapshotFields.map(([key, value]) => html`
                                <div class="snapshot-field">
                                    <span class="snapshot-key">${key}</span>
                                    <span class="snapshot-value">${
                                        typeof value === 'object' 
                                            ? JSON.stringify(value, null, 2)
                                            : String(value)
                                    }</span>
                                </div>
                            `)}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('span-details-modal', SpanDetailsModal);
