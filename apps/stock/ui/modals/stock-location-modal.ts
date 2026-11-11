/**
 * Создание/редактирование локации склада: имя, usage (view/bin/container),
 * порядок отбора, уровень, штрихкод, блокировки и активность.
 *
 * `locationId` задан → режим редактирования (`stock/location_update`);
 * иначе создание (`stock/location_create`), родитель — `parentId`,
 * склад — `warehouseId` (при создании дочерней наследуется от родителя).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { FormController, OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SegmentItem } from '@platform/lib/components/platform-segmented-control.js';
import type { StockLocation } from '@platform/lib/events/wire/stock.gen.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';

export class StockLocationModal extends PlatformFormModal {
    static modalKind = 'stock.location';
    static i18nNamespace = 'stock';

    static override properties: PropertyDeclarations = {
        locationId: { type: String, attribute: 'location-id' },
        parentId: { type: String, attribute: 'parent-id' },
        warehouseId: { type: String, attribute: 'warehouse-id' },
    };
    declare locationId: string;
    declare parentId: string;
    declare warehouseId: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-3); }
            .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
        `,
    ];

    private _form: FormController;
    private _updateForm: FormController;
    private _createOp: OpController;
    private _updateOp: OpController;
    private _locations: ResourceController;
    private _storageTypes: OpController;
    private _containerTypes: OpController;

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = true;
        this.locationId = '';
        this.parentId = '';
        this.warehouseId = '';
        this._form = this.useForm('stock/location_create_form');
        this._updateForm = this.useForm('stock/location_update_form');
        this._createOp = this.useOp('stock/location_create');
        this._updateOp = this.useOp('stock/location_update');
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._storageTypes = this.useOp('stock/storage_types_list');
        this._containerTypes = this.useOp('stock/container_types_list');
    }

    private get _editing(): boolean {
        return this.locationId !== '';
    }

    private get _activeForm(): FormController {
        return this._editing ? this._updateForm : this._form;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (this._editing) {
            const loc = this._findLocation();
            const barcode = loc?.barcode;
            this._updateForm.openForm({
                location_id: this.locationId,
                name: loc?.name ?? '',
                barcode: typeof barcode === 'string' ? barcode : '',
                pick_sequence: loc?.pick_sequence ?? 0,
                allow_negative: loc?.allow_negative === true,
                putaway_blocked: loc?.putaway_blocked === true,
                removal_blocked: loc?.removal_blocked === true,
                is_active: loc?.is_active !== false,
            });
            this.useEvent(this._updateOp.op.events.SUCCEEDED, () => { this.closeAfterSave(); });
        } else {
            const parent = this.parentId !== '' ? this._findLocation() : null;
            const warehouseId = this.warehouseId !== ''
                ? this.warehouseId
                : (parent !== null && typeof parent.warehouse_id === 'string' ? parent.warehouse_id : '');
            this._form.openForm({
                warehouse_id: warehouseId,
                parent_id: this.parentId !== '' ? this.parentId : null,
                name: '', usage: 'bin', barcode: '',
                pick_sequence: 0, level: 0,
                allow_negative: false, storage_type_id: null, container_type_id: null,
            });
            this.useEvent(this._createOp.op.events.SUCCEEDED, () => { this.closeAfterSave(); });
        }
        if (this.warehouseId !== '' || this.parentId !== '') {
            this._storageTypes.run({ warehouse_id: this._resolveWarehouseId() });
            this._containerTypes.run({ warehouse_id: this._resolveWarehouseId() });
        }
    }

    private _resolveWarehouseId(): string {
        if (this.warehouseId !== '') return this.warehouseId;
        const parent = this._findLocation();
        return parent !== null && typeof parent.warehouse_id === 'string' ? parent.warehouse_id : '';
    }

    private _findLocation(): StockLocation | null {
        const id = this._editing ? this.locationId : this.parentId;
        const row = this._locations.items.find((r) => isPlainRecord(r) && r.location_id === id);
        if (!isPlainRecord(row)) return null;
        return row as unknown as StockLocation;
    }

    override disconnectedCallback(): void {
        this._form.close();
        this._updateForm.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.isDirty = this._activeForm.draft.name !== '' && this._activeForm.draft.name !== undefined;
    }

    private _valid(): boolean {
        const draft = this._activeForm.draft;
        return typeof draft.name === 'string' && draft.name.trim() !== '';
    }

    override async _performSave(): Promise<void> {
        if (!this._valid()) return;
        this._activeForm.submit();
    }

    override renderHeader() {
        return this.t(this._editing ? 'modal.location_edit' : this.parentId !== '' ? 'modal.location_create_child' : 'modal.location_create');
    }

    override renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._activeForm.submitting || !this._valid(),
            title: this.t('settings.save'),
        });
    }

    private _usageItems(): Array<Partial<SegmentItem>> {
        return [
            { value: 'view', label: this.t('explorer.usage_view') },
            { value: 'bin', label: this.t('explorer.usage_bin') },
            { value: 'container', label: this.t('explorer.usage_container') },
        ];
    }

    private _typeOptions(op: OpController, idField: string): { values: { value: string; label: string }[] } {
        const result = op.lastResult;
        const items = isPlainRecord(result) && Array.isArray(result.items) ? result.items : [];
        const values: { value: string; label: string }[] = [];
        for (const item of items) {
            if (isPlainRecord(item) && typeof item[idField] === 'string') {
                values.push({ value: item[idField] as string, label: typeof item.name === 'string' ? item.name : (item[idField] as string) });
            }
        }
        return { values };
    }

    override renderBody() {
        const draft = this._activeForm.draft;
        const setField = (f: string) => (e: CustomEvent) => this._activeForm.setField(f, e.detail.value);
        const fields = html`
            <platform-field
                type="string" mode="edit"
                .label=${this.t('settings.name')}
                .value=${typeof draft.name === 'string' ? draft.name : ''}
                required
                data-location-name
                @change=${setField('name')}
            ></platform-field>
            <platform-field
                type="string" mode="edit"
                .label=${this.t('explorer.barcode')}
                .value=${typeof draft.barcode === 'string' ? draft.barcode : ''}
                data-location-barcode
                @change=${setField('barcode')}
            ></platform-field>
            <platform-field
                type="number" mode="edit"
                .label=${this.t('explorer.pick_sequence')}
                .value=${typeof draft.pick_sequence === 'number' ? draft.pick_sequence : 0}
                data-location-pick-seq
                @change=${setField('pick_sequence')}
            ></platform-field>
            <platform-field
                type="boolean" mode="edit"
                .label=${this.t('explorer.allow_negative')}
                .value=${draft.allow_negative === true}
                data-location-allow-neg
                @change=${setField('allow_negative')}
            ></platform-field>
        `;
        if (this._editing) {
            return html`
                <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                    ${fields}
                    <platform-field
                        type="boolean" mode="edit"
                        .label=${this.t('explorer.blocked_putaway')}
                        .value=${draft.putaway_blocked === true}
                        data-location-putaway-blocked
                        @change=${setField('putaway_blocked')}
                    ></platform-field>
                    <platform-field
                        type="boolean" mode="edit"
                        .label=${this.t('explorer.blocked_removal')}
                        .value=${draft.removal_blocked === true}
                        data-location-removal-blocked
                        @change=${setField('removal_blocked')}
                    ></platform-field>
                    <platform-field
                        type="boolean" mode="edit"
                        .label=${this.t('settings.is_active')}
                        .value=${draft.is_active !== false}
                        data-location-active
                        @change=${setField('is_active')}
                    ></platform-field>
                </form>
            `;
        }
        const usage = typeof draft.usage === 'string' ? draft.usage : 'bin';
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                ${fields}
                <platform-segmented-control
                    full-width density="compact"
                    .value=${usage}
                    .items=${this._usageItems()}
                    .ariaLabel=${this.t('settings.usage')}
                    data-location-usage
                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._form.setField('usage', e.detail.value)}
                ></platform-segmented-control>
                ${usage === 'container' ? html`
                    <platform-field
                        type="enum" mode="edit"
                        .label=${this.t('packages.type')}
                        .value=${typeof draft.container_type_id === 'string' ? draft.container_type_id : ''}
                        .config=${this._typeOptions(this._containerTypes, 'container_type_id')}
                        required
                        data-location-container-type
                        @change=${setField('container_type_id')}
                    ></platform-field>
                ` : html`
                    <platform-field
                        type="enum" mode="edit"
                        .label=${this.t('settings.type_field')}
                        .value=${typeof draft.storage_type_id === 'string' ? draft.storage_type_id : ''}
                        .config=${this._typeOptions(this._storageTypes, 'storage_type_id')}
                        data-location-storage-type
                        @change=${setField('storage_type_id')}
                    ></platform-field>
                `}
            </form>
        `;
    }
}

customElements.define('stock-location-modal', StockLocationModal);
registerModalKind(StockLocationModal.modalKind, 'stock-location-modal');
