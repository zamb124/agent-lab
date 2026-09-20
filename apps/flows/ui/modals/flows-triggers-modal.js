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
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import './flows-trigger-editor-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/fields/platform-field.js';

export class FlowsTriggersModal extends PlatformModal {
    static modalKind = 'flows.triggers';
    static i18nNamespace = 'flows';

    static styles = [
        ...PlatformModal.styles,
        glassStyles,
        css`
            .trg-search {
                margin-bottom: var(--space-3);
            }
            .trg-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
            .trg-table th, .trg-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
            .trg-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
            .trg-test-panel {
                margin-bottom: var(--space-4);
            }
            .trg-test-panel platform-field {
                display: block;
                width: 100%;
            }
            .trg-test-out {
                margin-top: var(--space-3);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-family: var(--font-mono);
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
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
        _query: { state: true },
        _testSampleJson: { state: true },
        _testResultText: { state: true },
        _lastTestTriggerId: { state: true },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.flowId = '';
        this._query = '';
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
                cancelText: this.t('common.action_cancel'),
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
            await this._testOp.run({
                flow_id: this.flowId,
                trigger_id: t.trigger_id,
                payload: body,
            });
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
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-triggers-modal: test sample expects string detail.value');
        }
        this._testSampleJson = v;
    }

    _onSearchChange(e) {
        const rawValue = e.detail.value;
        if (typeof rawValue !== 'string') {
            throw new TypeError('flows-triggers-modal: search expects string detail.value');
        }
        this._query = rawValue;
    }

    _filteredItems() {
        const listed = this._listOp.lastResult;
        if (listed === null || listed === undefined) {
            return [];
        }
        if (typeof listed !== 'object' || !Array.isArray(listed.items)) {
            throw new Error('flows-triggers-modal: triggers_list lastResult.items must be an array');
        }
        const items = listed.items;
        const query = this._query.trim().toLocaleLowerCase();
        if (query.length === 0) {
            return items;
        }
        return items.filter((item) => {
            if (!item || typeof item !== 'object') {
                return false;
            }
            const triggerId = typeof item.trigger_id === 'string' ? item.trigger_id : '';
            const name = typeof item.name === 'string' ? item.name : '';
            const type = typeof item.type === 'string' ? item.type : '';
            const haystack = `${triggerId} ${name} ${type}`.toLocaleLowerCase();
            return haystack.includes(query);
        });
    }

    _renderRows() {
        const items = this._filteredItems();
        if (this._listOp.busy && items.length === 0 && this._query.trim().length === 0) {
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
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('triggers_modal.action_test')}
                            @click=${() => this._test(t)}
                        >
                            <platform-icon name="play" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('triggers_modal.action_edit')}
                            @click=${() => this._edit(t)}
                        >
                            <platform-icon name="edit" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('triggers_modal.action_delete')}
                            @click=${() => this._delete(t)}
                        >
                            <platform-icon name="trash" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </td>
            </tr>
        `);
    }

    renderHeader() {
        return this.t('triggers_modal.title');
    }

    renderHeaderActions() {
        const createLabel = this.t('common.action_create');
        return html`
            <platform-button
                variant="primary"
                icon-only
                density="dense"
                aria-label=${createLabel}
                @click=${() => this._create()}
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </platform-button>
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
                      <div class="trg-test-out glass-subtle">${this._testResultText}</div>
                  `
                : null;
        return html`
            <div class="trg-test-panel">
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('triggers_modal.test_sample_label')}
                    .value=${this._testSampleJson}
                    @change=${this._onTestSampleInput}
                ></platform-field>
            </div>
            <platform-modal-search-field
                class="trg-search"
                layout="fill"
                .value=${this._query}
                placeholder=${this.t('triggers_modal.search')}
                @change=${this._onSearchChange}
            ></platform-modal-search-field>
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
