/**
 * BranchItem — элемент ветки графа в flow-card.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

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
                --platform-button-icon-size: 22px;
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
                align-items: center;
            }

            .branch-item:hover .branch-actions {
                opacity: 1;
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

        const chatTitle = this.t('flow_card.open_chat_title');
        const editTitle = this.t('flow_card.edit_title');
        const deleteTitle = this.t('flow_card.delete_title');

        return html`
            <div class="branch-item">
                <div class="branch-info">
                    <div class="branch-name">${this.branch.name || this.branch.id}</div>
                    ${this.branch.description ? html`
                        <div class="branch-description">${this.branch.description}</div>
                    ` : ''}
                </div>
                <div class="branch-actions">
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${chatTitle}
                        @click=${(e) => this._emitAction('chat', e)}
                    >
                        <platform-icon name="chat" size="12"></platform-icon>
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${editTitle}
                        @click=${(e) => this._emitAction('edit', e)}
                    >
                        <platform-icon name="edit" size="12"></platform-icon>
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${deleteTitle}
                        @click=${(e) => this._emitAction('delete-branch', e)}
                    >
                        <platform-icon name="trash" size="12"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }
}

customElements.define('branch-item', BranchItem);
