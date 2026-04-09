import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

const PALETTE = [
    '#007aff', '#5856d6', '#34c759', '#ff9500', '#ff3b30',
    '#af52de', '#00c7be', '#ff2d55', '#5ac8fa', '#ffcc00',
];

export class RelationshipTypesPage extends PlatformElement {
    static properties = {
        _types: { state: true },
        _loading: { state: true },
        _showCreateForm: { state: true },
        _createDraft: { state: true },
        _createSaving: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container {
                display: flex; flex-direction: column; gap: var(--space-4);
                height: 100%; overflow-y: auto; overflow-x: hidden;
                padding: var(--space-2); box-sizing: border-box;
            }
            .section {
                background: var(--crm-surface); border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl); padding: var(--space-4);
                display: flex; flex-direction: column; gap: var(--space-3);
            }
            .hero { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .hero-subtitle { color: var(--text-secondary); font-size: var(--text-sm); }
            .back-btn { display: inline-flex; align-items: center; gap: var(--space-2); background: none; border: none; color: var(--text-secondary); font-size: var(--text-sm); cursor: pointer; padding: 0; }
            .back-btn:hover { color: var(--text-primary); }
            .type-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); }
            .type-card {
                border: 1px solid var(--crm-stroke); border-radius: var(--radius-lg);
                padding: var(--space-4); background: var(--crm-surface-muted);
                display: flex; flex-direction: column; gap: var(--space-2);
            }
            .type-header { display: flex; align-items: center; gap: var(--space-2); }
            .type-color {
                width: 10px; height: 10px; border-radius: var(--radius-full);
                flex-shrink: 0;
            }
            .type-name { font-size: var(--text-sm); font-weight: 600; color: var(--text-primary); }
            .type-id { font-size: var(--text-xs); color: var(--text-tertiary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
            .type-meta { font-size: var(--text-xs); color: var(--text-secondary); display: flex; gap: var(--space-3); flex-wrap: wrap; }
            .badge {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px 8px; border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle); color: var(--text-secondary);
            }
            .badge.system { background: rgba(255,149,0,0.15); color: #ff9500; }
            .type-desc { font-size: var(--text-sm); color: var(--text-secondary); }
            .empty { text-align: center; padding: var(--space-6); color: var(--text-tertiary); font-size: var(--text-sm); }
            .save-btn {
                display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
                border: 1px solid var(--accent); background: var(--accent);
                color: var(--platform-btn-primary-text); border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content;
            }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-1); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .form-input, .form-textarea {
                border: 1px solid var(--crm-stroke); border-radius: var(--radius-md);
                background: var(--crm-surface-elevated); color: var(--text-primary);
                padding: var(--space-2) var(--space-3); font-size: var(--text-sm);
            }
            .form-textarea { min-height: 60px; resize: vertical; }
            .form-checkbox { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; }
            .form-checkbox input { accent-color: var(--accent); }
            .form-footer { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .palette { display: flex; gap: var(--space-1); flex-wrap: wrap; }
            .palette-dot {
                width: 20px; height: 20px; border-radius: var(--radius-full);
                border: 2px solid transparent; cursor: pointer;
            }
            .palette-dot.active { border-color: var(--text-primary); }
            @media (max-width: 767px) { .type-grid, .form-grid { grid-template-columns: 1fr; } }
        `,
    ];

    constructor() {
        super();
        this._types = [];
        this._loading = false;
        this._showCreateForm = false;
        this._createDraft = RelationshipTypesPage._defaultDraft();
        this._createSaving = false;
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._types = state.entities.relationshipTypes || [];
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    static _defaultDraft() {
        return {
            type_id: '',
            name: '',
            description: '',
            is_directed: true,
            inverse_type_id: '',
            icon: '',
            color: '',
            weight_default: 1.0,
        };
    }

    async firstUpdated() {
        this._loading = true;
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadRelationshipTypes(crmApi);
        this._loading = false;
    }

    _updateDraft(field, value) {
        this._createDraft = { ...this._createDraft, [field]: value };
    }

    async _onCreate() {
        const draft = this._createDraft;
        if (!draft.type_id.trim()) {
            this.warning(this.i18n.t('relationship_types_page.err_type_id_required'));
            return;
        }
        if (!draft.name.trim()) {
            this.warning(this.i18n.t('relationship_types_page.err_name_required'));
            return;
        }
        this._createSaving = true;
        try {
            const crmApi = this.services.get('crmApi');
            await crmApi.createRelationshipType({
                type_id: draft.type_id.trim(),
                name: draft.name.trim(),
                description: draft.description.trim() || null,
                is_directed: draft.is_directed,
                inverse_type_id: draft.inverse_type_id.trim() || null,
                icon: draft.icon.trim() || null,
                color: draft.color.trim() || null,
                weight_default: Number(draft.weight_default) || 1.0,
            });
            await CRMStore.loadRelationshipTypes(crmApi);
            this._showCreateForm = false;
            this._createDraft = RelationshipTypesPage._defaultDraft();
            this.success(this.i18n.t('relationship_types_page.success_created'));
        } catch (err) {
            this.error(err instanceof Error ? err.message : this.i18n.t('relationship_types_page.err_create'));
        } finally {
            this._createSaving = false;
        }
    }

    _renderCreateForm() {
        if (!this._showCreateForm) return '';
        const d = this._createDraft;
        return html`
            <div class="section">
                <div class="hero-title">
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.i18n.t('relationship_types_page.form_title')}
                </div>
                <div class="form-grid">
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_type_id')} *</label>
                        <input class="form-input" .value=${d.type_id} @input=${(e) => this._updateDraft('type_id', e.target.value)} placeholder="e.g. works_for" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_name')} *</label>
                        <input class="form-input" .value=${d.name} @input=${(e) => this._updateDraft('name', e.target.value)} />
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_description')}</label>
                        <textarea class="form-textarea" .value=${d.description} @input=${(e) => this._updateDraft('description', e.target.value)}></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_inverse')}</label>
                        <input class="form-input" .value=${d.inverse_type_id} @input=${(e) => this._updateDraft('inverse_type_id', e.target.value)} placeholder="e.g. employed_by" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_weight')}</label>
                        <input class="form-input" type="number" step="0.1" min="0" .value=${String(d.weight_default)} @input=${(e) => this._updateDraft('weight_default', e.target.value)} />
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('relationship_types_page.label_color')}</label>
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
                    <div class="form-group">
                        <label class="form-checkbox">
                            <input type="checkbox" .checked=${d.is_directed} @change=${(e) => this._updateDraft('is_directed', e.target.checked)} />
                            ${this.i18n.t('relationship_types_page.label_directed')}
                        </label>
                    </div>
                </div>
                <div class="form-footer">
                    <button class="save-btn" ?disabled=${this._createSaving} @click=${this._onCreate}>
                        <platform-icon name="check" size="14"></platform-icon>
                        ${this._createSaving ? this.i18n.t('relationship_types_page.saving') : this.i18n.t('relationship_types_page.create')}
                    </button>
                    <button class="save-btn soft-btn" @click=${() => { this._showCreateForm = false; }}>
                        ${this.i18n.t('relationship_types_page.cancel')}
                    </button>
                </div>
            </div>
        `;
    }

    render() {
        return html`
            <div class="container">
                <div class="section">
                    <button class="back-btn" @click=${() => CRMStore.setCurrentView('settings')}>
                        <platform-icon name="arrow-left" size="14"></platform-icon>
                        ${this.i18n.t('relationship_types_page.back')}
                    </button>
                    <div class="hero">
                        <div>
                            <div class="hero-title">
                                <platform-icon name="link" size="18"></platform-icon>
                                ${this.i18n.t('relationship_types_page.hero_title')}
                            </div>
                            <div class="hero-subtitle">${this.i18n.t('relationship_types_page.hero_subtitle')}</div>
                        </div>
                        ${!this._showCreateForm ? html`
                            <button class="save-btn" @click=${() => { this._showCreateForm = true; }}>
                                <platform-icon name="plus" size="14"></platform-icon>
                                ${this.i18n.t('relationship_types_page.add')}
                            </button>
                        ` : ''}
                    </div>
                </div>

                ${this._renderCreateForm()}

                <div class="section">
                    ${this._loading ? html`<div class="empty">${this.i18n.t('relationship_types_page.loading')}</div>` : ''}
                    ${!this._loading && this._types.length === 0 ? html`<div class="empty">${this.i18n.t('relationship_types_page.empty')}</div>` : ''}
                    ${!this._loading && this._types.length > 0 ? html`
                        <div class="type-grid">
                            ${this._types.map((t) => html`
                                <div class="type-card">
                                    <div class="type-header">
                                        ${t.color ? html`<div class="type-color" style="background:${t.color}"></div>` : ''}
                                        <span class="type-name">${t.name}</span>
                                        ${t.is_system ? html`<span class="badge system">${this.i18n.t('relationship_types_page.system')}</span>` : ''}
                                    </div>
                                    <div class="type-id">${t.type_id}</div>
                                    ${t.description ? html`<div class="type-desc">${t.description}</div>` : ''}
                                    <div class="type-meta">
                                        <span class="badge">
                                            <platform-icon name="${t.is_directed ? 'arrow-right' : 'link'}" size="10"></platform-icon>
                                            ${t.is_directed
                                                ? this.i18n.t('relationship_types_page.directed')
                                                : this.i18n.t('relationship_types_page.undirected')}
                                        </span>
                                        ${t.inverse_type_id ? html`
                                            <span class="badge">
                                                <platform-icon name="swap" size="10"></platform-icon>
                                                ${t.inverse_type_id}
                                            </span>
                                        ` : ''}
                                        ${t.weight_default != null ? html`
                                            <span class="badge">
                                                ${this.i18n.t('relationship_types_page.weight')}: ${t.weight_default}
                                            </span>
                                        ` : ''}
                                    </div>
                                </div>
                            `)}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('relationship-types-page', RelationshipTypesPage);
