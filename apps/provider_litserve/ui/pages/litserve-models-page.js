/**
 * HumanitecModelsPage — реестр системных моделей Humanitec.
 *
 * Использует фабрику `humanitec_models/models` (createResourceCollection)
 * и операцию `humanitec_models/model_retry` (createAsyncOp). Доступ к
 * фабрикам — только через helpers `PlatformPage`.
 */

import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/fields/platform-field.js';

const KIND_ENUM_VALUES = ['embedding', 'rerank'];

export class HumanitecModelsPage extends PlatformPage {
    static i18nNamespace = 'litserve';

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
            }
            .page-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                box-sizing: border-box;
                padding: var(--space-4);
                flex: 1;
                min-height: 0;
            }
            @media (max-width: 767px) {
                .page-body {
                    padding: var(--space-2);
                    padding-top: 0;
                    padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
                    padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                    padding-bottom: var(--space-2);
                }
            }
            .add-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                box-shadow: var(--glass-shadow-subtle);
                padding: var(--space-4);
            }
            .add-grid {
                display: grid;
                grid-template-columns: 160px 1fr 1fr auto;
                gap: var(--space-3);
                align-items: end;
            }
            .add-grid platform-field { min-width: 0; }            .models-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: var(--space-4);
            }
            .model-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                box-shadow: var(--glass-shadow-subtle);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .model-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                padding: 0 var(--space-3);
                height: 26px;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                border: 1px solid var(--border-subtle);
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
            }
            .status-ready { border-color: var(--success); color: var(--success); }
            .status-failed { border-color: var(--error); color: var(--error); }
            .status-downloading,
            .status-pending { border-color: var(--warning); color: var(--warning); }
            .status-deleted { border-color: var(--text-tertiary); color: var(--text-tertiary); }
            .model-title {
                margin: 0;
                font-size: var(--text-base);
                color: var(--text-primary);
                word-break: break-word;
            }
            .meta-row { display: flex; flex-direction: column; gap: var(--space-1); }
            .meta-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .meta-value {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-primary);
                word-break: break-word;
            }
            .error-text {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--error);
                white-space: pre-wrap;
                word-break: break-word;
            }
            .actions {
                margin-top: auto;
                display: flex;
                gap: var(--space-2);
            }
            .empty {
                border: 1px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .loading { color: var(--text-secondary); }
            @media (max-width: 900px) {
                .add-grid { grid-template-columns: 1fr; }
            }
        `,
    ];

    static properties = {
        _kind: { state: true },
        _hfModelId: { state: true },
        _apiModelId: { state: true },
    };

    constructor() {
        super();
        this._kind = 'embedding';
        this._hfModelId = '';
        this._apiModelId = '';
        this._models = this.useResource('humanitec_models/models', { autoload: true });
        this._retry = this.useOp('humanitec_models/model_retry');
    }

    _kindEnumConfig() {
        return {
            values: KIND_ENUM_VALUES.map((k) => ({
                value: k,
                label: this.t(`models.kind_${k}`),
            })),
        };
    }

    _onKindChange(event) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        if (!KIND_ENUM_VALUES.includes(v)) {
            throw new Error(`HumanitecModelsPage._onKindChange: invalid kind "${v}"`);
        }
        this._kind = v;
    }

    _onHfModelChange(event) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._hfModelId = v;
    }

    _onApiModelChange(event) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._apiModelId = v;
    }

    _addModel() {
        const hfModelId = this._hfModelId.trim();
        const apiModelId = this._apiModelId.trim();
        if (!hfModelId) {
            throw new Error('hf_model_id is required');
        }
        if (!apiModelId) {
            throw new Error('api_model_id is required');
        }
        this._models.create({
            kind: this._kind,
            hf_model_id: hfModelId,
            api_model_id: apiModelId,
        });
        this._hfModelId = '';
        this._apiModelId = '';
    }

    _retryModel(modelId) {
        this._retry.run({ model_id: modelId });
    }

    _deleteModel(modelId) {
        this._models.remove(modelId);
    }

    _statusClass(status) {
        return `status-${status}`;
    }

    _renderModelCard(item) {
        return html`
            <article class="model-card">
                <div class="model-header">
                    <h3 class="model-title">${item.api_model_id}</h3>
                    <span class="badge ${this._statusClass(item.status)}">${item.status}</span>
                </div>

                <div class="meta-row">
                    <span class="meta-label">${this.t('models.kind')}</span>
                    <p class="meta-value">${item.kind}</p>
                </div>

                <div class="meta-row">
                    <span class="meta-label">${this.t('models.hf_model')}</span>
                    <p class="meta-value">${item.hf_model_id}</p>
                </div>

                <div class="meta-row">
                    <span class="meta-label">${this.t('models.updated_at')}</span>
                    <p class="meta-value">${item.updated_at}</p>
                </div>

                ${item.error
                    ? html`
                          <div class="meta-row">
                              <span class="meta-label">${this.t('models.error')}</span>
                              <p class="error-text">${item.error}</p>
                          </div>
                      `
                    : ''}

                <div class="actions">
                    <button class="btn btn-secondary" @click=${() => this._retryModel(item.model_id)}>
                        ${this.t('models.retry')}
                    </button>
                    <button class="btn btn-danger" @click=${() => this._deleteModel(item.model_id)}>
                        ${this.t('models.delete')}
                    </button>
                </div>
            </article>
        `;
    }

    render() {
        const items = this._models.items;
        const loading = this._models.loading;
        return html`
            <page-header
                title=${this.t('models.title')}
                subtitle=${this.t('models.subtitle')}
            ></page-header>
            <div class="page-body">
                <section class="add-card">
                    <div class="add-grid">
                        <platform-field
                            type="enum"
                            mode="edit"
                            .label=${this.t('models.kind')}
                            .value=${this._kind}
                            .config=${this._kindEnumConfig()}
                            @change=${this._onKindChange}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('models.hf_model')}
                            .placeholder=${this.t('models.hf_placeholder')}
                            .value=${this._hfModelId}
                            @change=${this._onHfModelChange}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('models.api_model')}
                            .placeholder=${this.t('models.api_placeholder')}
                            .value=${this._apiModelId}
                            @change=${this._onApiModelChange}
                        ></platform-field>
                        <button class="btn btn-primary" @click=${this._addModel}>
                            ${this.t('models.add')}
                        </button>
                    </div>
                </section>

                ${loading
                    ? html`<p class="loading">${this.t('models.loading')}</p>`
                    : ''}

                ${!loading && items.length === 0
                    ? html`<div class="empty">${this.t('models.empty')}</div>`
                    : ''}

                <section class="models-grid">
                    ${repeat(items, (item) => item.model_id, (item) => this._renderModelCard(item))}
                </section>
            </div>
        `;
    }
}

customElements.define('humanitec-models-page', HumanitecModelsPage);
