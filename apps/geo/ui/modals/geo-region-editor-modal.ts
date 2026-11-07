/**
 * GeoRegionEditorModal — создание и правка региона покрытия.
 *
 * openModal('geo.region_editor', { region: GeoRegionItem | null, onApply }).
 * region === null → create; задан → update (name read-only — slug-ключ).
 * Поля — по GeoRegionUpsertRequest: slug/title/kind/bbox/extract_urls/
 * replication_url/enabled.
 */
import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type { ResourceControllerOf } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/events/resources/geo-coverage.resource.js';
import type { geoRegionsResource } from '@platform/lib/events/resources/geo-coverage.resource.js';
import type { GeoRegionItem } from '@platform/lib/events/wire/geo.gen.js';

const KINDS = ['city', 'region', 'custom'] as const;

export class GeoRegionEditorModal extends PlatformFormModal {
    static modalKind = 'geo.region_editor';
    static i18nNamespace = 'geo';

    declare region: GeoRegionItem | null;
    declare onApply: (() => void) | null;

    declare _name: string;
    declare _title: string;
    declare _kind: string;
    declare _south: string;
    declare _west: string;
    declare _north: string;
    declare _east: string;
    declare _extractUrls: string;
    declare _replicationUrl: string;
    declare _enabled: boolean;

    private _regionsCtl: ResourceControllerOf<typeof geoRegionsResource> | null = null;

    static override properties: PropertyDeclarations = {
        region: { type: Object, attribute: false },
        onApply: { attribute: false },
        _name: { state: true },
        _title: { state: true },
        _kind: { state: true },
        _south: { state: true },
        _west: { state: true },
        _north: { state: true },
        _east: { state: true },
        _extractUrls: { state: true },
        _replicationUrl: { state: true },
        _enabled: { state: true },
    };

    constructor() {
        super();
        this.size = 'md';
        this.region = null;
        this.onApply = null;
        this._name = '';
        this._title = '';
        this._kind = 'city';
        this._south = '';
        this._west = '';
        this._north = '';
        this._east = '';
        this._extractUrls = '';
        this._replicationUrl = '';
        this._enabled = true;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._regionsCtl = this.useResource('geo/regions');
        const r = this.region;
        if (r) {
            this._name = r.name;
            this._title = r.title;
            this._kind = r.kind;
            this._south = String(r.bbox.south);
            this._west = String(r.bbox.west);
            this._north = String(r.bbox.north);
            this._east = String(r.bbox.east);
            this._extractUrls = r.extract_urls.join('\n');
            this._replicationUrl = r.replication_url;
            this._enabled = r.enabled;
        }
        this.title = this.t(
            r ? 'region_editor.title_edit' : 'region_editor.title_create',
        );
    }

    private get _isCreate(): boolean {
        return this.region === null;
    }

    private _num(key: 'south' | 'west' | 'north' | 'east'): number | null {
        const raw = { south: this._south, west: this._west, north: this._north, east: this._east }[key];
        const v = Number(raw);
        return raw.trim() !== '' && Number.isFinite(v) ? v : null;
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
                label=${this.t(`region_editor.label_${key}`)}
                .value=${value}
                .error=${this.fieldError(key)}
                @change=${(e: CustomEvent) => {
                    set(String(e.detail?.value ?? ''));
                    this.isDirty = true;
                }}
            ></platform-field>
        `;
    }

    private _numField(
        key: 'south' | 'west' | 'north' | 'east',
        value: string,
    ): TemplateResult {
        return html`
            <platform-field
                type="number"
                mode="edit"
                label=${this.t(`region_editor.bbox_${key}`)}
                .value=${value}
                .error=${this.fieldError(key)}
                @change=${(e: CustomEvent) => {
                    if (key === 'south') this._south = String(e.detail?.value ?? '');
                    else if (key === 'west') this._west = String(e.detail?.value ?? '');
                    else if (key === 'north') this._north = String(e.detail?.value ?? '');
                    else this._east = String(e.detail?.value ?? '');
                    this.isDirty = true;
                }}
            ></platform-field>
        `;
    }

    override validateForm(): Record<string, string> {
        const errors: Record<string, string> = {};
        if (this._isCreate && !/^[a-z0-9][a-z0-9_-]*$/.test(this._name.trim())) {
            errors.name = this.t('region_editor.err_name');
        }
        const s = this._num('south');
        const w = this._num('west');
        const n = this._num('north');
        const e = this._num('east');
        for (const [k, v] of [['south', s], ['west', w], ['north', n], ['east', e]] as const) {
            if (v === null) errors[k] = this.t('region_editor.err_bbox');
        }
        if (s !== null && n !== null && s >= n) errors.south = this.t('region_editor.err_bbox');
        if (w !== null && e !== null && w >= e) errors.west = this.t('region_editor.err_bbox');
        return errors;
    }

    override async handleSubmit(): Promise<void> {
        const s = this._num('south');
        const w = this._num('west');
        const n = this._num('north');
        const e = this._num('east');
        if (s === null || w === null || n === null || e === null) return;
        const payload = {
            name: this._name.trim(),
            title: this._title.trim(),
            kind: this._kind as (typeof KINDS)[number],
            bbox: { south: s, west: w, north: n, east: e },
            extract_urls: this._extractUrls
                .split('\n')
                .map((u) => u.trim())
                .filter((u) => u !== ''),
            replication_url: this._replicationUrl.trim(),
            enabled: this._enabled,
        };
        if (this._isCreate) this._regionsCtl?.create(payload);
        else this._regionsCtl?.update(this._name, payload);
        this.onApply?.();
        this.closeAfterSave();
    }

    override renderBody(): TemplateResult {
        return html`
            <form @submit=${this._onSubmit}>
                <div class="form-row">
                    <platform-field
                        type="string"
                        mode=${this._isCreate ? 'edit' : 'view'}
                        label=${this.t('region_editor.label_name')}
                        .value=${this._name}
                        .error=${this.fieldError('name')}
                        @change=${(e: CustomEvent) => {
                            this._name = String(e.detail?.value ?? '');
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    ${this._field('title', this._title, (v) => (this._title = v))}
                </div>
                <div class="form-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('region_editor.label_kind')}
                        .value=${this._kind}
                        .config=${{
                            values: KINDS.map((k) => ({
                                value: k,
                                label: this.t(`region_editor.kind_${k}`),
                            })),
                        }}
                        @change=${(e: CustomEvent) => {
                            this._kind = String(e.detail?.value ?? 'city');
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label=${this.t('region_editor.label_enabled')}
                        .value=${this._enabled}
                        @change=${(e: CustomEvent) => {
                            this._enabled = Boolean(e.detail?.value);
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
                <div class="group-title">${this.t('region_editor.bbox_title')}</div>
                <div class="form-row">
                    ${this._numField('south', this._south)}
                    ${this._numField('north', this._north)}
                </div>
                <div class="form-row">
                    ${this._numField('west', this._west)}
                    ${this._numField('east', this._east)}
                </div>
                <div class="form-group">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('region_editor.label_extract')}
                        .value=${this._extractUrls}
                        @change=${(e: CustomEvent) => {
                            this._extractUrls = String(e.detail?.value ?? '');
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    <div class="hint">${this.t('region_editor.hint_extract')}</div>
                </div>
                <div class="form-group">
                    ${this._field('replication_url', this._replicationUrl, (v) => (this._replicationUrl = v))}
                </div>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        const canSubmit =
            this._name.trim().length > 0 &&
            this._num('south') !== null &&
            this._num('north') !== null &&
            this._num('west') !== null &&
            this._num('east') !== null &&
            !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('region_editor.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading
                        ? this.t('region_editor.saving')
                        : this.t('region_editor.submit')}
                </button>
            </div>
        `;
    }

    static override styles = [
        PlatformFormModal.styles,
        css`
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            .group-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin: var(--space-2) 0 var(--space-2);
            }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: var(--space-1); }
        `,
    ];
}

customElements.define('geo-region-editor-modal', GeoRegionEditorModal);
registerModalKind(GeoRegionEditorModal.modalKind, 'geo-region-editor-modal');

declare global {
    interface HTMLElementTagNameMap {
        'geo-region-editor-modal': GeoRegionEditorModal;
    }
}
