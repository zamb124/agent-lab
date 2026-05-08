/**
 * RelationshipTypesPage — каталог типов связей CRM.
 *
 * Список и создание — через фабрику `crm/relationship_types`
 * (createResourceCollection: list + create). Удаление и редактирование на
 * бэкенде пока не поддерживаются — карточки readonly.
 *
 * Кнопка "Добавить тип" разворачивает inline-форму. Сабмит — через
 * `_resource.create(payload)`; на CREATED форма скрывается, draft сбрасывается;
 * тост об успехе диспатчит сама фабрика (`toast.relationship_type.created`).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/fields/platform-field.js';

const PALETTE = [
    '#007aff', '#5856d6', '#34c759', '#ff9500', '#ff3b30',
    '#af52de', '#00c7be', '#ff2d55', '#5ac8fa', '#ffcc00',
];

function _emptyDraft() {
    return {
        type_id: '',
        name: '',
        description: '',
        is_directed: true,
        inverse_type_id: '',
        color: '',
        weight_default: 1.0,
    };
}

export class CRMRelationshipTypesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _showForm: { state: true },
        _draft: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: var(--space-2) var(--space-4) 0;
            }

            .section {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .form-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
                align-items: start;
            }

            .form-grid platform-field {
                min-width: 0;
            }

            .palette-card {
                margin-bottom: 0;
            }

            .form-footer {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border: 1px solid transparent;
                transition: background var(--duration-fast),
                            border-color var(--duration-fast);
            }

            .btn-primary {
                background: var(--accent);
                color: var(--platform-btn-primary-text, white);
                border-color: var(--accent);
            }

            .btn-primary:hover:not(:disabled) {
                filter: brightness(0.95);
            }

            .btn-soft {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-color: var(--glass-border-subtle);
            }

            .btn-soft:hover:not(:disabled) {
                border-color: var(--accent);
            }

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .palette {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
            }

            .palette-dot {
                width: 22px;
                height: 22px;
                border-radius: var(--radius-full);
                border: 2px solid transparent;
                cursor: pointer;
            }

            .palette-dot.active {
                border-color: var(--text-primary);
            }

            .type-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
            }

            .type-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                background: var(--glass-solid-medium);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .type-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .type-color {
                width: 12px;
                height: 12px;
                border-radius: var(--radius-full);
                flex-shrink: 0;
            }

            .type-name {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .type-id {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
            }

            .type-desc {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .type-meta {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }

            .badge.system {
                background: rgba(255, 149, 0, 0.15);
                color: #ff9500;
                border-color: rgba(255, 149, 0, 0.3);
            }

            .empty {
                text-align: center;
                padding: var(--space-6);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            @media (max-width: 767px) {
                .scroll {
                    padding: var(--space-3);
                    gap: var(--space-3);
                }
                .type-grid,
                .form-grid {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._showForm = false;
        this._draft = _emptyDraft();
        this._saving = false;
        this._resource = this.useResource('crm/relationship_types', { autoload: true });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._resource.resource.events.CREATED, () => {
            this._saving = false;
            this._showForm = false;
            this._draft = _emptyDraft();
        });
        this.useEvent(this._resource.resource.events.CREATE_FAILED, () => {
            this._saving = false;
            this.toast('relationship_types_page.err_create', { type: 'error' });
        });
    }

    _updateDraft(field, value) {
        this._draft = { ...this._draft, [field]: value };
    }

    _toggleForm() {
        if (this._showForm) {
            this._showForm = false;
            this._draft = _emptyDraft();
        } else {
            this._showForm = true;
        }
    }

    _onSubmit() {
        const draft = this._draft;
        const typeId = draft.type_id.trim();
        const name = draft.name.trim();
        if (typeId.length === 0) {
            this.toast('relationship_types_page.err_type_id_required', { type: 'warning' });
            return;
        }
        if (name.length === 0) {
            this.toast('relationship_types_page.err_name_required', { type: 'warning' });
            return;
        }
        this._saving = true;
        const description = draft.description.trim();
        const inverse = draft.inverse_type_id.trim();
        const color = draft.color.trim();
        const weight = Number(draft.weight_default);
        const payload = {
            type_id: typeId,
            name,
            description: description.length > 0 ? description : null,
            is_directed: Boolean(draft.is_directed),
            inverse_type_id: inverse.length > 0 ? inverse : null,
            color: color.length > 0 ? color : null,
            weight_default: Number.isFinite(weight) && weight > 0 ? weight : 1.0,
        };
        this._resource.create(payload);
    }

    _renderForm() {
        if (!this._showForm) return '';
        const d = this._draft;
        return html`
            <div class="section">
                <strong>${this.t('relationship_types_page.form_title')}</strong>
                <div class="form-grid">
                    <platform-field
                        type="string"
                        mode="edit"
                        input-type="text"
                        .label=${`${this.t('relationship_types_page.label_type_id')} *`}
                        placeholder="works_for"
                        .value=${d.type_id}
                        @change=${(e) => this._updateDraft('type_id', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        input-type="text"
                        .label=${`${this.t('relationship_types_page.label_name')} *`}
                        .value=${d.name}
                        @change=${(e) => this._updateDraft('name', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('relationship_types_page.label_description')}
                        .value=${d.description}
                        @change=${(e) => this._updateDraft('description', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        input-type="text"
                        .label=${this.t('relationship_types_page.label_inverse')}
                        placeholder="employed_by"
                        .value=${d.inverse_type_id}
                        @change=${(e) => this._updateDraft('inverse_type_id', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        .label=${this.t('relationship_types_page.label_weight')}
                        .value=${d.weight_default}
                        @change=${(e) => {
                            const v = e.detail.value;
                            const next = v != null && typeof v === 'number' && Number.isFinite(v) ? v : 1.0;
                            this._updateDraft('weight_default', next);
                        }}
                    ></platform-field>
                    <div class="field-pill palette-card">
                        <div class="field-pill-head">
                            <span class="field-pill-label">${this.t('relationship_types_page.label_color')}</span>
                        </div>
                        <div class="palette">
                            ${PALETTE.map((c) => html`
                                <div
                                    class="palette-dot ${d.color === c ? 'active' : ''}"
                                    style="background:${c}"
                                    @click=${() => this._updateDraft('color', d.color === c ? '' : c)}
                                ></div>
                            `)}
                        </div>
                    </div>
                    <platform-field
                        type="boolean"
                        mode="edit"
                        .label=${this.t('relationship_types_page.label_directed')}
                        .value=${d.is_directed}
                        @change=${(e) => this._updateDraft('is_directed', Boolean(e.detail.value))}
                    ></platform-field>
                </div>
                <div class="form-footer">
                    <button class="btn btn-primary" ?disabled=${this._saving} @click=${this._onSubmit}>
                        <platform-icon name="check" size="14"></platform-icon>
                        ${this._saving
                            ? this.t('relationship_types_page.saving')
                            : this.t('relationship_types_page.create')}
                    </button>
                    <button class="btn btn-soft" ?disabled=${this._saving} @click=${this._toggleForm}>
                        ${this.t('relationship_types_page.cancel')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderList() {
        const items = this._resource.items;
        if (this._resource.loading && items.length === 0) {
            return html`<div class="section"><div class="empty">${this.t('relationship_types_page.loading')}</div></div>`;
        }
        if (items.length === 0) {
            return html`<div class="section"><div class="empty">${this.t('relationship_types_page.empty')}</div></div>`;
        }
        return html`
            <div class="section">
                <div class="type-grid">
                    ${items.map((t) => html`
                        <div class="type-card">
                            <div class="type-header">
                                ${t.color ? html`<div class="type-color" style="background:${t.color}"></div>` : ''}
                                <span class="type-name">${t.name}</span>
                                ${t.is_system ? html`<span class="badge system">${this.t('relationship_types_page.system')}</span>` : ''}
                            </div>
                            <div class="type-id">${t.type_id}</div>
                            ${t.description ? html`<div class="type-desc">${t.description}</div>` : ''}
                            <div class="type-meta">
                                <span class="badge">
                                    <platform-icon
                                        name="${t.is_directed ? 'arrow-right' : 'link'}"
                                        size="10"
                                    ></platform-icon>
                                    ${t.is_directed
                                        ? this.t('relationship_types_page.directed')
                                        : this.t('relationship_types_page.undirected')}
                                </span>
                                ${t.inverse_type_id ? html`
                                    <span class="badge">
                                        <platform-icon name="swap" size="10"></platform-icon>
                                        ${t.inverse_type_id}
                                    </span>
                                ` : ''}
                                ${t.weight_default !== null && t.weight_default !== undefined ? html`
                                    <span class="badge">
                                        ${this.t('relationship_types_page.weight')}: ${t.weight_default}
                                    </span>
                                ` : ''}
                            </div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    render() {
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('relationship_types_page.hero_title')}
                subtitle=${this.t('relationship_types_page.hero_subtitle')}
            >
                <button
                    slot="actions"
                    class="btn btn-primary"
                    @click=${this._toggleForm}
                >
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this._showForm
                        ? this.t('relationship_types_page.cancel')
                        : this.t('relationship_types_page.add')}
                </button>
            </page-header>
            <div class="scroll">
                ${this._renderForm()}
                ${this._renderList()}
            </div>
        `;
    }
}

customElements.define('crm-relationship-types-page', CRMRelationshipTypesPage);
