/**
 * CRMEntityMergeModal — слияние двух сущностей в одну.
 *
 * Свойства:
 *   - entityIdA: string — первая сущность (обязательно).
 *   - entityIdB: string — вторая сущность (обязательно, != entityIdA).
 *
 * Поток:
 *   1. На open: `entitiesResource.get(entityIdA)` и `.get(entityIdB)` параллельно;
 *      сами entity читаются из `_entities.byId[id]` после ITEM_LOADED.
 *   2. UI разделён на две колонки. Левая (survivor) сохраняется, правая (source) удаляется.
 *      Кнопка swap меняет survivor/source местами.
 *   3. Превью полей из `_MERGE_SCALAR_KEYS` (name, description, status, entity_subtype,
 *      priority, note_date, due_date) и объединённых ключей `attributes`. Для каждого
 *      конфликтного поля показывается выбор `survivor | source` (radio).
 *   4. Tags объединяются автоматически (union на бэкенде).
 *   5. Локальная валидация перед сабмитом:
 *        - survivor_id != source_id;
 *        - survivor.namespace == source.namespace;
 *        - не оба `note`;
 *        - все конфликты разрешены.
 *   6. Сабмит: `entityMergeOp.run({ survivor_entity_id, source_entity_id,
 *      scalar_choices, attribute_choices })`.
 *   7. На SUCCEEDED — close(); список и граф подписаны на `crm/entity_merge/succeeded`
 *      и сами рефрешат данные.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const MERGE_OP_NAME = 'crm/entity_merge';

const SCALAR_FIELDS = [
    { key: 'name', labelKey: 'entity_merge_modal.field_name' },
    { key: 'description', labelKey: 'entity_merge_modal.field_description' },
    { key: 'status', labelKey: 'entity_merge_modal.field_status' },
    { key: 'entity_subtype', labelKey: 'entity_merge_modal.field_entity_subtype' },
    { key: 'note_date', labelKey: 'entity_merge_modal.field_note_date' },
];

function _canonical(value) {
    return JSON.stringify(value === undefined ? null : value);
}

function _isEmpty(value) {
    if (value === null || value === undefined) return true;
    if (typeof value === 'string' && value.length === 0) return true;
    if (Array.isArray(value) && value.length === 0) return true;
    if (typeof value === 'object' && Object.keys(value).length === 0) return true;
    return false;
}

export class CRMEntityMergeModal extends PlatformModal {
    static modalKind = 'crm.entity_merge';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        entityIdA: { type: String },
        entityIdB: { type: String },
        _swapped: { state: true },
        _scalarChoices: { state: true },
        _attrChoices: { state: true },
        _submitFailedMessage: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .body {
                display: grid;
                gap: var(--space-5);
                padding: var(--space-2) 0;
            }
            .loading-block {
                padding: var(--space-6);
                display: flex;
                justify-content: center;
            }
            .error-block {
                padding: var(--space-4);
                color: var(--color-danger);
                text-align: center;
                font-size: var(--text-sm);
            }
            .warning {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-md);
                background: rgba(220, 38, 38, 0.08);
                border: 1px solid rgba(220, 38, 38, 0.25);
                color: var(--color-danger);
            }
            .warning .text { display: grid; gap: 2px; }
            .warning .title { font-weight: 600; font-size: var(--text-sm); }
            .warning .desc { font-size: var(--text-xs); color: var(--text-secondary); }

            .sides {
                display: grid;
                grid-template-columns: 1fr auto 1fr;
                gap: var(--space-3);
                align-items: stretch;
            }
            .side {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-width: 0;
            }
            .side.survivor {
                border-color: var(--accent);
                background: var(--crm-selected-bg);
            }
            .side .role {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .side.survivor .role { color: var(--accent); }
            .side.source .role { color: var(--color-danger); }
            .side .name {
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .side .meta {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .side .meta .badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px var(--space-2);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
            }
            .swap-col {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .swap-btn {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .swap-btn:hover { background: var(--crm-selected-bg); border-color: var(--accent); }
            .swap-btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .section-title {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                padding-top: var(--space-2);
                border-top: 1px solid var(--crm-stroke);
            }

            .field-row {
                display: grid;
                grid-template-columns: 180px 1fr 1fr;
                gap: var(--space-2);
                align-items: stretch;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
            }
            .field-row.conflict {
                border-color: rgba(234, 179, 8, 0.5);
                background: rgba(234, 179, 8, 0.06);
            }
            .field-row .label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-weight: 500;
                align-self: center;
            }
            .field-row .label .conflict-tag {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                margin-left: var(--space-1);
                padding: 1px var(--space-1);
                font-size: 10px;
                color: rgb(180, 130, 0);
                background: rgba(234, 179, 8, 0.18);
                border-radius: var(--radius-sm);
            }
            .opt {
                display: grid;
                gap: 2px;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
                min-width: 0;
                word-break: break-word;
            }
            .opt.picked {
                border-color: var(--accent);
                box-shadow: 0 0 0 1px var(--accent) inset;
                background: var(--crm-selected-bg);
            }
            .opt.disabled {
                opacity: 0.55;
                cursor: not-allowed;
            }
            .opt .side-tag {
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-tertiary);
            }
            .opt.picked .side-tag { color: var(--accent); }
            .opt .value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: pre-wrap;
            }
            .opt .empty { color: var(--text-tertiary); font-style: italic; }

            .single-value {
                grid-column: 2 / span 2;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: pre-wrap;
            }
            .single-value.empty { color: var(--text-tertiary); font-style: italic; }

            .empty-section {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }

            .tags-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
            }
            .tag-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-primary);
            }
            .tag-empty { color: var(--text-tertiary); font-size: var(--text-xs); font-style: italic; }
            .tag-hint { color: var(--text-tertiary); font-size: var(--text-xs); margin-top: var(--space-1); }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .footer-actions .submit-error {
                margin-right: auto;
                color: var(--color-danger);
                font-size: var(--text-sm);
                align-self: center;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.headerSavePrimary = true;
        this.entityIdA = '';
        this.entityIdB = '';

        this._swapped = false;
        this._scalarChoices = {};
        this._attrChoices = {};
        this._submitFailedMessage = '';

        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME);
        this._mergeOp = this.useOp(MERGE_OP_NAME);

        this._loadedIds = new Set();
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.entityIdA !== 'string' || this.entityIdA.length === 0) {
            throw new Error('CRMEntityMergeModal: prop "entityIdA" required');
        }
        if (typeof this.entityIdB !== 'string' || this.entityIdB.length === 0) {
            throw new Error('CRMEntityMergeModal: prop "entityIdB" required');
        }
        if (this.entityIdA === this.entityIdB) {
            throw new Error('CRMEntityMergeModal: entityIdA == entityIdB');
        }

        this.useEvent(this._entities.resource.events.ITEM_LOADED, (event) => {
            const id = event && event.payload && event.payload.item && event.payload.item.entity_id;
            if (typeof id === 'string') this._loadedIds.add(id);
        });
        this.useEvent(this._mergeOp.op.events.SUCCEEDED, () => this.close());
        this.useEvent(this._mergeOp.op.events.FAILED, (event) => {
            const message = event && event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : this.t('entity_merge_modal.submit_failed');
            this._submitFailedMessage = message;
        });

        this._entities.get(this.entityIdA);
        this._entities.get(this.entityIdB);
        if (this._entityTypes.items.length === 0) this._entityTypes.load(null);
    }

    _entityById(id) {
        const item = this._entities.byId[id];
        return item === undefined ? null : item;
    }

    _survivorId() { return this._swapped ? this.entityIdB : this.entityIdA; }
    _sourceId() { return this._swapped ? this.entityIdA : this.entityIdB; }

    _typeName(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) return '';
        for (const t of this._entityTypes.items) {
            if (t.type_id === typeId) return t.name;
        }
        return typeId;
    }

    _bothLoaded() {
        return this._entityById(this.entityIdA) !== null && this._entityById(this.entityIdB) !== null;
    }

    _validateForSubmit(survivor, source) {
        if (survivor.entity_id === source.entity_id) {
            return this.t('entity_merge_modal.same_id_error');
        }
        if (survivor.namespace !== source.namespace) {
            return this.t('entity_merge_modal.namespace_mismatch');
        }
        if (survivor.entity_type === 'note' && source.entity_type === 'note') {
            return this.t('entity_merge_modal.both_notes_error');
        }
        for (const { key } of SCALAR_FIELDS) {
            const av = survivor[key];
            const bv = source[key];
            if (_canonical(av) !== _canonical(bv)) {
                if (this._scalarChoices[key] !== 'survivor' && this._scalarChoices[key] !== 'source') {
                    return this.t('entity_merge_modal.choice_required');
                }
            }
        }
        const sa = survivor.attributes && typeof survivor.attributes === 'object' ? survivor.attributes : {};
        const sb = source.attributes && typeof source.attributes === 'object' ? source.attributes : {};
        const allKeys = new Set([...Object.keys(sa), ...Object.keys(sb)]);
        for (const k of allKeys) {
            const inA = k in sa;
            const inB = k in sb;
            if (inA && inB && _canonical(sa[k]) !== _canonical(sb[k])) {
                if (this._attrChoices[k] !== 'survivor' && this._attrChoices[k] !== 'source') {
                    return this.t('entity_merge_modal.choice_required');
                }
            }
        }
        return null;
    }

    _onSwap() {
        this._swapped = !this._swapped;
        this._scalarChoices = {};
        this._attrChoices = {};
        this._submitFailedMessage = '';
    }

    _onPickScalar(key, side) {
        this._scalarChoices = { ...this._scalarChoices, [key]: side };
        this._submitFailedMessage = '';
    }

    _onPickAttr(key, side) {
        this._attrChoices = { ...this._attrChoices, [key]: side };
        this._submitFailedMessage = '';
    }

    _onSubmit() {
        if (!this._bothLoaded()) return;
        const survivor = this._entityById(this._survivorId());
        const source = this._entityById(this._sourceId());
        const error = this._validateForSubmit(survivor, source);
        if (typeof error === 'string') {
            this._submitFailedMessage = error;
            return;
        }
        this._submitFailedMessage = '';
        this._mergeOp.run({
            survivor_entity_id: survivor.entity_id,
            source_entity_id: source.entity_id,
            scalar_choices: { ...this._scalarChoices },
            attribute_choices: { ...this._attrChoices },
        });
    }

    renderHeader() {
        return this.t('entity_merge_modal.header');
    }

    renderSaveHeaderButton() {
        const ready = this._bothLoaded() && !this._mergeOp.busy;
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSubmit(),
            disabled: !ready,
            title: this._mergeOp.busy
                ? this.t('entity_merge_modal.submitting')
                : this.t('entity_merge_modal.submit'),
        });
    }

    _formatValue(value) {
        if (_isEmpty(value)) {
            return html`<span class="empty">${this.t('entity_merge_modal.value_empty')}</span>`;
        }
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            return html`<span class="value">${String(value)}</span>`;
        }
        return html`<span class="value">${JSON.stringify(value)}</span>`;
    }

    _renderSide(role, entity) {
        if (entity === null) {
            return html`
                <div class="side ${role}">
                    <div class="role">${this.t(`entity_merge_modal.${role}`)}</div>
                    <glass-spinner></glass-spinner>
                </div>
            `;
        }
        const typeName = this._typeName(entity.entity_type);
        return html`
            <div class="side ${role}">
                <div class="role">
                    <platform-icon
                        name=${role === 'survivor' ? 'check' : 'trash'}
                        size="12"
                    ></platform-icon>
                    ${this.t(`entity_merge_modal.${role}`)}
                </div>
                <div class="name">${entity.name}</div>
                <div class="meta">
                    <span class="badge">
                        <platform-icon name="folder" size="10"></platform-icon>
                        ${entity.namespace}
                    </span>
                    <span class="badge">
                        <platform-icon name="tag" size="10"></platform-icon>
                        ${typeName}
                    </span>
                    <span class="badge">
                        <platform-icon name="tag" size="10"></platform-icon>
                        ${entity.entity_id}
                    </span>
                </div>
            </div>
        `;
    }

    _renderScalarRow(field, survivor, source) {
        const av = survivor[field.key];
        const bv = source[field.key];
        const isConflict = _canonical(av) !== _canonical(bv);
        if (!isConflict) {
            const label = this.t(field.labelKey);
            const valueEmpty = _isEmpty(av);
            return html`
                <div class="field-row">
                    <div class="label">${label}</div>
                    <div class="single-value ${valueEmpty ? 'empty' : ''}">
                        ${this._formatValue(av)}
                    </div>
                </div>
            `;
        }
        const picked = this._scalarChoices[field.key];
        return html`
            <div class="field-row conflict">
                <div class="label">
                    ${this.t(field.labelKey)}
                    <span class="conflict-tag">${this.t('entity_merge_modal.conflict_tag')}</span>
                </div>
                <button
                    type="button"
                    class="opt ${picked === 'survivor' ? 'picked' : ''}"
                    @click=${() => this._onPickScalar(field.key, 'survivor')}
                >
                    <span class="side-tag">${this.t('entity_merge_modal.survivor')}</span>
                    ${this._formatValue(av)}
                </button>
                <button
                    type="button"
                    class="opt ${picked === 'source' ? 'picked' : ''}"
                    @click=${() => this._onPickScalar(field.key, 'source')}
                >
                    <span class="side-tag">${this.t('entity_merge_modal.source')}</span>
                    ${this._formatValue(bv)}
                </button>
            </div>
        `;
    }

    _renderAttributeRow(key, survivor, source) {
        const sa = survivor.attributes && typeof survivor.attributes === 'object' ? survivor.attributes : {};
        const sb = source.attributes && typeof source.attributes === 'object' ? source.attributes : {};
        const inA = key in sa;
        const inB = key in sb;
        if (inA && !inB) {
            return html`
                <div class="field-row">
                    <div class="label">${key}</div>
                    <div class="single-value">${this._formatValue(sa[key])}</div>
                </div>
            `;
        }
        if (!inA && inB) {
            return html`
                <div class="field-row">
                    <div class="label">${key}</div>
                    <div class="single-value">${this._formatValue(sb[key])}</div>
                </div>
            `;
        }
        const av = sa[key];
        const bv = sb[key];
        if (_canonical(av) === _canonical(bv)) {
            return html`
                <div class="field-row">
                    <div class="label">${key}</div>
                    <div class="single-value">${this._formatValue(av)}</div>
                </div>
            `;
        }
        const picked = this._attrChoices[key];
        return html`
            <div class="field-row conflict">
                <div class="label">
                    ${key}
                    <span class="conflict-tag">${this.t('entity_merge_modal.conflict_tag')}</span>
                </div>
                <button
                    type="button"
                    class="opt ${picked === 'survivor' ? 'picked' : ''}"
                    @click=${() => this._onPickAttr(key, 'survivor')}
                >
                    <span class="side-tag">${this.t('entity_merge_modal.survivor')}</span>
                    ${this._formatValue(av)}
                </button>
                <button
                    type="button"
                    class="opt ${picked === 'source' ? 'picked' : ''}"
                    @click=${() => this._onPickAttr(key, 'source')}
                >
                    <span class="side-tag">${this.t('entity_merge_modal.source')}</span>
                    ${this._formatValue(bv)}
                </button>
            </div>
        `;
    }

    _renderTags(survivor, source) {
        const a = Array.isArray(survivor.tags) ? survivor.tags : [];
        const b = Array.isArray(source.tags) ? source.tags : [];
        const merged = [];
        const seen = new Set();
        for (const t of [...a, ...b]) {
            if (typeof t !== 'string' || t.length === 0 || seen.has(t)) continue;
            seen.add(t);
            merged.push(t);
        }
        if (merged.length === 0) {
            return html`<div class="tags-row"><span class="tag-empty">${this.t('entity_merge_modal.tags_empty')}</span></div>`;
        }
        return html`
            <div class="tags-row">
                ${merged.map((tag) => html`<span class="tag-chip">${tag}</span>`)}
            </div>
            <div class="tag-hint">${this.t('entity_merge_modal.tags_union_hint')}</div>
        `;
    }

    renderBody() {
        const survivorEntity = this._entityById(this._survivorId());
        const sourceEntity = this._entityById(this._sourceId());

        if (survivorEntity === null || sourceEntity === null) {
            return html`<div class="loading-block"><glass-spinner></glass-spinner></div>`;
        }

        const sameNamespace = survivorEntity.namespace === sourceEntity.namespace;
        const bothNotes = survivorEntity.entity_type === 'note' && sourceEntity.entity_type === 'note';

        const conflictRows = [];
        const ok_rows = [];
        for (const field of SCALAR_FIELDS) {
            const isConflict = _canonical(survivorEntity[field.key]) !== _canonical(sourceEntity[field.key]);
            const html_row = this._renderScalarRow(field, survivorEntity, sourceEntity);
            if (isConflict) conflictRows.push(html_row); else ok_rows.push(html_row);
        }

        const sa = survivorEntity.attributes && typeof survivorEntity.attributes === 'object' ? survivorEntity.attributes : {};
        const sb = sourceEntity.attributes && typeof sourceEntity.attributes === 'object' ? sourceEntity.attributes : {};
        const allAttrKeys = Array.from(new Set([...Object.keys(sa), ...Object.keys(sb)])).sort();
        const attrConflictRows = [];
        const attrOkRows = [];
        for (const k of allAttrKeys) {
            const inA = k in sa;
            const inB = k in sb;
            const isConflict = inA && inB && _canonical(sa[k]) !== _canonical(sb[k]);
            const row_html = this._renderAttributeRow(k, survivorEntity, sourceEntity);
            if (isConflict) attrConflictRows.push(row_html); else attrOkRows.push(row_html);
        }

        return html`
            <div class="body">
                <div class="warning">
                    <platform-icon name="alert" size="16"></platform-icon>
                    <div class="text">
                        <span class="title">${this.t('entity_merge_modal.warning_title')}</span>
                        <span class="desc">${this.t('entity_merge_modal.warning_destructive')}</span>
                    </div>
                </div>

                ${!sameNamespace
                    ? html`<div class="error-block">${this.t('entity_merge_modal.namespace_mismatch')}</div>`
                    : nothing}
                ${bothNotes
                    ? html`<div class="error-block">${this.t('entity_merge_modal.both_notes_error')}</div>`
                    : nothing}

                <div class="sides">
                    ${this._renderSide('survivor', survivorEntity)}
                    <div class="swap-col">
                        <button
                            type="button"
                            class="swap-btn"
                            title=${this.t('entity_merge_modal.swap')}
                            @click=${() => this._onSwap()}
                            ?disabled=${this._mergeOp.busy}
                        >
                            <platform-icon name="swap" size="16"></platform-icon>
                        </button>
                    </div>
                    ${this._renderSide('source', sourceEntity)}
                </div>

                <div class="section-title">${this.t('entity_merge_modal.section_fields')}</div>
                ${conflictRows.length === 0 && ok_rows.length === 0
                    ? html`<div class="empty-section">${this.t('entity_merge_modal.no_fields')}</div>`
                    : html`${conflictRows}${ok_rows}`}

                <div class="section-title">${this.t('entity_merge_modal.section_attributes')}</div>
                ${attrConflictRows.length === 0 && attrOkRows.length === 0
                    ? html`<div class="empty-section">${this.t('entity_merge_modal.no_attributes')}</div>`
                    : html`${attrConflictRows}${attrOkRows}`}

                <div class="section-title">${this.t('entity_merge_modal.section_tags')}</div>
                ${this._renderTags(survivorEntity, sourceEntity)}
            </div>
        `;
    }

    renderFooter() {
        const ready = this._bothLoaded() && !this._mergeOp.busy;
        return html`
            <div class="footer-actions">
                ${this._submitFailedMessage.length > 0
                    ? html`<span class="submit-error">${this._submitFailedMessage}</span>`
                    : nothing}
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                    ?disabled=${this._mergeOp.busy}
                >
                    ${this.t('entity_merge_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!ready}
                    @click=${() => this._onSubmit()}
                >
                    ${this._mergeOp.busy
                        ? this.t('entity_merge_modal.submitting')
                        : this.t('entity_merge_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-entity-merge-modal', CRMEntityMergeModal);
registerModalKind(CRMEntityMergeModal.modalKind, 'crm-entity-merge-modal');
