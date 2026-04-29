/**
 * Каталог типов сущностей из шаблонов пространств: карточки (lead, project, …)
 * для копирования определения в новый тип (при выборе подставляется type_id из шаблона, его можно изменить).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED } from '../utils/entity-type-create-events.js';

const FILTER_ALL = '__all__';

const KIND_FILTER_ALL = '__kind_all__';
const KIND_NOTE = 'note';
const KIND_TASK = 'task';
const KIND_ENTITY = 'entity';

const NOTE_FAMILY_TYPE_IDS = new Set(['note', 'meeting', 'call']);
const TASK_ROOT_TYPE_ID = 'task';

function _presetRowKind(typeObj) {
    if (!typeObj || typeof typeObj.type_id !== 'string' || typeObj.type_id.length === 0) {
        throw new Error('CRMEntityTypePresetPickerModal: type snapshot must include type_id');
    }
    const id = typeObj.type_id;
    if (NOTE_FAMILY_TYPE_IDS.has(id)) {
        return KIND_NOTE;
    }
    if (id === TASK_ROOT_TYPE_ID) {
        return KIND_TASK;
    }
    return KIND_ENTITY;
}

function _pickBetterPresetRow(a, b) {
    const pref = (t) => (t.template_id === 'sales' ? 0 : 1);
    const da = pref(a);
    const db = pref(b);
    if (da !== db) {
        return da < db ? a : b;
    }
    if (a.template_id < b.template_id) {
        return a;
    }
    if (a.template_id > b.template_id) {
        return b;
    }
    return a;
}

function _dedupePresetRowsByTypeId(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const bestByType = new Map();
    for (const r of list) {
        if (!r || !r.type || typeof r.type.type_id !== 'string' || r.type.type_id.length === 0) {
            continue;
        }
        const id = r.type.type_id;
        const prev = bestByType.get(id);
        if (prev === undefined) {
            bestByType.set(id, r);
        } else {
            bestByType.set(id, _pickBetterPresetRow(prev, r));
        }
    }
    const firstIdx = new Map();
    for (let i = 0; i < list.length; i++) {
        const r = list[i];
        if (!r || !r.type || typeof r.type.type_id !== 'string' || r.type.type_id.length === 0) {
            continue;
        }
        const id = r.type.type_id;
        if (!firstIdx.has(id)) {
            firstIdx.set(id, i);
        }
    }
    const pairs = [...bestByType.entries()].sort((x, y) => {
        const ix = firstIdx.get(x[0]);
        const iy = firstIdx.get(y[0]);
        return ix - iy;
    });
    return pairs.map(([, row]) => row);
}

function _iconNameForPresetType(typeObj) {
    if (typeObj && typeof typeObj.icon === 'string' && typeObj.icon.trim().length > 0) {
        return typeObj.icon.trim();
    }
    const id = typeObj && typeof typeObj.type_id === 'string' ? typeObj.type_id : '';
    if (NOTE_FAMILY_TYPE_IDS.has(id)) {
        return 'doc-detail';
    }
    if (id === TASK_ROOT_TYPE_ID) {
        return 'checklist';
    }
    return 'layers';
}

export class CRMEntityTypePresetPickerModal extends PlatformModal {
    static modalKind = 'crm.entity_type_preset_picker';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        _filterTemplateId: { state: true },
        _kindFilter: { state: true },
        _selectedKey: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host {
                --modal-width: min(960px, calc(100vw - 24px));
            }
            p.intro {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                margin: 0 0 var(--space-4) 0;
                line-height: 1.45;
                flex-shrink: 0;
            }
            .content-area {
                height: min(70vh, 600px);
                overflow: hidden;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                min-height: 0;
            }
            .shell {
                display: flex;
                gap: var(--space-4);
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }
            .sidebar {
                flex: 0 0 200px;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                border-right: 1px solid var(--glass-border-subtle);
                padding-right: var(--space-3);
                min-width: 0;
                min-height: 0;
                overflow-y: auto;
            }
            .cat-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                width: 100%;
                box-sizing: border-box;
            }
            .cat-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
            }
            .cat-btn.active {
                color: var(--text-primary);
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.1);
            }
            .main {
                flex: 1;
                min-width: 0;
                min-height: 0;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .kind-bar {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .kind-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                box-sizing: border-box;
            }
            .kind-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
            }
            .kind-btn.active {
                color: var(--text-primary);
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.1);
            }
            .main-scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
            }
            .main-scroll .empty {
                min-height: 200px;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
                gap: var(--space-3);
                align-content: start;
            }
            .card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 2px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                text-align: left;
                cursor: pointer;
                font: inherit;
                color: inherit;
                box-sizing: border-box;
            }
            .card:hover {
                border-color: var(--accent);
            }
            .card.selected {
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.12);
            }
            .card-top {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
            }
            .card-title {
                font-weight: 600;
                font-size: var(--text-sm);
                flex: 1;
                min-width: 0;
            }
            .chip-tpl {
                font-size: var(--text-xs);
                padding: 2px 8px;
                border-radius: var(--radius-full);
                background: rgba(255, 255, 255, 0.08);
                color: var(--text-tertiary);
                white-space: nowrap;
            }
            .mono {
                font-family: ui-monospace, monospace;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .card-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
                margin: 0;
            }
            .loading,
            .empty {
                flex: 1;
                min-height: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .main .empty {
                flex: 1;
            }
            .footer-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                width: 100%;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            .btn:hover {
                background: var(--crm-surface-muted, rgba(255, 255, 255, 0.06));
                color: var(--text-primary);
            }
            .btn-primary {
                border-color: var(--accent);
                background: var(--accent);
                color: white;
            }
            .btn-primary:hover:not(:disabled) {
                filter: brightness(1.05);
                color: white;
            }
            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this._filterTemplateId = FILTER_ALL;
        this._kindFilter = KIND_FILTER_ALL;
        this._selectedKey = '';
        this._templates = this.useResource('crm/templates', { autoload: true });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._templates.resource.events.LIST_LOADED, () => {
            this._ensureTemplateDetails();
        });
        this._ensureTemplateDetails();
    }

    firstUpdated() {
        super.firstUpdated();
        this._ensureTemplateDetails();
    }

    _ensureTemplateDetails() {
        const items = Array.isArray(this._templates.items) ? this._templates.items : [];
        for (const row of items) {
            const tid = typeof row.template_id === 'string' ? row.template_id : '';
            if (!tid.length) continue;
            const d = this._templates.byId[tid];
            if (!this._detailReady(d)) {
                this._templates.get(tid);
            }
        }
    }

    _detailReady(detail) {
        return (
            detail !== undefined
            && detail !== null
            && typeof detail === 'object'
            && Array.isArray(detail.types)
        );
    }

    _allDetailsLoaded() {
        const items = Array.isArray(this._templates.items) ? this._templates.items : [];
        if (items.length === 0) {
            return true;
        }
        for (const row of items) {
            const id = typeof row.template_id === 'string' ? row.template_id : '';
            if (!id.length) continue;
            const d = this._templates.byId[id];
            if (!this._detailReady(d)) {
                return false;
            }
        }
        return true;
    }

    _presetRows() {
        const items = Array.isArray(this._templates.items) ? this._templates.items : [];
        const rows = [];
        for (const row of items) {
            const tid = typeof row.template_id === 'string' ? row.template_id : '';
            if (!tid.length) continue;
            const d = this._templates.byId[tid];
            if (!this._detailReady(d)) continue;
            const tname = typeof d.name === 'string' && d.name.length > 0 ? d.name : tid;
            for (const typ of d.types) {
                if (!typ || typeof typ.type_id !== 'string' || typ.type_id.length === 0) continue;
                rows.push({
                    key: `${tid}\u0000${typ.type_id}`,
                    template_id: tid,
                    template_name: tname,
                    type: typ,
                });
            }
        }
        return rows;
    }

    _rowsAfterTemplateFilter() {
        const all = this._presetRows();
        if (this._filterTemplateId === FILTER_ALL) {
            return _dedupePresetRowsByTypeId(all);
        }
        return all.filter((r) => r.template_id === this._filterTemplateId);
    }

    _syncSelectionWithVisibleRows(visibleRows) {
        const rows = Array.isArray(visibleRows) ? visibleRows : [];
        const sel = this._selectedKey;
        if (typeof sel !== 'string' || sel.length === 0) {
            return;
        }
        const still = rows.some((r) => r.key === sel);
        if (!still) {
            this._selectedKey = '';
        }
    }

    _filteredRows() {
        const byTpl = this._rowsAfterTemplateFilter();
        if (this._kindFilter === KIND_FILTER_ALL) {
            return byTpl;
        }
        return byTpl.filter((r) => _presetRowKind(r.type) === this._kindFilter);
    }

    _sidebarTemplateIds() {
        const items = Array.isArray(this._templates.items) ? this._templates.items : [];
        return items
            .map((row) => (typeof row.template_id === 'string' ? row.template_id : ''))
            .filter((id) => id.length > 0);
    }

    _templateLabel(templateId) {
        const d = this._templates.byId[templateId];
        if (d && typeof d.name === 'string' && d.name.length > 0) {
            return d.name;
        }
        return templateId;
    }

    _selectCard(key) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('CRMEntityTypePresetPickerModal._selectCard: key required');
        }
        this._selectedKey = key;
    }

    _selectedSnapshot() {
        const key = this._selectedKey;
        if (typeof key !== 'string' || key.length === 0) {
            return null;
        }
        const rows = this._presetRows();
        const row = rows.find((r) => r.key === key);
        if (!row || !row.type || typeof row.type !== 'object') {
            return null;
        }
        return row.type;
    }

    _done() {
        const snap = this._selectedSnapshot();
        if (!snap) {
            this.toast('crm:entity_type_preset_picker_modal.pick_first', { type: 'warning' });
            return;
        }
        this.dispatch(CRM_ENTITY_TYPE_PRESET_PICKER_APPLIED, { type_snapshot: snap });
        this.close();
    }

    _emptyMessage() {
        const total = this._presetRows().length;
        if (this._filterTemplateId === FILTER_ALL && total === 0) {
            return this.t('entity_type_preset_picker_modal.empty_no_presets');
        }
        const byTpl = this._rowsAfterTemplateFilter();
        if (byTpl.length > 0 && this._filteredRows().length === 0) {
            return this.t('entity_type_preset_picker_modal.empty_no_kind_match');
        }
        if (byTpl.length === 0 && this._filterTemplateId !== FILTER_ALL) {
            return this.t('entity_type_preset_picker_modal.empty_no_types');
        }
        return this.t('entity_type_preset_picker_modal.empty_no_types');
    }

    renderHeader() {
        return this.t('entity_type_preset_picker_modal.title');
    }

    renderBody() {
        const list = Array.isArray(this._templates.items) ? this._templates.items : [];
        const loading = list.length > 0 && !this._allDetailsLoaded();

        if (this._templates.loading && list.length === 0) {
            return html`
                <div class="content-area">
                    <div class="loading">
                        <glass-spinner></glass-spinner>
                    </div>
                </div>
            `;
        }

        if (list.length === 0) {
            return html`
                <div class="content-area">
                    <div class="empty">${this.t('entity_type_preset_picker_modal.empty_no_templates')}</div>
                </div>
            `;
        }

        if (loading) {
            return html`
                <p class="intro">${this.t('entity_type_preset_picker_modal.intro')}</p>
                <div class="content-area">
                    <div class="loading">
                        <glass-spinner></glass-spinner>
                    </div>
                </div>
            `;
        }

        const filtered = this._filteredRows();
        const tplIds = this._sidebarTemplateIds();

        return html`
            <p class="intro">${this.t('entity_type_preset_picker_modal.intro')}</p>
            <div class="content-area">
                <div class="shell">
                    <nav class="sidebar" aria-label=${this.t('entity_type_preset_picker_modal.sidebar_aria')}>
                        <button
                            type="button"
                            class="cat-btn ${this._filterTemplateId === FILTER_ALL ? 'active' : ''}"
                            @click=${() => {
                                this._filterTemplateId = FILTER_ALL;
                                this._syncSelectionWithVisibleRows(this._filteredRows());
                            }}
                        >
                            ${this.t('entity_type_preset_picker_modal.filter_all')}
                        </button>
                        ${tplIds.map(
                            (tid) => html`
                                <button
                                    type="button"
                                    class="cat-btn ${this._filterTemplateId === tid ? 'active' : ''}"
                                    @click=${() => {
                                        this._filterTemplateId = tid;
                                        this._syncSelectionWithVisibleRows(this._filteredRows());
                                    }}
                                >
                                    ${this._templateLabel(tid)}
                                </button>
                            `,
                        )}
                    </nav>
                    <div class="main">
                        <div
                            class="kind-bar"
                            role="tablist"
                            aria-label=${this.t('entity_type_preset_picker_modal.kind_bar_aria')}
                        >
                            <button
                                type="button"
                                role="tab"
                                class="kind-btn ${this._kindFilter === KIND_FILTER_ALL ? 'active' : ''}"
                                @click=${() => {
                                    this._kindFilter = KIND_FILTER_ALL;
                                    this._syncSelectionWithVisibleRows(this._filteredRows());
                                }}
                            >
                                ${this.t('entity_type_preset_picker_modal.filter_kind_all')}
                            </button>
                            <button
                                type="button"
                                role="tab"
                                class="kind-btn ${this._kindFilter === KIND_NOTE ? 'active' : ''}"
                                @click=${() => {
                                    this._kindFilter = KIND_NOTE;
                                    this._syncSelectionWithVisibleRows(this._filteredRows());
                                }}
                            >
                                ${this.t('entity_type_preset_picker_modal.filter_kind_note')}
                            </button>
                            <button
                                type="button"
                                role="tab"
                                class="kind-btn ${this._kindFilter === KIND_TASK ? 'active' : ''}"
                                @click=${() => {
                                    this._kindFilter = KIND_TASK;
                                    this._syncSelectionWithVisibleRows(this._filteredRows());
                                }}
                            >
                                ${this.t('entity_type_preset_picker_modal.filter_kind_task')}
                            </button>
                            <button
                                type="button"
                                role="tab"
                                class="kind-btn ${this._kindFilter === KIND_ENTITY ? 'active' : ''}"
                                @click=${() => {
                                    this._kindFilter = KIND_ENTITY;
                                    this._syncSelectionWithVisibleRows(this._filteredRows());
                                }}
                            >
                                ${this.t('entity_type_preset_picker_modal.filter_kind_entity')}
                            </button>
                        </div>
                        <div class="main-scroll">
                            ${filtered.length === 0
                                ? html`<div class="empty">${this._emptyMessage()}</div>`
                                : html`
                                      <div class="grid">
                                          ${filtered.map((r) => {
                                              const typ = r.type;
                                              const name =
                                                  typeof typ.name === 'string' && typ.name.length > 0
                                                      ? typ.name
                                                      : typ.type_id;
                                              const desc =
                                                  typeof typ.description === 'string' &&
                                                  typ.description.length > 0
                                                      ? typ.description
                                                      : this.t('entity_type_preset_picker_modal.no_description');
                                              const selected = this._selectedKey === r.key;
                                              const iconName = _iconNameForPresetType(typ);
                                              return html`
                                                  <button
                                                      type="button"
                                                      class="card ${selected ? 'selected' : ''}"
                                                      @click=${() => this._selectCard(r.key)}
                                                  >
                                                      <div class="card-top">
                                                          <platform-icon
                                                              name=${iconName}
                                                              size="18"
                                                          ></platform-icon>
                                                          <span class="card-title">${name}</span>
                                                          <span class="chip-tpl">${r.template_name}</span>
                                                      </div>
                                                      <div class="mono">${typ.type_id}</div>
                                                      <p class="card-desc">${desc}</p>
                                                  </button>
                                              `;
                                          })}
                                      </div>
                                  `}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderFooter() {
        const hasSelection = typeof this._selectedKey === 'string' && this._selectedKey.length > 0;
        return html`
            <div class="footer-actions">
                <button type="button" class="btn" @click=${() => this.close()}>
                    ${this.t('entity_type_preset_picker_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary" ?disabled=${!hasSelection} @click=${() => this._done()}>
                    ${this.t('entity_type_preset_picker_modal.done')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-entity-type-preset-picker-modal', CRMEntityTypePresetPickerModal);
registerModalKind(CRMEntityTypePresetPickerModal.modalKind, 'crm-entity-type-preset-picker-modal');
