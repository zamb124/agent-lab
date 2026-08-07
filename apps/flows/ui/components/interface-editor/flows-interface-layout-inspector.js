/**
 * Grid-first layout inspector: visual column span + container gap.
 * Position/alignment is canvas DnD + E/W resize — no justify/align chips.
 * Band overrides and row_span live under Advanced.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import { resolvedPlacement } from '@platform/lib/flow-ui/layout/grid-contract.js';

const BANDS = ['wide', 'medium', 'compact'];
const GAP_TOKENS = ['space.0', 'space.1', 'space.2', 'space.3', 'space.4', 'space.6', 'space.8'];
const WIDE_COLUMNS = 12;

export class FlowsInterfaceLayoutInspector extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        component: { attribute: false },
        band: { type: String },
        advancedOpen: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; gap: 12px; }
        .section {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: var(--text-tertiary);
            margin-top: 4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
        }
        .bands { display: inline-flex; gap: 3px; }
        .band {
            border: 1px solid var(--border-subtle);
            color: var(--text-tertiary);
            border-radius: 999px;
            font-size: 10px;
            font-weight: 700;
            padding: 3px 9px;
            cursor: pointer;
            position: relative;
            text-transform: none;
            display: inline-flex;
            align-items: center;
        }
        .band:focus-visible, .reset:focus-visible, .chip:focus-visible, .span-cell:focus-visible,
        .advanced-toggle:focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 1px;
        }
        .band[data-active="true"] {
            border-color: var(--accent);
            color: var(--accent);
            background: var(--accent-subtle);
        }
        .band[data-override="true"]::after {
            content: '';
            position: absolute;
            top: -2px;
            right: -2px;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--accent);
        }
        .reset {
            color: var(--accent);
            font-size: 11px;
            cursor: pointer;
            text-transform: none;
            font-weight: 600;
            justify-self: start;
        }
        .label {
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 600;
        }
        .span-track {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 2px;
            min-height: 28px;
        }
        .chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--border-subtle);
            background: var(--bg-elevated);
            color: var(--text-secondary);
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            min-width: 32px;
            height: 30px;
            padding: 0 8px;
            cursor: pointer;
            box-sizing: border-box;
        }
        .span-cell {
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            background: var(--bg-elevated);
            cursor: pointer;
            min-height: 26px;
            box-sizing: border-box;
        }
        .span-cell[data-active="true"] {
            background: var(--accent-subtle);
            border-color: var(--accent);
        }
        .span-cell[data-full="true"] {
            background: var(--accent);
            border-color: var(--accent);
            opacity: .55;
        }
        .chips { display: inline-flex; gap: 4px; flex-wrap: wrap; }
        .chip[data-active="true"] {
            border-color: var(--accent);
            color: var(--accent);
            background: var(--accent-subtle);
        }
        .advanced-toggle {
            border: 0;
            background: transparent;
            color: var(--text-tertiary);
            font: inherit;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            cursor: pointer;
            text-align: left;
            padding: 4px 0;
        }
        .advanced-toggle:hover { color: var(--accent); }
    `];

    constructor() {
        super();
        this.component = null;
        this.band = 'wide';
        this.advancedOpen = false;
    }

    _patch(patch) {
        this.emit('placement-patch', {
            band: this.band === 'wide' ? 'base' : this.band,
            patch,
        });
    }

    _layout(patch) {
        this.emit('layout-patch', { patch });
    }

    _placement() {
        const component = this.component;
        if (!component?.placement) {
            return {};
        }
        const band = this.band === 'base' ? 'wide' : (this.band || 'wide');
        return resolvedPlacement(component.placement, band);
    }

    _hasOverride(band) {
        const overrides = this.component?.placement?.overrides?.[band];
        return overrides != null && Object.keys(overrides).length > 0;
    }

    _bandColumns() {
        if (this.band === 'compact') return 4;
        if (this.band === 'medium') return 8;
        return WIDE_COLUMNS;
    }

    _spanValue(placement) {
        const span = placement.column_span;
        if (span === 'full' || span == null) return 'full';
        const parsed = Number(span);
        if (!Number.isInteger(parsed) || parsed < 1) return 'full';
        return Math.min(parsed, this._bandColumns());
    }

    _setSpan(span) {
        this._patch({ column_span: span });
    }

    _spanTrack(placement) {
        const span = this._spanValue(placement);
        const columns = this._bandColumns();
        const activeCount = span === 'full' ? columns : span;
        return html`
            <div class="label">${this.t('interface_editor.layout_width')}</div>
            <div class="span-track" role="group" aria-label=${this.t('interface_editor.layout_width')}>
                ${Array.from({ length: columns }, (_, index) => {
                    const size = index + 1;
                    const filled = size <= activeCount;
                    return html`<article
                        class="span-cell"
                        role="button"
                        tabindex="0"
                        data-active=${filled && span !== 'full' ? 'true' : 'false'}
                        data-full=${span === 'full' ? 'true' : 'false'}
                        title=${String(size)}
                        aria-label=${this.t('interface_editor.layout_width_n', { n: size })}
                        @click=${() => this._setSpan(size === columns ? 'full' : size)}
                        @keydown=${(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                this._setSpan(size === columns ? 'full' : size);
                            }
                        }}
                    ></article>`;
                })}
            </div>
            <div class="chips">
                <article
                    class="chip"
                    role="button"
                    tabindex="0"
                    data-active=${span === 'full' ? 'true' : 'false'}
                    @click=${() => this._setSpan('full')}
                    @keydown=${(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            this._setSpan('full');
                        }
                    }}
                >${this.t('interface_editor.layout_width_full')}</article>
            </div>
        `;
    }

    _containerSection(layout) {
        if (!layout || layout.mode !== 'grid') return nothing;
        return html`
            <div class="section"><span>${this.t('interface_editor.layout_container')}</span></div>
            <platform-field
                type="enum"
                .label=${this.t('interface_editor.layout_gap')}
                .value=${layout.grid?.column_gap_token || 'space.4'}
                .config=${{ values: GAP_TOKENS }}
                mode="edit"
                @change=${(event) => this._layout({ gap: event.detail.value })}
            ></platform-field>
        `;
    }

    _advancedSection(placement) {
        return html`
            <article
                class="advanced-toggle"
                role="button"
                tabindex="0"
                aria-expanded=${this.advancedOpen ? 'true' : 'false'}
                @click=${() => { this.advancedOpen = !this.advancedOpen; }}
                @keydown=${(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        this.advancedOpen = !this.advancedOpen;
                    }
                }}
            >${this.t('interface_editor.layout_advanced')}</article>
            ${this.advancedOpen ? html`
                <div class="section">
                    <span>${this.t('interface_editor.layout_bands')}</span>
                    <span class="bands">${BANDS.map((band) => html`
                        <span
                            class="band"
                            role="button"
                            tabindex="0"
                            aria-pressed=${band === this.band ? 'true' : 'false'}
                            data-active=${band === this.band ? 'true' : 'false'}
                            data-override=${band !== 'wide' && this._hasOverride(band) ? 'true' : 'false'}
                            @click=${() => this.emit('band-change', { band })}
                            @keydown=${(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault();
                                    this.emit('band-change', { band });
                                }
                            }}
                        >${band === 'wide' ? '12' : band === 'medium' ? '8' : '4'}</span>
                    `)}</span>
                </div>
                ${this.band !== 'wide' && this._hasOverride(this.band)
                    ? html`<span
                        class="reset"
                        role="button"
                        tabindex="0"
                        @click=${() => this.emit('placement-reset', { band: this.band })}
                        @keydown=${(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                this.emit('placement-reset', { band: this.band });
                            }
                        }}
                    >${this.t('interface_editor.layout_reset_override')}</span>`
                    : nothing}
            ` : nothing}
        `;
    }

    render() {
        const component = this.component;
        if (!component) return nothing;
        const placement = this._placement();
        const rowStart = Number.isInteger(placement.row_start) ? placement.row_start : 1;
        const rowSpan = Number.isInteger(placement.row_span) ? placement.row_span : 1;
        return html`
            <div class="section"><span>${this.t('interface_editor.layout_placement')}</span></div>
            ${this._spanTrack(placement)}
            <platform-field
                type="number"
                .label=${this.t('interface_editor.layout_row_start')}
                .value=${rowStart}
                mode="edit"
                @change=${(event) => this._patch({
                    row_start: Math.max(1, Number(event.detail.value)),
                })}
            ></platform-field>
            <platform-field
                type="number"
                .label=${this.t('interface_editor.layout_row_span')}
                .value=${rowSpan}
                mode="edit"
                @change=${(event) => this._patch({
                    row_span: Math.max(1, Number(event.detail.value)),
                })}
            ></platform-field>
            ${this._containerSection(component.container_layout)}
            ${this._advancedSection(placement)}
        `;
    }
}

if (!customElements.get('flows-interface-layout-inspector')) {
    customElements.define('flows-interface-layout-inspector', FlowsInterfaceLayoutInspector);
}
