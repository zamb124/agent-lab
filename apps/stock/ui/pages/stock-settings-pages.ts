/**
 * Конфигурационные страницы склада — один паттерн на все справочники:
 * combobox склада, таблица `StockItemsResponse`, раскрываемая форма
 * создания (platform-field), toggle-апдейты через update-опы.
 *
 * Элементы: stock-warehouses-page, stock-storage-types-page,
 * stock-container-types-page, stock-resources-page,
 * stock-putaway-rules-page, stock-reorder-rules-page, stock-routes-page.
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { AsyncOpFactory } from '@platform/lib/events/factories/async-op.js';
import type { FactoryNameOfKind } from '@platform/lib/events/factory-registry.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

type PlainRow = Record<string, unknown>;

interface Column {
    key: string;
    labelKey: string;
    num?: boolean;
    render?: (row: PlainRow) => unknown;
}

interface FormField {
    key: string;
    labelKey: string;
    type?: 'string' | 'number' | 'boolean' | 'enum';
    required?: boolean;
    options?: () => { value: string; label: string }[];
}

interface EntityConfig {
    titleKey: string;
    listOp?: FactoryNameOfKind<'async-op'>;
    listResource?: FactoryNameOfKind<'resource-collection'>;
    createOp?: FactoryNameOfKind<'async-op'>;
    updateOp?: FactoryNameOfKind<'async-op'>;
    idField: string;
    listQuery?: (warehouseId: string) => Record<string, unknown>;
    warehouseFilter: boolean;
    columns: Column[];
    formFields?: FormField[];
    buildCreatePayload?: (draft: PlainRow, warehouseId: string) => PlainRow;
    onRowClick?: (row: PlainRow) => void;
}

abstract class StockSettingsPageBase extends PlatformPage {
    static override properties = {
        _warehouseId: { state: true },
        _formOpen: { state: true },
        _draft: { state: true },
    };
    declare private _warehouseId: string;
    declare private _formOpen: boolean;
    declare private _draft: PlainRow;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-5); }
            .head { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; margin-bottom: var(--space-4); }
            .head h1 { margin: 0; font-size: var(--text-2xl); color: var(--text-primary); flex: 1; }
            .head platform-searchable-combobox { min-width: 200px; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            tr.clickable { cursor: pointer; }
            tr.clickable:hover td { background: var(--surface-2); }
            .create-panel { border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-md); padding: var(--space-4); margin-bottom: var(--space-4); display: grid; gap: var(--space-3); }
            .create-panel .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--space-3); }
            h2.section { font-size: var(--text-base); color: var(--text-secondary); margin: var(--space-5) 0 var(--space-2); }
        `,
    ];

    protected abstract config: EntityConfig;
    private _list!: OpController | null;
    private _createOp!: OpController | null;
    private _updateOp!: OpController | null;
    private _listResource: ResourceController | null = null;
    protected _warehouses!: ResourceController;

    constructor() {
        super();
        this._warehouseId = '';
        this._formOpen = false;
        this._draft = {};
    }

    protected init() {
        this._list = this.config.listOp !== undefined ? this.useOp(this.config.listOp) : null;
        this._createOp = this.config.createOp !== undefined ? this.useOp(this.config.createOp) : null;
        this._updateOp = this.config.updateOp !== undefined ? this.useOp(this.config.updateOp) : null;
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._listResource = this.config.listResource !== undefined ? this.useResource(this.config.listResource, { autoload: true }) : null;
    }



    override connectedCallback(): void {
        super.connectedCallback();
        this.reload();
        if (this._createOp !== null) {
            this.useEvent((this._createOp.op as AsyncOpFactory).events.SUCCEEDED, () => {
                this._formOpen = false;
                this._draft = {};
            });
        }
    }

    protected reload() {
        if (this._list === null) {
            this._listResource?.load({});
            return;
        }
        const q = this.config.listQuery !== undefined
            ? this.config.listQuery(this._warehouseId)
            : (this._warehouseId !== '' ? { warehouse_id: this._warehouseId } : {});
        this._list.run(q);
    }

    protected items(): PlainRow[] {
        if (this._list === null) {
            return this._listResource?.items.filter(isPlainRecord) ?? [];
        }
        const result = this._list.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord);
    }

    protected warehouseId(): string { return this._warehouseId; }

    protected locationOptions(): { value: string; label: string }[] {
        return [];
    }

    protected _renderHead(): TemplateResult {
        const whOptions = this._warehouses.items.filter(isPlainRecord).map((w) => ({ value: w.warehouse_id as string, label: w.name as string }));
        return html`
            <div class="head">
                <h1>${this.t(this.config.titleKey)}</h1>
                ${this.config.warehouseFilter ? html`
                    <platform-searchable-combobox
                        .label=${this.t('settings.warehouse')}
                        .value=${this._warehouseId}
                        .options=${whOptions}
                        @change=${(e: CustomEvent) => {
                            this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                            this.reload();
                        }}
                    ></platform-searchable-combobox>
                ` : ''}
                ${this._createOp !== null ? html`
                    <platform-button variant="primary" density="compact" @click=${() => { this._formOpen = !this._formOpen; }}>
                        <platform-icon name="plus" size="14"></platform-icon> ${this.t('settings.create')}
                    </platform-button>
                ` : ''}
            </div>
        `;
    }

    private _renderCreateForm(): TemplateResult | '' {
        if (!this._formOpen || this._createOp === null || this.config.formFields === undefined) return '';
        return html`
            <div class="create-panel">
                <div class="grid">
                    ${this.config.formFields.map((f) => html`
                        <platform-field
                            type=${f.type ?? 'string'} mode="edit"
                            .label=${this.t(f.labelKey)}
                            .value=${this._draft[f.key] ?? (f.type === 'boolean' ? false : '')}
                            ?required=${f.required === true}
                            .config=${f.options !== undefined ? { values: f.options() } : {}}
                            @change=${(e: CustomEvent) => { this._draft = { ...this._draft, [f.key]: e.detail.value }; }}
                        ></platform-field>
                    `)}
                </div>
                <div style="display:flex; gap: var(--space-2);">
                    <platform-button variant="primary" ?loading=${this._createOp.busy} @click=${() => this._submitCreate()}>
                        <platform-icon name="check" size="14"></platform-icon> ${this.t('settings.save')}
                    </platform-button>
                    <platform-button variant="secondary" @click=${() => { this._formOpen = false; }}>${this.t('settings.cancel')}</platform-button>
                </div>
            </div>
        `;
    }

    private _submitCreate() {
        if (this._createOp === null || this.config.buildCreatePayload === undefined) return;
        const payload = this.config.buildCreatePayload(this._draft, this._warehouseId);
        this._createOp.run(payload);
    }

    protected _renderTable(columns: Column[], items: PlainRow[], emptyKey = 'settings.empty'): TemplateResult {
        if (items.length === 0) {
            return html`<platform-empty-state .message=${this.t(emptyKey)}></platform-empty-state>`;
        }
        return html`
            <table><thead><tr>
                ${columns.map((c) => html`<th class=${c.num === true ? 'num' : ''}>${this.t(c.labelKey)}</th>`)}
            </tr></thead><tbody>
                ${items.map((row) => html`
                    <tr class=${this.config.onRowClick !== undefined ? 'clickable' : ''}
                        @click=${() => this.config.onRowClick?.(row)}>
                        ${columns.map((c) => html`<td class=${c.num === true ? 'num' : ''}>${c.render !== undefined ? c.render(row) : (row[c.key] ?? '—')}</td>`)}
                    </tr>
                `)}
            </tbody></table>
        `;
    }

    protected renderExtra(): TemplateResult | '' { return ''; }

    override render() {
        return html`
            <div class="wrap">
                ${this._renderHead()}
                ${this._renderCreateForm()}
                ${this._renderTable(this.config.columns, this.items())}
                ${this.renderExtra()}
            </div>
        `;
    }
}

function txt(row: PlainRow, key: string): string {
    const v = row[key];
    return typeof v === 'string' && v !== '' ? v : '—';
}

function toggleCell(page: StockSettingsPageBase, row: PlainRow, idField: string, op: OpController | null, field: string): TemplateResult {
    const on = row[field] !== false;
    return html`
        <input type="checkbox" ?checked=${on} ?disabled=${op === null || op.busy}
            @click=${(e: Event) => e.stopPropagation()}
            @change=${(e: Event) => {
                e.stopPropagation();
                op?.run({ [idField]: row[idField], [field]: (e.target as HTMLInputElement).checked });
            }} />
    `;
}

function scanFlowCell(page: StockSettingsPageBase, row: PlainRow, op: OpController | null): TemplateResult {
    const value = typeof row.scan_flow === 'string' && row.scan_flow !== '' ? row.scan_flow : 'default';
    return html`
        <platform-field type="enum" mode="edit"
            .value=${value}
            .config=${{ values: [
                { value: 'default', label: page.t('settings.scan_flow_default') },
                { value: 'pack', label: page.t('settings.scan_flow_pack') },
                { value: 'ship', label: page.t('settings.scan_flow_ship') },
            ] }}
            @click=${(e: Event) => e.stopPropagation()}
            @change=${(e: CustomEvent) => {
                e.stopPropagation();
                if (op === null || typeof e.detail.value !== 'string') return;
                op.run({ operation_type_id: row.operation_type_id, scan_flow: e.detail.value });
            }}
        ></platform-field>
    `;
}

/* --- Склады и операции ------------------------------------------------ */

export class StockWarehousesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.warehouses_title',
        listResource: 'stock/warehouses', createOp: 'stock/warehouse_create', updateOp: 'stock/warehouse_update',
        idField: 'warehouse_id', warehouseFilter: false,
        columns: [
            { key: 'code', labelKey: 'settings.code' },
            { key: 'name', labelKey: 'settings.name' },
            { key: 'layout_preset', labelKey: 'settings.layout_preset' },
            { key: 'removal_strategy', labelKey: 'settings.removal_strategy' },
        ],
        formFields: [
            { key: 'code', labelKey: 'settings.code', required: true },
            { key: 'name', labelKey: 'settings.name', required: true },
            {
                key: 'layout_preset', labelKey: 'settings.layout_preset', type: 'enum',
                options: () => [
                    { value: 'simple', label: 'simple' },
                    { value: 'standard', label: 'standard' },
                    { value: 'distribution_center', label: 'distribution_center' },
                ],
            },
            {
                key: 'removal_strategy', labelKey: 'settings.removal_strategy', type: 'enum',
                options: () => [
                    { value: 'fifo', label: 'FIFO' },
                    { value: 'fefo', label: 'FEFO' },
                    { value: 'lifo', label: 'LIFO' },
                ],
            },
        ],
        buildCreatePayload: (d) => ({
            code: d.code, name: d.name,
            layout_preset: typeof d.layout_preset === 'string' && d.layout_preset !== '' ? d.layout_preset : 'standard',
            removal_strategy: typeof d.removal_strategy === 'string' && d.removal_strategy !== '' ? d.removal_strategy : 'fifo',
        }),
    };

    private _opTypes!: OpController;
    private _opTypeUpdate!: OpController;
    declare private _opWarehouseId: string;
    static override properties = { ...StockSettingsPageBase.properties, _opWarehouseId: { state: true } };

    constructor() {
        super();
        this._opWarehouseId = '';
        this.init();
    }

    protected override reload() {
        super.reload();
        if (this._opWarehouseId !== '') this._opTypes?.run({ warehouse_id: this._opWarehouseId });
    }

    override connectedCallback(): void {
        this._opTypes = this.useOp('stock/operation_types_list');
        this._opTypeUpdate = this.useOp('stock/operation_type_update');
        super.connectedCallback();
    }

    protected override _renderHead(): TemplateResult {
        const head = super._renderHead();
        return head;
    }

    protected override renderExtra(): TemplateResult {
        const whOptions = this._warehouses.items.filter(isPlainRecord).map((w) => ({ value: w.warehouse_id as string, label: w.name as string }));
        const result = this._opTypes.lastResult;
        const items = isPlainRecord(result) && Array.isArray(result.items) ? result.items.filter(isPlainRecord) : [];
        return html`
            <h2 class="section">${this.t('settings.operation_types')}</h2>
            <platform-searchable-combobox
                .label=${this.t('settings.warehouse')}
                .value=${this._opWarehouseId}
                .options=${whOptions}
                @change=${(e: CustomEvent) => {
                    this._opWarehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                    if (this._opWarehouseId !== '') this._opTypes.run({ warehouse_id: this._opWarehouseId });
                }}
            ></platform-searchable-combobox>
            ${this._opWarehouseId === '' ? '' : this._renderTable([
                { key: 'name', labelKey: 'settings.name' },
                { key: 'code', labelKey: 'settings.code' },
                {
                    key: 'auto_validate', labelKey: 'settings.auto_validate',
                    render: (row) => toggleCell(this, row, 'operation_type_id', this._opTypeUpdate, 'auto_validate'),
                },
                {
                    key: 'scan_flow', labelKey: 'settings.scan_flow',
                    render: (row) => scanFlowCell(this, row, this._opTypeUpdate),
                },
            ], items)}
        `;
    }
}
customElements.define('stock-warehouses-page', StockWarehousesPage);

/* --- Типы хранения ----------------------------------------------------- */

export class StockStorageTypesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.storage_types_title',
        listOp: 'stock/storage_types_list', createOp: 'stock/storage_type_create', updateOp: 'stock/storage_type_update',
        idField: 'storage_type_id', warehouseFilter: true,
        columns: [
            { key: 'name', labelKey: 'settings.name' },
            { key: 'container_policy', labelKey: 'settings.container_policy' },
            { key: 'product_mixing', labelKey: 'settings.product_mixing' },
            { key: 'max_containers', labelKey: 'settings.max_containers', num: true },
            { key: 'max_weight', labelKey: 'settings.max_weight', num: true },
            { key: 'cycle_count_days', labelKey: 'settings.cycle_count_days', num: true },
        ],
        formFields: [
            { key: 'name', labelKey: 'settings.name', required: true },
            { key: 'max_containers', labelKey: 'settings.max_containers', type: 'number' },
            { key: 'max_weight', labelKey: 'settings.max_weight', type: 'number' },
            { key: 'cycle_count_days', labelKey: 'settings.cycle_count_days', type: 'number' },
        ],
        buildCreatePayload: (d, wh) => ({
            warehouse_id: wh, name: d.name,
            max_containers: Number.isFinite(Number(d.max_containers)) && d.max_containers !== '' ? Number(d.max_containers) : null,
            max_weight: Number.isFinite(Number(d.max_weight)) && d.max_weight !== '' ? Number(d.max_weight) : null,
            cycle_count_days: Number.isFinite(Number(d.cycle_count_days)) && d.cycle_count_days !== '' ? Number(d.cycle_count_days) : null,
        }),
    };
    constructor() { super(); this.init(); }
}
customElements.define('stock-storage-types-page', StockStorageTypesPage);

/* --- Типы тары ---------------------------------------------------------- */

export class StockContainerTypesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.container_types_title',
        listOp: 'stock/container_types_list', createOp: 'stock/container_type_create', updateOp: 'stock/container_type_update',
        idField: 'container_type_id', warehouseFilter: true,
        columns: [
            { key: 'name', labelKey: 'settings.name' },
            { key: 'kind', labelKey: 'settings.kind' },
            { key: 'max_weight', labelKey: 'settings.max_weight', num: true },
            { key: 'max_volume', labelKey: 'settings.max_volume', num: true },
            { key: 'is_reusable', labelKey: 'settings.is_reusable', render: (r) => (r.is_reusable === true ? '✓' : '—') },
        ],
        formFields: [
            { key: 'name', labelKey: 'settings.name', required: true },
            {
                key: 'kind', labelKey: 'settings.kind', type: 'enum',
                options: () => [
                    { value: 'pallet', label: 'pallet' }, { value: 'box', label: 'box' },
                    { value: 'tote', label: 'tote' }, { value: 'cart', label: 'cart' },
                ],
            },
            { key: 'max_weight', labelKey: 'settings.max_weight', type: 'number' },
            { key: 'max_volume', labelKey: 'settings.max_volume', type: 'number' },
            { key: 'is_reusable', labelKey: 'settings.is_reusable', type: 'boolean' },
        ],
        buildCreatePayload: (d, wh) => ({
            warehouse_id: wh, name: d.name,
            kind: typeof d.kind === 'string' && d.kind !== '' ? d.kind : 'box',
            max_weight: Number.isFinite(Number(d.max_weight)) && d.max_weight !== '' ? Number(d.max_weight) : null,
            max_volume: Number.isFinite(Number(d.max_volume)) && d.max_volume !== '' ? Number(d.max_volume) : null,
            is_reusable: d.is_reusable === true,
        }),
    };
    constructor() { super(); this.init(); }
}
customElements.define('stock-container-types-page', StockContainerTypesPage);

/* --- Ресурсы (типы + единицы) ------------------------------------------- */

export class StockResourcesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.resources_title',
        listOp: 'stock/resources_list', createOp: 'stock/resource_create', updateOp: 'stock/resource_update',
        idField: 'resource_id', warehouseFilter: true,
        columns: [
            { key: 'code', labelKey: 'settings.code' },
            { key: 'resource_type_id', labelKey: 'settings.type_field', render: (r) => this._typeName(r.resource_type_id) },
            { key: 'barcode', labelKey: 'settings.barcode' },
        ],
        formFields: [
            { key: 'code', labelKey: 'settings.code', required: true },
            { key: 'resource_type_id', labelKey: 'settings.type_field', type: 'enum', required: true, options: () => this._typeOptions() },
            { key: 'barcode', labelKey: 'settings.barcode' },
        ],
        buildCreatePayload: (d, wh) => ({
            warehouse_id: wh, resource_type_id: d.resource_type_id, code: d.code,
            barcode: typeof d.barcode === 'string' && d.barcode !== '' ? d.barcode : null,
        }),
    };

    private _types!: OpController;
    private _typeCreate!: OpController;

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
        this._types = this.useOp('stock/resource_types_list');
        this._typeCreate = this.useOp('stock/resource_type_create');
        super.connectedCallback();
        this._types.run(this.warehouseId() !== '' ? { warehouse_id: this.warehouseId() } : {});
    }

    private _typeOptions(): { value: string; label: string }[] {
        const result = this._types.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord).map((r) => ({ value: r.resource_type_id as string, label: r.name as string }));
    }

    private _typeName(id: unknown): string {
        const opts = this._typeOptions();
        const found = opts.find((o) => o.value === id);
        return found !== undefined ? found.label : '—';
    }

    protected override renderExtra(): TemplateResult {
        const result = this._types.lastResult;
        const types = isPlainRecord(result) && Array.isArray(result.items) ? result.items.filter(isPlainRecord) : [];
        return html`
            <h2 class="section">${this.t('settings.resource_types')}</h2>
            ${this._renderTable([
                { key: 'name', labelKey: 'settings.name' },
                { key: 'handles_loose', labelKey: 'settings.is_active', render: (r) => (r.handles_loose === true ? '✓' : '—') },
            ], types)}
        `;
    }
}
customElements.define('stock-resources-page', StockResourcesPage);

/* --- Правила размещения --------------------------------------------------- */

export class StockPutawayRulesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.putaway_rules_title',
        listOp: 'stock/putaway_rules_list', createOp: 'stock/putaway_rule_create', updateOp: 'stock/putaway_rule_update',
        idField: 'rule_id', warehouseFilter: true,
        columns: [
            { key: 'location_in_id', labelKey: 'settings.location_in', render: (r) => this._locName(r.location_in_id) },
            { key: 'location_out_id', labelKey: 'settings.location_out', render: (r) => this._locName(r.location_out_id) },
            { key: 'product_id', labelKey: 'settings.product', render: (r) => txt(r, 'product_id') },
            { key: 'sequence', labelKey: 'settings.sequence', num: true },
            {
                key: 'is_active', labelKey: 'settings.is_active',
                render: (r) => toggleCell(this, r, 'rule_id', this._update, 'is_active'),
            },
            {
                key: 'x', labelKey: '',
                render: (r) => html`<platform-button icon-only density="dense" variant="ghost-danger"
                    title=${this.t('settings.delete')} aria-label=${this.t('settings.delete')}
                    @click=${(e: Event) => { e.stopPropagation(); this._delete(r); }}
                ><platform-icon name="trash" size="14"></platform-icon></platform-button>`,
            },
        ],
        formFields: [
            { key: 'location_in_id', labelKey: 'settings.location_in', type: 'enum', required: true, options: () => this._locOptions() },
            { key: 'location_out_id', labelKey: 'settings.location_out', type: 'enum', required: true, options: () => this._locOptions() },
            { key: 'product_id', labelKey: 'settings.product', type: 'enum', options: () => this._productOptions() },
            { key: 'sequence', labelKey: 'settings.sequence', type: 'number' },
        ],
        buildCreatePayload: (d, wh) => ({
            warehouse_id: wh, location_in_id: d.location_in_id, location_out_id: d.location_out_id,
            product_id: typeof d.product_id === 'string' && d.product_id !== '' ? d.product_id : null,
            sequence: Number.isFinite(Number(d.sequence)) ? Number(d.sequence) : 0,
        }),
    };

    private _update!: OpController;
    private _deleteOp!: OpController;
    protected _locations!: ResourceController;
    protected _products!: ResourceController;

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
        this._update = this.useOp('stock/putaway_rule_update');
        this._deleteOp = this.useOp('stock/putaway_rule_delete');
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._products = this.useResource('stock/products', { autoload: true });
        super.connectedCallback();
    }

    private _locOptions(): { value: string; label: string }[] {
        return this._locations.items.filter(isPlainRecord).map((l) => ({
            value: l.location_id as string,
            label: (typeof l.complete_name === 'string' && l.complete_name !== '' ? l.complete_name : l.name) as string,
        }));
    }

    private _productOptions(): { value: string; label: string }[] {
        return this._products.items.filter(isPlainRecord).map((p) => ({
            value: p.product_id as string,
            label: (typeof p.name === 'string' && p.name !== '' ? p.name : p.product_id) as string,
        }));
    }

    private _locName(id: unknown): string {
        const opts = this._locOptions();
        const found = opts.find((o) => o.value === id);
        return found !== undefined ? found.label : '—';
    }

    private async _delete(row: PlainRow) {
        const ok = await platformConfirm(this.t('settings.confirm_delete'), { confirmText: this.t('settings.delete'), confirmVariant: 'danger' });
        if (ok !== true) return;
        this._deleteOp.run({ rule_id: row.rule_id });
    }
}
customElements.define('stock-putaway-rules-page', StockPutawayRulesPage);

/* --- Правила пополнения ----------------------------------------------------- */

export class StockReorderRulesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.reorder_rules_title',
        listOp: 'stock/reorder_rules_list', createOp: 'stock/reorder_rule_create', updateOp: 'stock/reorder_rule_update',
        idField: 'rule_id', warehouseFilter: true,
        columns: [
            { key: 'product_id', labelKey: 'settings.product', render: (r) => this._name(this._productsRes, r.product_id, 'product_id') },
            { key: 'location_id', labelKey: 'settings.location', render: (r) => this._name(this._locationsRes, r.location_id, 'location_id') },
            { key: 'min_qty', labelKey: 'settings.min_qty', num: true },
            { key: 'max_qty', labelKey: 'settings.max_qty', num: true },
            { key: 'route_id', labelKey: 'settings.route', render: (r) => txt(r, 'route_id') },
            {
                key: 'is_active', labelKey: 'settings.is_active',
                render: (r) => toggleCell(this, r, 'rule_id', this._reorderUpdate, 'is_active'),
            },
        ],
        formFields: [
            { key: 'product_id', labelKey: 'settings.product', type: 'enum', required: true, options: () => this._options(this._productsRes, 'product_id') },
            { key: 'location_id', labelKey: 'settings.location', type: 'enum', required: true, options: () => this._options(this._locationsRes, 'location_id') },
            { key: 'min_qty', labelKey: 'settings.min_qty', type: 'number', required: true },
            { key: 'max_qty', labelKey: 'settings.max_qty', type: 'number', required: true },
            { key: 'operation_type_id', labelKey: 'settings.operation_type', type: 'enum', required: true, options: () => this._opTypeOptions() },
        ],
        buildCreatePayload: (d, wh) => ({
            warehouse_id: wh, product_id: d.product_id, location_id: d.location_id,
            min_qty: Number(d.min_qty), max_qty: Number(d.max_qty),
            operation_type_id: d.operation_type_id,
        }),
    };

    private _reorderUpdate!: OpController;
    private _opTypes!: OpController;
    private _locationsRes!: ResourceController;
    private _productsRes!: ResourceController;

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
        this._reorderUpdate = this.useOp('stock/reorder_rule_update');
        this._opTypes = this.useOp('stock/operation_types_list');
        this._locationsRes = this.useResource('stock/locations', { autoload: true });
        this._productsRes = this.useResource('stock/products', { autoload: true });
        super.connectedCallback();
    }

    protected override reload() {
        super.reload();
        if (this.warehouseId() !== '') this._opTypes?.run({ warehouse_id: this.warehouseId() });
    }

    private _options(ctl: ResourceController, idField: string): { value: string; label: string }[] {
        return ctl.items.filter(isPlainRecord).map((r) => ({
            value: r[idField] as string,
            label: (typeof r.complete_name === 'string' && r.complete_name !== '' ? r.complete_name : r.name) as string,
        }));
    }

    private _name(ctl: ResourceController, id: unknown, idField: string): string {
        const found = this._options(ctl, idField).find((o) => o.value === id);
        return found !== undefined ? found.label : '—';
    }

    private _opTypeOptions(): { value: string; label: string }[] {
        const result = this._opTypes?.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord).map((r) => ({ value: r.operation_type_id as string, label: r.name as string }));
    }
}
customElements.define('stock-reorder-rules-page', StockReorderRulesPage);

/* --- Маршруты ---------------------------------------------------------------- */

export class StockRoutesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.routes_title',
        listOp: 'stock/routes_list', createOp: 'stock/route_create',
        idField: 'route_id', warehouseFilter: false,
        listQuery: () => ({}),
        columns: [
            { key: 'code', labelKey: 'settings.code' },
            { key: 'name', labelKey: 'settings.name' },
            {
                key: 'steps', labelKey: 'settings.steps',
                render: (r) => Array.isArray(r.steps) ? r.steps.length : '—',
            },
        ],
        formFields: [
            { key: 'name', labelKey: 'settings.name', required: true },
            { key: 'code', labelKey: 'settings.code' },
        ],
        buildCreatePayload: (d) => ({
            name: d.name,
            code: typeof d.code === 'string' && d.code !== '' ? d.code : undefined,
            warehouse_id: null,
        }),
    };
    constructor() { super(); this.init(); }
}
customElements.define('stock-routes-page', StockRoutesPage);
