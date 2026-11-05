/**
 * GeoLayerPanel — панель переключения канонических слоёв карты.
 *
 * Список — из `geo/layers` (реестр + счётчики фич); видимость — slice
 * `geo/map` (`hidden`), переключение действием `toggle`. Ставится рядом
 * с `<geo-map>` на любой странице: состояние общее, все карты приложения
 * слушают один и тот же slice.
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { OpControllerOf, SliceControllerOf } from '@platform/lib/base/use-resource.js';
import type { GeoLayerInfo } from '../events/wire/geo.gen.js';
import type { geoLayersOp } from '../events/resources/geo-layers.resource.js';
import { geoMapSlice } from '../events/resources/geo-layers.resource.js';
import '../events/resources/geo-layers.resource.js';
import './platform-icon.js';

export class GeoLayerPanel extends PlatformElement {
    static i18nNamespace = 'geo';

    private _layersCtl: OpControllerOf<typeof geoLayersOp>;
    private _mapCtl: SliceControllerOf<typeof geoMapSlice>;

    static override properties = {
        _expanded: { state: true },
    };

    declare _expanded: boolean;

    constructor() {
        super();
        this._expanded = false;
        this._layersCtl = this.useOp('geo/layers');
        this._mapCtl = this.useSlice('geo/map');
    }

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .panel {
                min-width: 180px;
                border-radius: var(--radius-m, 12px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 94%, transparent);
                backdrop-filter: blur(12px);
                border: 1px solid color-mix(in srgb, var(--text-primary) 10%, transparent);
                box-shadow: 0 6px 22px color-mix(in srgb, var(--text-primary) 12%, transparent);
                overflow: hidden;
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                background: transparent;
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                cursor: pointer;
            }
            .head platform-icon { color: var(--text-tertiary); }
            .items { display: flex; flex-direction: column; padding: 0 var(--space-2) var(--space-2); }
            .item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
                user-select: none;
            }
            .item input { accent-color: var(--accent); margin: 0; }
            .swatch {
                width: 10px;
                height: 10px;
                border-radius: 3px;
                flex-shrink: 0;
            }
            .count { margin-left: auto; color: var(--text-tertiary); font-size: var(--text-xs); }
        `,
    ];

    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._layersCtl.lastResult && !this._layersCtl.busy) {
            void this._layersCtl.run({});
        }
    }

    private _isVisible(name: string): boolean {
        return this._mapCtl.value.hidden[name] !== true;
    }

    private _renderLayer(layer: GeoLayerInfo): TemplateResult {
        const visible = this._isVisible(layer.name);
        return html`
            <label class="item">
                <input
                    type="checkbox"
                    .checked=${visible}
                    @change=${() => this._mapCtl.toggle({ name: layer.name })}
                />
                <span class="swatch" style="background:${layer.color}"></span>
                <span>${this.t(`layers.${layer.name}`)}</span>
                <span class="count">${layer.features}</span>
            </label>
        `;
    }

    protected override render(): TemplateResult {
        const layers = this._layersCtl.lastResult?.layers ?? [];
        return html`
            <div class="panel">
                <button type="button" class="head" @click=${() => { this._expanded = !this._expanded; }}>
                    <platform-icon name="layers" size="14"></platform-icon>
                    ${this.t('layers.title')}
                    <platform-icon name=${this._expanded ? 'chevron-up' : 'chevron-down'} size="14"></platform-icon>
                </button>
                ${this._expanded
                    ? html`<div class="items">${layers.map((layer) => this._renderLayer(layer))}</div>`
                    : html``}
            </div>
        `;
    }
}

if (!customElements.get('geo-layer-panel')) {
    customElements.define('geo-layer-panel', GeoLayerPanel);
}
