/**
 * Универсальная модалка создания записи справочника склада.
 *
 * Страница передаёт через openModal props:
 *   modalTitle   — заголовок (уже локализованный);
 *   fields       — StockEntityFormField[] (label локализован, options разрешены);
 *   submitOp     — имя async-op фабрики создания;
 *   buildPayload — (draft) => payload для op.run.
 *
 * Модалка сама ведёт draft, валидирует required и закрывается
 * по SUCCEEDED своего опа (страница на том же событии делает reload).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { FactoryNameOfKind } from '@platform/lib/events/factory-registry.js';
import '@platform/lib/components/fields/platform-field.js';

type Draft = Record<string, unknown>;

export interface StockEntityFormField {
    key: string;
    label: string;
    type?: 'string' | 'number' | 'boolean' | 'enum' | undefined;
    required?: boolean | undefined;
    options?: { value: string; label: string }[] | undefined;
}

export class StockEntityFormModal extends PlatformFormModal {
    static modalKind = 'stock.entity_form';
    static i18nNamespace = 'stock';

    static override properties: PropertyDeclarations = {
        modalTitle: { attribute: false },
        fields: { attribute: false },
        submitOp: { attribute: false },
        buildPayload: { attribute: false },
        initialDraft: { attribute: false },
        _draft: { state: true },
    };
    declare modalTitle: string;
    declare fields: StockEntityFormField[];
    declare submitOp: FactoryNameOfKind<'async-op'>;
    declare buildPayload: (draft: Draft) => Record<string, unknown>;
    declare initialDraft: Draft;
    declare private _draft: Draft;

    private _op: OpController | null = null;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = true;
        this.modalTitle = '';
        this.fields = [];
        this.buildPayload = (d) => d;
        this.initialDraft = {};
        this._draft = {};
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._op = this.useOp(this.submitOp);
        this.useEvent(this._op.op.events.SUCCEEDED, () => { this.closeAfterSave(); });
        this._draft = { ...this.initialDraft };
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.isDirty = this.fields.some((f) => {
            const v = this._draft[f.key];
            return v !== undefined && v !== '' && v !== false;
        });
    }

    private get _valid(): boolean {
        return this.fields.every((f) => {
            if (f.required !== true) return true;
            const v = this._draft[f.key];
            return typeof v === 'string' ? v.trim() !== '' : v !== undefined && v !== '';
        });
    }

    override async _performSave(): Promise<void> {
        if (this._op === null || !this._valid) return;
        await this._op.run(this.buildPayload(this._draft));
    }

    override renderHeader(): string {
        return this.modalTitle;
    }

    override renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._op?.busy === true || !this._valid,
            title: this.t('settings.save'),
        });
    }

    override renderBody(): TemplateResult {
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                ${this.fields.map((f) => html`
                    <platform-field
                        type=${f.type ?? 'string'} mode="edit"
                        .label=${f.label}
                        .value=${this._draft[f.key] ?? (f.type === 'boolean' ? false : '')}
                        ?required=${f.required === true}
                        .config=${f.options !== undefined ? { values: f.options } : {}}
                        data-field=${f.key}
                        @change=${(e: CustomEvent) => { this._draft = { ...this._draft, [f.key]: e.detail.value }; }}
                    ></platform-field>
                `)}
            </form>
        `;
    }
}

customElements.define('stock-entity-form-modal', StockEntityFormModal);
registerModalKind(StockEntityFormModal.modalKind, 'stock-entity-form-modal');
