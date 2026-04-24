/**
 * flows-triggers-modal — список триггеров flow.
 *
 * Источник — useOp('flows/triggers_list'); CRUD через trigger_create/update/remove ops.
 * Редактор открывается через `flows.trigger_editor`.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import './flows-trigger-editor-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsTriggersModal extends PlatformModal {
    static modalKind = 'flows.triggers';
    static i18nNamespace = 'flows';

    static styles = [
        ...PlatformModal.styles,
        css`
            .trg-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
            .trg-table th, .trg-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
            .trg-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
            .flows-header-action-create {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 50%);
                flex-shrink: 0;
                cursor: pointer;
                color: var(--platform-btn-primary-text, #ffffff);
                background: var(--platform-btn-primary-bg, #99a6f9);
                box-shadow: var(--platform-btn-primary-shadow, none);
                transition: all var(--duration-fast, 0.15s) var(--easing-default, ease);
            }
            .flows-header-action-create platform-icon {
                display: flex;
            }
            .flows-header-action-create:hover:not(:disabled) {
                background: var(--platform-btn-primary-bg-hover, #8794f0);
                box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
            }
            .flows-header-action-create:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .trg-test-panel {
                margin-bottom: var(--space-4);
            }
            .trg-test-panel label {
                display: block;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            .trg-test-textarea {
                width: 100%;
                min-height: 80px;
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-xs);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                box-sizing: border-box;
            }
            .trg-test-out {
                margin-top: var(--space-3);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-xs);
                white-space: pre-wrap;
                word-break: break-word;
                max-height: 240px;
                overflow: auto;
            }
            .trg-row-actions {
                display: inline-flex;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .trg-row-actions .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 32px;
                min-height: 32px;
                padding: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .trg-row-actions .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }
            .trg-row-actions .icon-btn.danger:hover {
                color: var(--error, #f43f5e);
                border-color: var(--error, #f43f5e);
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
        _testSampleJson: { state: true },
        _testResultText: { state: true },
        _lastTestTriggerId: { state: true },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.flowId = '';
        this._testSampleJson = '{}';
        this._testResultText = '';
        this._lastTestTriggerId = '';
        this._listOp = this.useOp('flows/triggers_list');
        this._removeOp = this.useOp('flows/trigger_remove');
        this._testOp = this.useOp('flows/trigger_test');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            void this._listOp.run({ flow_id: this.flowId });
        }
    }

    _create() {
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: null });
    }

    _edit(t) {
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: t });
    }

    async _delete(t) {
        const ok = await platformConfirm(
            this.t('triggers_modal.delete_message', { id: t.trigger_id }),
            {
                title: this.t('triggers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('triggers_modal.action_delete'),
                cancelText: this.t('triggers_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._removeOp.run({ flow_id: this.flowId, trigger_id: t.trigger_id });
        await this._listOp.run({ flow_id: this.flowId });
    }

    async _test(t) {
        const raw = this._testSampleJson;
        if (typeof raw !== 'string') {
            throw new Error('flows-triggers-modal: test sample must be a string');
        }
        const trimmed = raw.trim();
        let body;
        if (trimmed.length === 0) {
            body = {};
        } else {
            try {
                body = JSON.parse(trimmed);
            } catch (err) {
                this._testResultText = '';
                this._lastTestTriggerId = '';
                this.toast('flows:triggers_modal.test_json_error', { type: 'error' });
                return;
            }
        }
        if (body !== null && typeof body === 'object' && !Array.isArray(body)) {
            await this._testOp.run({ flow_id: this.flowId, trigger_id: t.trigger_id, body });
            const lr = this._testOp.lastResult;
            this._testResultText = JSON.stringify(lr, null, 2);
            this._lastTestTriggerId = t.trigger_id;
        } else {
            this._testResultText = '';
            this._lastTestTriggerId = '';
            this.toast('flows:triggers_modal.test_json_error', { type: 'error' });
        }
    }

    _onTestSampleInput(e) {
        this._testSampleJson = e.target.value;
    }

    _renderRows() {
        const items = Array.isArray(this._listOp.lastResult) ? this._listOp.lastResult : [];
        if (this._listOp.busy && items.length === 0) {
            return html`<tr><td colspan="5"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="5" class="trg-empty">${this.t('triggers_modal.empty')}</td></tr>`;
        }
        return items.map((t) => html`
            <tr>
                <td><code>${t.trigger_id}</code></td>
                <td>${t.name}</td>
                <td>${t.type}</td>
                <td>${t.enabled ? this.t('triggers_modal.status_enabled') : this.t('triggers_modal.status_disabled')}</td>
                <td>
                    <div class="trg-row-actions">
                        <button
                            type="button"
                            class="icon-btn"
                            title=${this.t('triggers_modal.action_test')}
                            aria-label=${this.t('triggers_modal.action_test')}
                            @click=${() => this._test(t)}
                        >
                            <platform-icon name="play" size="16"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="icon-btn"
                            title=${this.t('triggers_modal.action_edit')}
                            aria-label=${this.t('triggers_modal.action_edit')}
                            @click=${() => this._edit(t)}
                        >
                            <platform-icon name="edit" size="16"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="icon-btn danger"
                            title=${this.t('triggers_modal.action_delete')}
                            aria-label=${this.t('triggers_modal.action_delete')}
                            @click=${() => this._delete(t)}
                        >
                            <platform-icon name="trash" size="16"></platform-icon>
                        </button>
                    </div>
                </td>
            </tr>
        `);
    }

    renderHeader() {
        return this.t('triggers_modal.title');
    }

    renderHeaderActions() {
        const createLabel = this.t('triggers_modal.action_create');
        return html`
            <button
                type="button"
                class="flows-header-action-create"
                title=${createLabel}
                aria-label=${createLabel}
                @click=${() => this._create()}
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        const resultBlock =
            this._testResultText.length > 0
                ? html`
                      <p class="trg-test-hint" style="margin: 0 0 var(--space-1) 0; font-size: var(--text-sm); color: var(--text-secondary);">
                          ${this.t('triggers_modal.test_result_title')}
                          ${this._lastTestTriggerId
                              ? html` <code>${this._lastTestTriggerId}</code>`
                              : ''}
                      </p>
                      <div class="trg-test-out">${this._testResultText}</div>
                  `
                : null;
        return html`
            <div class="trg-test-panel">
                <label for="trg-test-json">${this.t('triggers_modal.test_sample_label')}</label>
                <textarea
                    id="trg-test-json"
                    class="trg-test-textarea"
                    spellcheck="false"
                    .value=${this._testSampleJson}
                    @input=${this._onTestSampleInput}
                ></textarea>
            </div>
            <table class="trg-table">
                <thead>
                    <tr>
                        <th>${this.t('triggers_modal.col_id')}</th>
                        <th>${this.t('triggers_modal.col_name')}</th>
                        <th>${this.t('triggers_modal.col_type')}</th>
                        <th>${this.t('triggers_modal.col_status')}</th>
                        <th>${this.t('triggers_modal.col_actions')}</th>
                    </tr>
                </thead>
                <tbody>${this._renderRows()}</tbody>
            </table>
            ${resultBlock}
        `;
    }
}

customElements.define('flows-triggers-modal', FlowsTriggersModal);
registerModalKind(FlowsTriggersModal.modalKind, 'flows-triggers-modal');
