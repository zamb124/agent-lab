/**
 * Слияние двух сущностей: выбор базовой карточки и left/right по конфликтам.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';

const SCALAR_KEYS = [
    'name',
    'description',
    'status',
    'entity_subtype',
    'priority',
    'note_date',
    'due_date',
];

function stableStringify(value) {
    if (value === undefined) {
        return 'null';
    }
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map((x) => stableStringify(x)).join(',')}]`;
    }
    const keys = Object.keys(value).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
}

function formatCellValue(value) {
    if (value === null || value === undefined || value === '') {
        return '';
    }
    if (typeof value === 'object') {
        return stableStringify(value);
    }
    return String(value);
}

export class EntityMergeModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        entityIdA: { type: String },
        entityIdB: { type: String },
        _loading: { state: true },
        _error: { state: true },
        _left: { state: true },
        _right: { state: true },
        _survivorIsLeft: { state: true },
        _pickScalar: { state: true },
        _pickAttr: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            .merge-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .pair-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            .pick-card {
                border: 2px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                cursor: pointer;
                text-align: left;
                background: var(--crm-surface-muted);
                transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
            }
            .pick-card:hover {
                border-color: var(--accent);
            }
            .pick-card.selected {
                border-color: var(--crm-button-primary-bg);
                box-shadow: var(--focus-ring);
            }
            .pick-card .name {
                font-weight: 600;
                color: var(--text-primary);
                margin: 0 0 var(--space-1) 0;
                font-size: var(--text-base);
            }
            .pick-card .meta {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            .section-title {
                margin: 0 0 var(--space-2) 0;
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-secondary);
            }
            .conflict-row {
                margin-bottom: var(--space-3);
            }
            .conflict-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }
            .split-pick {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-2);
            }
            .half {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                padding: var(--space-2);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--bg-secondary);
                min-height: 2.5rem;
                word-break: break-word;
            }
            .half:hover {
                border-color: var(--accent);
            }
            .half.active {
                border-color: var(--crm-button-primary-bg);
                background: var(--crm-selected-bg);
            }
            .err {
                color: var(--color-danger, #e55);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this._loading = false;
        this._error = '';
        this._left = null;
        this._right = null;
        this._survivorIsLeft = null;
        this._pickScalar = {};
        this._pickAttr = {};
        this._saving = false;
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('open') && this.open) {
            this._bootstrap();
        }
    }

    async _bootstrap() {
        this.heading = this.i18n.t('entity_merge.heading');
        this._error = '';
        this._survivorIsLeft = null;
        this._pickScalar = {};
        this._pickAttr = {};
        const a = (this.entityIdA || '').trim();
        const b = (this.entityIdB || '').trim();
        if (!a || !b || a === b) {
            this._error = this.i18n.t('entity_merge.err_pair');
            this._left = null;
            this._right = null;
            return;
        }
        this._loading = true;
        const crmApi = this.services.get('crmApi');
        try {
            const [left, right] = await Promise.all([
                crmApi.getEntity(a),
                crmApi.getEntity(b),
            ]);
            this._left = left;
            this._right = right;
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this._error = message;
            this._left = null;
            this._right = null;
        } finally {
            this._loading = false;
        }
    }

    _computeScalarConflicts() {
        if (!this._left || !this._right) {
            return [];
        }
        const out = [];
        for (const key of SCALAR_KEYS) {
            const lv = this._left[key];
            const rv = this._right[key];
            if (stableStringify(lv) !== stableStringify(rv)) {
                out.push({ key, left: lv, right: rv });
            }
        }
        return out;
    }

    _computeAttrConflicts() {
        if (!this._left || !this._right) {
            return [];
        }
        const la = this._left.attributes || {};
        const ra = this._right.attributes || {};
        const keys = new Set([...Object.keys(la), ...Object.keys(ra)]);
        const out = [];
        for (const key of Array.from(keys).sort()) {
            const aHas = Object.prototype.hasOwnProperty.call(la, key);
            const bHas = Object.prototype.hasOwnProperty.call(ra, key);
            if (aHas && !bHas) {
                continue;
            }
            if (bHas && !aHas) {
                continue;
            }
            if (stableStringify(la[key]) !== stableStringify(ra[key])) {
                out.push({ key, left: la[key], right: ra[key] });
            }
        }
        return out;
    }

    _onPickSurvivor(isLeft) {
        this._survivorIsLeft = isLeft;
        const def = isLeft;
        const nextScalar = {};
        const nextAttr = {};
        for (const row of this._computeScalarConflicts()) {
            nextScalar[row.key] = def;
        }
        for (const row of this._computeAttrConflicts()) {
            nextAttr[row.key] = def;
        }
        this._pickScalar = nextScalar;
        this._pickAttr = nextAttr;
    }

    _mergeSideFromPick(pickLeft) {
        if (this._survivorIsLeft === null) {
            throw new Error('survivor not chosen');
        }
        const fromSurvivorColumn = pickLeft === this._survivorIsLeft;
        return fromSurvivorColumn ? 'survivor' : 'source';
    }

    _onPickScalar(key, pickLeft) {
        this._pickScalar = { ...this._pickScalar, [key]: pickLeft };
    }

    _onPickAttr(key, pickLeft) {
        this._pickAttr = { ...this._pickAttr, [key]: pickLeft };
    }

    async _onMerge() {
        if (this._survivorIsLeft === null || !this._left || !this._right) {
            return;
        }
        this._saving = true;
        const crmApi = this.services.get('crmApi');
        const survivorId = this._survivorIsLeft ? this._left.entity_id : this._right.entity_id;
        const sourceId = this._survivorIsLeft ? this._right.entity_id : this._left.entity_id;
        const scalarChoices = {};
        for (const row of this._computeScalarConflicts()) {
            scalarChoices[row.key] = this._mergeSideFromPick(this._pickScalar[row.key]);
        }
        const attributeChoices = {};
        for (const row of this._computeAttrConflicts()) {
            attributeChoices[row.key] = this._mergeSideFromPick(this._pickAttr[row.key]);
        }
        const payload = {
            survivor_entity_id: survivorId,
            source_entity_id: sourceId,
            scalar_choices: scalarChoices,
            attribute_choices: attributeChoices,
        };
        try {
            await CRMStore.mergeEntities(crmApi, payload);
            this.success(this.i18n.t('entity_merge.success'));
            this.dispatchEvent(new CustomEvent('merged', {
                bubbles: true,
                composed: true,
                detail: { survivorId, sourceId },
            }));
            this.close();
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this.error(message);
            throw error;
        } finally {
            this._saving = false;
        }
    }

    _fieldLabel(key) {
        const k = `entity_merge.field.${key}`;
        const t = this.i18n.t(k);
        return t === k ? key : t;
    }

    _renderPickCards() {
        if (!this._left || !this._right) {
            return '';
        }
        return html`
            <p class="section-title">${this.i18n.t('entity_merge.pick_base')}</p>
            <div class="pair-row">
                <button
                    type="button"
                    class="pick-card ${this._survivorIsLeft === true ? 'selected' : ''}"
                    @click=${() => this._onPickSurvivor(true)}
                >
                    <p class="name">${this._left.name || this._left.entity_id}</p>
                    <p class="meta">${this._left.entity_type}${this._left.entity_subtype ? `:${this._left.entity_subtype}` : ''}</p>
                </button>
                <button
                    type="button"
                    class="pick-card ${this._survivorIsLeft === false ? 'selected' : ''}"
                    @click=${() => this._onPickSurvivor(false)}
                >
                    <p class="name">${this._right.name || this._right.entity_id}</p>
                    <p class="meta">${this._right.entity_type}${this._right.entity_subtype ? `:${this._right.entity_subtype}` : ''}</p>
                </button>
            </div>
        `;
    }

    _renderConflicts() {
        if (this._survivorIsLeft === null) {
            return '';
        }
        const scalarRows = this._computeScalarConflicts();
        const attrRows = this._computeAttrConflicts();
        if (scalarRows.length === 0 && attrRows.length === 0) {
            return html`<p class="section-title">${this.i18n.t('entity_merge.no_conflicts')}</p>`;
        }
        return html`
            <p class="section-title">${this.i18n.t('entity_merge.conflicts')}</p>
            ${scalarRows.map((row) => {
                const pickLeft = this._pickScalar[row.key];
                return html`
                    <div class="conflict-row">
                        <div class="conflict-label">${this._fieldLabel(row.key)}</div>
                        <div class="split-pick">
                            <button
                                type="button"
                                class="half ${pickLeft === true ? 'active' : ''}"
                                @click=${() => this._onPickScalar(row.key, true)}
                            >${formatCellValue(row.left) || '—'}</button>
                            <button
                                type="button"
                                class="half ${pickLeft === false ? 'active' : ''}"
                                @click=${() => this._onPickScalar(row.key, false)}
                            >${formatCellValue(row.right) || '—'}</button>
                        </div>
                    </div>
                `;
            })}
            ${attrRows.map((row) => {
                const pickLeft = this._pickAttr[row.key];
                return html`
                    <div class="conflict-row">
                        <div class="conflict-label">${this.i18n.t('entity_merge.attr_key', { key: row.key })}</div>
                        <div class="split-pick">
                            <button
                                type="button"
                                class="half ${pickLeft === true ? 'active' : ''}"
                                @click=${() => this._onPickAttr(row.key, true)}
                            >${formatCellValue(row.left) || '—'}</button>
                            <button
                                type="button"
                                class="half ${pickLeft === false ? 'active' : ''}"
                                @click=${() => this._onPickAttr(row.key, false)}
                            >${formatCellValue(row.right) || '—'}</button>
                        </div>
                    </div>
                `;
            })}
        `;
    }

    renderBody() {
        if (this._loading) {
            return html`<p>${this.i18n.t('entity_merge.loading')}</p>`;
        }
        if (this._error) {
            return html`<p class="err">${this._error}</p>`;
        }
        return html`
            <div class="merge-wrap">
                ${this._renderPickCards()}
                ${this._renderConflicts()}
            </div>
        `;
    }

    renderFooter() {
        const canMerge = !this._loading
            && !this._error
            && this._left
            && this._right
            && this._survivorIsLeft !== null;
        return html`
            <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                ${this.i18n.t('actions.cancel')}
            </button>
            <button
                type="button"
                class="btn btn-primary"
                ?disabled=${!canMerge || this._saving}
                @click=${() => this._onMerge()}
            >
                ${this.i18n.t('entity_merge.submit')}
            </button>
        `;
    }
}

customElements.define('entity-merge-modal', EntityMergeModal);
