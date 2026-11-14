/**
 * Конфигурационные страницы склада — один паттерн на все справочники:
 * `page-header` с CTA «Создать» → `stock-entity-form-modal`, тулбар
 * с compact-combobox склада, таблица `StockItemsResponse` в `.table-card`,
 * toggle-апдейты через update-опы.
 *
 * Элементы: stock-warehouses-page, stock-storage-types-page,
 * stock-container-types-page, stock-resources-page,
 * stock-putaway-rules-page, stock-reorder-rules-page, stock-routes-page.
 */

import { html } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { FactoryNameOfKind } from '@platform/lib/events/factory-registry.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import { stockPageStyles } from '../styles/stock-page.styles.js';
import { StockEntityFormModal } from '../modals/stock-entity-form-modal.js';
import type { StockEntityFormField } from '../modals/stock-entity-form-modal.js';

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
    subtitleKey?: string;
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
    /** List op требует warehouse_id — «все склады» невозможно: прячем
     * пункт и автовыбираем первый склад, иначе список навсегда пуст. */
    warehouseRequired?: boolean;
}

abstract class StockSettingsPageBase extends PlatformPage {
    static override properties = {
        _warehouseId: { state: true },
    };
    declare private _warehouseId: string;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        stockPageStyles,
    ];

    protected abstract config: EntityConfig;
    private _list!: OpController | null;
    private _createOp!: OpController | null;
    protected _updateOp!: OpController | null;
    private _listResource: ResourceController | null = null;
    protected _warehouses!: ResourceController;

    constructor() {
        super();
        this._warehouseId = '';
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

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this.config.warehouseRequired !== true || this._warehouseId !== '') return;
        const first = this._warehouses.items.filter(isPlainRecord)[0];
        if (first === undefined || typeof first.warehouse_id !== 'string') return;
        this._warehouseId = first.warehouse_id;
        this.reload();
    }

    protected _warehouseOptions(): { value: string; label: string }[] {
        return this._warehouses.items.filter(isPlainRecord).map((w) => ({ value: w.warehouse_id as string, label: w.name as string }));
    }

    protected _openCreate(): void {
        const cfg = this.config;
        if (cfg.createOp === undefined || cfg.formFields === undefined || cfg.buildCreatePayload === undefined) return;
        const buildPayload = cfg.buildCreatePayload;
        const fields: StockEntityFormField[] = [];
        if (cfg.warehouseFilter) {
            fields.push({
                key: 'warehouse_id', label: this.t('settings.warehouse'),
                type: 'enum', required: true, options: this._warehouseOptions(),
            });
        }
        for (const f of cfg.formFields) {
            fields.push({ key: f.key, label: this.t(f.labelKey), type: f.type, required: f.required, options: f.options?.() });
        }
        this.openModal(StockEntityFormModal, {
            modalTitle: `${this.t('settings.create')} · ${this.t(cfg.titleKey)}`,
            fields,
            submitOp: cfg.createOp,
            initialDraft: { warehouse_id: this._warehouseId },
            buildPayload: (draft: PlainRow) => buildPayload(
                draft,
                typeof draft.warehouse_id === 'string' && draft.warehouse_id !== '' ? draft.warehouse_id : this._warehouseId,
            ),
        });
    }

    protected _renderTable(columns: Column[], items: PlainRow[], emptyKey = 'settings.empty'): TemplateResult {
        return html`
            <div class="table-card"><div class="scroll">
                ${items.length === 0
                    ? html`<platform-empty-state .message=${this.t(emptyKey)}></platform-empty-state>`
                    : html`
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
                    `}
            </div></div>
        `;
    }

    protected _renderToolbar(): TemplateResult | '' {
        if (!this.config.warehouseFilter) return '';
        return html`
            <div class="toolbar">
                <platform-searchable-combobox compact
                    .placeholder=${this.t('settings.warehouse')}
                    .value=${this._warehouseId}
                    .options=${[
                        ...(this.config.warehouseRequired === true ? [] : [{ value: '', label: this.t('settings.all_warehouses') }]),
                        ...this._warehouseOptions(),
                    ]}
                    @change=${(e: CustomEvent) => {
                        this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.reload();
                    }}
                ></platform-searchable-combobox>
            </div>
        `;
    }

    protected _renderSection(titleKey: string, action?: TemplateResult): TemplateResult {
        return html`
            <div class="section">
                <h2>${this.t(titleKey)}</h2>
                ${action ?? ''}
            </div>
        `;
    }

    protected renderExtra(): TemplateResult | '' { return ''; }

    override render() {
        return html`
            <div class="wrap">
                <page-header
                    title=${this.t(this.config.titleKey)}
                    subtitle=${this.config.subtitleKey !== undefined ? this.t(this.config.subtitleKey) : ''}
                    dense
                >
                    ${this._createOp !== null ? html`
                        <platform-button slot="actions" variant="primary" data-create @click=${() => this._openCreate()}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            ${this.t('settings.create')}
                        </platform-button>
                    ` : ''}
                </page-header>
                ${this._renderToolbar()}
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

function toggleCell(row: PlainRow, idField: string, op: OpController | null, field: string): TemplateResult {
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
        subtitleKey: 'settings.warehouses_subtitle',
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

    override connectedCallback(): void {
        this._opTypes = this.useOp('stock/operation_types_list');
        this._opTypeUpdate = this.useOp('stock/operation_type_update');
        super.connectedCallback();
    }

    protected override renderExtra(): TemplateResult {
        const result = this._opTypes.lastResult;
        const items = isPlainRecord(result) && Array.isArray(result.items) ? result.items.filter(isPlainRecord) : [];
        return html`
            ${this._renderSection('settings.operation_types')}
            <div class="toolbar">
                <platform-searchable-combobox compact
                    .placeholder=${this.t('settings.warehouse')}
                    .value=${this._opWarehouseId}
                    .options=${this._warehouseOptions()}
                    @change=${(e: CustomEvent) => {
                        this._opWarehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        if (this._opWarehouseId !== '') this._opTypes.run({ warehouse_id: this._opWarehouseId });
                    }}
                ></platform-searchable-combobox>
            </div>
            ${this._opWarehouseId === '' ? '' : this._renderTable([
                { key: 'name', labelKey: 'settings.name' },
                { key: 'code', labelKey: 'settings.code' },
                {
                    key: 'auto_validate', labelKey: 'settings.auto_validate',
                    render: (row) => toggleCell(row, 'operation_type_id', this._opTypeUpdate, 'auto_validate'),
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
        subtitleKey: 'settings.storage_types_subtitle',
        listOp: 'stock/storage_types_list', createOp: 'stock/storage_type_create', updateOp: 'stock/storage_type_update',
        idField: 'storage_type_id', warehouseFilter: true, warehouseRequired: true,
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
        subtitleKey: 'settings.container_types_subtitle',
        listOp: 'stock/container_types_list', createOp: 'stock/container_type_create', updateOp: 'stock/container_type_update',
        idField: 'container_type_id', warehouseFilter: true, warehouseRequired: true,
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
        subtitleKey: 'settings.resources_subtitle',
        listOp: 'stock/resources_list', createOp: 'stock/resource_create', updateOp: 'stock/resource_update',
        idField: 'resource_id', warehouseFilter: true, warehouseRequired: true,
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

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
        this._types = this.useOp('stock/resource_types_list');
        super.connectedCallback();
    }

    protected override reload() {
        super.reload();
        if (this.warehouseId() !== '') this._types.run({ warehouse_id: this.warehouseId() });
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

    private _openTypeCreate(): void {
        this.openModal(StockEntityFormModal, {
            modalTitle: `${this.t('settings.create')} · ${this.t('settings.resource_types')}`,
            fields: [
                {
                    key: 'warehouse_id', label: this.t('settings.warehouse'),
                    type: 'enum', required: true, options: this._warehouseOptions(),
                },
                { key: 'name', label: this.t('settings.name'), required: true },
                { key: 'handles_loose', label: this.t('settings.handles_loose'), type: 'boolean' },
                { key: 'max_level', label: this.t('settings.max_level'), type: 'number' },
                { key: 'max_load_weight', label: this.t('settings.max_load_weight'), type: 'number' },
            ],
            submitOp: 'stock/resource_type_create',
            initialDraft: { warehouse_id: this.warehouseId(), handles_loose: true },
            buildPayload: (d: PlainRow) => ({
                warehouse_id: typeof d.warehouse_id === 'string' ? d.warehouse_id : '',
                name: d.name,
                handles_loose: d.handles_loose !== false,
                max_level: Number.isFinite(Number(d.max_level)) && d.max_level !== '' ? Number(d.max_level) : null,
                max_load_weight: Number.isFinite(Number(d.max_load_weight)) && d.max_load_weight !== '' ? Number(d.max_load_weight) : null,
            }),
        });
    }

    protected override renderExtra(): TemplateResult {
        const result = this._types.lastResult;
        const types = isPlainRecord(result) && Array.isArray(result.items) ? result.items.filter(isPlainRecord) : [];
        return html`
            ${this._renderSection('settings.resource_types', html`
                <platform-button variant="secondary" density="compact" @click=${() => this._openTypeCreate()}>
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this.t('settings.create')}
                </platform-button>
            `)}
            ${this._renderTable([
                { key: 'name', labelKey: 'settings.name' },
                { key: 'handles_loose', labelKey: 'settings.handles_loose', render: (r) => (r.handles_loose === true ? '✓' : '—') },
                { key: 'max_level', labelKey: 'settings.max_level', num: true },
                { key: 'max_load_weight', labelKey: 'settings.max_load_weight', num: true },
            ], types)}
        `;
    }
}
customElements.define('stock-resources-page', StockResourcesPage);

/* --- Правила размещения --------------------------------------------------- */

export class StockPutawayRulesPage extends StockSettingsPageBase {
    protected config: EntityConfig = {
        titleKey: 'settings.putaway_rules_title',
        subtitleKey: 'settings.putaway_rules_subtitle',
        listOp: 'stock/putaway_rules_list', createOp: 'stock/putaway_rule_create', updateOp: 'stock/putaway_rule_update',
        idField: 'rule_id', warehouseFilter: true, warehouseRequired: true,
        columns: [
            { key: 'location_in_id', labelKey: 'settings.location_in', render: (r) => this._locName(r.location_in_id) },
            { key: 'location_out_id', labelKey: 'settings.location_out', render: (r) => this._locName(r.location_out_id) },
            { key: 'product_id', labelKey: 'settings.product', render: (r) => txt(r, 'product_id') },
            { key: 'sequence', labelKey: 'settings.sequence', num: true },
            {
                key: 'is_active', labelKey: 'settings.is_active',
                render: (r) => toggleCell(r, 'rule_id', this._updateOp, 'is_active'),
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

    private _deleteOp!: OpController;
    protected _locations!: ResourceController;
    protected _products!: ResourceController;

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
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
        subtitleKey: 'settings.reorder_rules_subtitle',
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
                render: (r) => toggleCell(r, 'rule_id', this._updateOp, 'is_active'),
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

    private _opTypes!: OpController;
    private _locationsRes!: ResourceController;
    private _productsRes!: ResourceController;

    constructor() { super(); this.init(); }

    override connectedCallback(): void {
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
        subtitleKey: 'settings.routes_subtitle',
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
            { key: 'warehouse_id', labelKey: 'settings.warehouse', type: 'enum', options: () => this._warehouseOptions() },
        ],
        buildCreatePayload: (d, wh) => ({
            name: d.name,
            code: typeof d.code === 'string' && d.code !== '' ? d.code : undefined,
            warehouse_id: wh !== '' ? wh : null,
        }),
    };
    constructor() { super(); this.init(); }
}
customElements.define('stock-routes-page', StockRoutesPage);
