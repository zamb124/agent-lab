/**
 * BranchItem — элемент ветки графа в flow-card.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class BranchItem extends PlatformElement {
    static properties = {
        branch: { type: Object },
        flowId: { type: String, attribute: 'flow-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .branch-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                transition: var(--motion-transition-interactive);
            }

            .branch-item:hover {
                background: var(--glass-solid-strong);
            }

            .branch-info {
                flex: 1;
                min-width: 0;
            }

            .branch-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .branch-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
                line-height: 1.4;
            }

            .branch-actions {
                display: flex;
                gap: 2px;
                opacity: 0;
                transition: opacity var(--duration-fast);
            }

            .branch-item:hover .branch-actions {
                opacity: 1;
            }

            .action-btn {
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: none;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .action-btn platform-icon {
                pointer-events: none;
            }

            .action-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .action-btn.chat:hover {
                color: var(--accent);
            }

            .action-btn.danger:hover {
                background: var(--error-bg);
                color: var(--error);
            }
        `,
    ];

    constructor() {
        super();
        this.branch = null;
        this.flowId = '';
    }

    _emitAction(action, e) {
        e?.stopPropagation();
        this.emit('branch-action', {
            action,
            branchId: this.branch.id,
            flowId: this.flowId,
        });
    }

    render() {
        if (!this.branch) return '';

        return html`
            <div class="branch-item">
                <div class="branch-info">
                    <div class="branch-name">${this.branch.name || this.branch.id}</div>
                    ${this.branch.description ? html`
                        <div class="branch-description">${this.branch.description}</div>
                    ` : ''}
                </div>
                <div class="branch-actions">
                    <button
                        class="action-btn chat"
                        @click=${(e) => this._emitAction('chat', e)}
                        title=${this.t('flow_card.open_chat_title')}
                    >
                        <platform-icon name="chat" size="12"></platform-icon>
                    </button>
                    <button
                        class="action-btn"
                        @click=${(e) => this._emitAction('edit', e)}
                        title=${this.t('flow_card.edit_title')}
                    >
                        <platform-icon name="edit" size="12"></platform-icon>
                    </button>
                    <button
                        class="action-btn danger"
                        @click=${(e) => this._emitAction('delete-branch', e)}
                        title=${this.t('flow_card.delete_title')}
                    >
                        <platform-icon name="trash" size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('branch-item', BranchItem);
