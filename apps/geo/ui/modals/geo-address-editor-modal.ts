/**
 * GeoAddressEditorModal — создание и правка адреса админом.
 *
 * openModal('geo.address_editor', { address: GeoAddressHit | null, onApply }).
 * address === null → режим «новый ручной адрес» (source=manual, gen0);
 * address задан → патч поверх OSM/manual (evergreen-оверлей на бэкенде).
 * Координаты — draggable-маркер на <platform-map> + числовые поля.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-map.js';
import type { PlatformMapConfig } from '@platform/lib/components/platform-map.js';
import '@platform/lib/events/resources/geo-admin.resource.js';
import type {
    geoAddressCreateOp,
    geoAddressUpdateOp,
} from '@platform/lib/events/resources/geo-admin.resource.js';
import type { GeoAddressHit } from '@platform/lib/events/wire/geo.gen.js';

export class GeoAddressEditorModal extends PlatformFormModal {
    static modalKind = 'geo.address_editor';
    static i18nNamespace = 'geo';

    declare address: GeoAddressHit | null;
    declare onApply: (() => void) | null;

    declare _displayName: string;
    declare _city: string;
    declare _street: string;
    declare _housenumber: string;
    declare _postcode: string;
    declare _region: string;
    declare _lat: number | null;
    declare _lng: number | null;
    declare _reason: string;
    declare _mapConfig: PlatformMapConfig;

    private _createCtl: OpControllerOf<typeof geoAddressCreateOp> | null = null;
    private _updateCtl: OpControllerOf<typeof geoAddressUpdateOp> | null = null;

    static override properties: PropertyDeclarations = {
        address: { type: Object, attribute: false },
        onApply: { attribute: false },
        _displayName: { state: true },
        _city: { state: true },
        _street: { state: true },
        _housenumber: { state: true },
        _postcode: { state: true },
        _region: { state: true },
        _lat: { state: true },
        _lng: { state: true },
        _reason: { state: true },
        _mapConfig: { state: true },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.address = null;
        this.onApply = null;
        this._displayName = '';
        this._city = '';
        this._street = '';
        this._housenumber = '';
        this._postcode = '';
        this._region = '';
        this._lat = null;
        this._lng = null;
        this._reason = '';
        this._mapConfig = {};
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._createCtl = this.useOp('geo/addresses_create');
        this._updateCtl = this.useOp('geo/addresses_update');
        const a = this.address;
        if (a) {
            this._displayName = a.display_name;
            this._city = a.city ?? '';
            this._street = a.street ?? '';
            this._housenumber = a.housenumber ?? '';
            this._postcode = a.postcode ?? '';
            this._lat = a.lat;
            this._lng = a.lng;
        }
        this._mapConfig = this._buildMapConfig();
        this.title = this.t(
            a ? 'address_editor.title_edit' : 'address_editor.title_create',
        );
    }

    private get _isCreate(): boolean {
        return this.address === null;
    }

    private _buildMapConfig(): PlatformMapConfig {
        const marker =
            this._lat !== null && this._lng !== null
                ? [{ key: 'addr', lngLat: [this._lng, this._lat] as [number, number], draggable: true }]
                : [];
        const config: PlatformMapConfig = {
            interactive: true,
            zoom: this._lat !== null ? 16 : 11,
            controls: { zoom: true, layers: true, locate: true },
            markers: marker,
        };
        if (this._lat !== null && this._lng !== null) {
            config.center = [this._lng, this._lat];
        }
        return config;
    }

    private _onMarkerDrag = (e: Event): void => {
        const d = (e as CustomEvent<{ key?: string; lngLat: [number, number] }>).detail;
        if (d.key !== 'addr') return;
        this._lng = d.lngLat[0];
        this._lat = d.lngLat[1];
        this.isDirty = true;
    };

    private _onMapClick = (e: Event): void => {
        const d = (e as CustomEvent<{ lngLat: [number, number] }>).detail;
        this._lng = d.lngLat[0];
        this._lat = d.lngLat[1];
        this._mapConfig = this._buildMapConfig();
        this.isDirty = true;
    };

    private _setCoord(kind: 'lat' | 'lng', value: string): void {
        const num = Number(value);
        if (!Number.isFinite(num)) return;
        if (kind === 'lat') this._lat = num; else this._lng = num;
        this._mapConfig = this._buildMapConfig();
        this.isDirty = true;
    }

    private _field(
        key: string,
        value: string,
        set: (v: string) => void,
    ): TemplateResult {
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=${this.t(`address_editor.label_${key}`)}
                .value=${value}
                .error=${this.fieldError(key)}
                @change=${(e: CustomEvent) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error(`address-editor: ${key} expects detail.value string`);
                    }
                    set(e.detail.value);
                    this.isDirty = true;
                }}
            ></platform-field>
        `;
    }

    override validateForm(): Record<string, string> {
        const errors: Record<string, string> = {};
        if (!this._displayName.trim()) {
            errors.display_name = this.t('address_editor.err_display_name');
        }
        if (this._lat === null || this._lng === null) {
            errors.lat = this.t('address_editor.err_point');
        }
        if (this._isCreate && !this._region.trim()) {
            errors.region = this.t('address_editor.err_region');
        }
        return errors;
    }

    override async handleSubmit(): Promise<void> {
        const lat = this._lat;
        const lng = this._lng;
        if (lat === null || lng === null) return;
        const common = {
            display_name: this._displayName.trim(),
            city: this._city.trim(),
            street: this._street.trim(),
            housenumber: this._housenumber.trim(),
            postcode: this._postcode.trim(),
            lat,
            lng,
        };
        if (this._isCreate) {
            await this._createCtl?.run({
                ...common,
                region: this._region.trim(),
                reason: this._reason.trim() || undefined,
            });
        } else {
            const a = this.address;
            if (!a) return;
            await this._updateCtl?.run({
                osm_type: a.osm_type,
                osm_id: a.osm_id,
                ...common,
                reason: this._reason.trim() || undefined,
            });
        }
        this.onApply?.();
        this.closeAfterSave();
    }

    override renderBody(): TemplateResult {
        return html`
            <form @submit=${this._onSubmit}>
                <div class="editor-grid">
                    <div class="fields-col">
                        <div class="form-group">
                            ${this._field('display_name', this._displayName, (v) => (this._displayName = v))}
                        </div>
                        <div class="form-group">
                            ${this._field('city', this._city, (v) => (this._city = v))}
                        </div>
                        <div class="form-group">
                            ${this._field('street', this._street, (v) => (this._street = v))}
                        </div>
                        <div class="form-group">
                            ${this._field('housenumber', this._housenumber, (v) => (this._housenumber = v))}
                        </div>
                        <div class="form-group">
                            ${this._field('postcode', this._postcode, (v) => (this._postcode = v))}
                        </div>
                        ${this._isCreate
                            ? html`
                                  <div class="form-group">
                                      ${this._field('region', this._region, (v) => (this._region = v))}
                                  </div>`
                            : ''}
                        <div class="form-group">
                            ${this._field('reason', this._reason, (v) => (this._reason = v))}
                        </div>
                        <div class="form-row">
                            <platform-field
                                type="number"
                                mode="edit"
                                label="lat"
                                .value=${this._lat === null ? '' : String(this._lat)}
                                .error=${this.fieldError('lat')}
                                @change=${(e: CustomEvent) => this._setCoord('lat', String(e.detail?.value ?? ''))}
                            ></platform-field>
                            <platform-field
                                type="number"
                                mode="edit"
                                label="lng"
                                .value=${this._lng === null ? '' : String(this._lng)}
                                @change=${(e: CustomEvent) => this._setCoord('lng', String(e.detail?.value ?? ''))}
                            ></platform-field>
                        </div>
                        <div class="map-hint">${this.t('address_editor.map_hint')}</div>
                    </div>
                    <div class="map-col">
                        <platform-map
                            .config=${this._mapConfig}
                            @pm-marker-drag=${this._onMarkerDrag}
                            @pm-click=${this._onMapClick}
                        ></platform-map>
                    </div>
                </div>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        const canSubmit =
            this._displayName.trim().length > 0 &&
            this._lat !== null &&
            this._lng !== null &&
            !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('address_editor.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading
                        ? this.t('address_editor.saving')
                        : this.t('address_editor.submit')}
                </button>
            </div>
        `;
    }

    static override styles = [
        PlatformFormModal.styles,
        css`
            .editor-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: var(--space-4);
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            .map-col {
                min-height: 320px;
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            .map-col platform-map {
                display: block;
                width: 100%;
                height: 100%;
            }
            .map-hint {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            @media (max-width: 900px) {
                .editor-grid { grid-template-columns: 1fr; }
                .map-col { min-height: 220px; }
            }
        `,
    ];
}

customElements.define('geo-address-editor-modal', GeoAddressEditorModal);
registerModalKind(GeoAddressEditorModal.modalKind, 'geo-address-editor-modal');

declare global {
    interface HTMLElementTagNameMap {
        'geo-address-editor-modal': GeoAddressEditorModal;
    }
}
