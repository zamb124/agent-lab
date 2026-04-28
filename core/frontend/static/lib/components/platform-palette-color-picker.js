/**
 * Выбор цвета из платформенной палитры (COLOR_PALETTE).
 * Наружу всегда hex из entry.dot; значения-ключи палитры при отображении совпадают со свотчем.
 * Значение #rrggbb вне палитры — отдельный свотч; выбор из палитры заменяет его.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { COLOR_PALETTE } from '../utils/color-palette.js';

/**
 * @param {string | undefined | null} raw
 * @returns {{ mode: 'empty' | 'palette' | 'custom' | 'unknown', emitted: string }}
 */
function parsePickerValue(raw) {
    const s = typeof raw === 'string' ? raw.trim() : '';
    if (!s) {
        return { mode: 'empty', emitted: '' };
    }
    for (const p of COLOR_PALETTE) {
        if (s.toLowerCase() === p.key.toLowerCase()) {
            return { mode: 'palette', emitted: p.dot };
        }
        if (s.toLowerCase() === p.dot.toLowerCase()) {
            return { mode: 'palette', emitted: p.dot };
        }
    }
    if (/^#[0-9a-f]{6}$/i.test(s)) {
        return { mode: 'custom', emitted: s };
    }
    return { mode: 'unknown', emitted: s };
}

export class PlatformPaletteColorPicker extends PlatformElement {
    static i18nNamespace = 'platform';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-width: 0;
            }
            .wrap {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }
            .swatches {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                flex: 1;
                min-width: 0;
                overflow-x: auto;
                overflow-y: hidden;
                padding-bottom: 2px;
                scrollbar-width: thin;
                -webkit-overflow-scrolling: touch;
            }
            .swatch {
                width: 22px;
                height: 22px;
                border: none;
                border-radius: 50%;
                padding: 0;
                cursor: pointer;
                flex-shrink: 0;
                box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 12%, transparent);
            }
            .swatch:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .swatch:focus-visible {
                outline: none;
                box-shadow:
                    0 0 0 2px var(--glass-solid-strong, #fff),
                    0 0 0 4px color-mix(in srgb, var(--accent, #3f4959) 55%, transparent);
            }
            .swatch.active {
                box-shadow:
                    0 0 0 2px var(--glass-solid-strong, #fff),
                    0 0 0 4px color-mix(in srgb, #3f4959 55%, transparent);
            }
            .clear {
                flex-shrink: 0;
                font-size: var(--text-xs);
                padding: 4px var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle, var(--border-subtle));
                background: var(--glass-solid-medium, var(--glass-solid-subtle));
                color: var(--text-secondary);
                cursor: pointer;
                white-space: nowrap;
            }
            .clear:hover:not(:disabled) {
                border-color: var(--accent, #3b82f6);
                color: var(--text-primary);
            }
            .clear:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `,
    ];

    static properties = {
        value: { type: String },
        disabled: { type: Boolean, reflect: true },
        allowClear: { type: Boolean, attribute: 'allow-clear' },
    };

    constructor() {
        super();
        this.value = '';
        this.disabled = false;
        this.allowClear = false;
    }

    _emit(next) {
        const v = typeof next === 'string' ? next : '';
        this.dispatchEvent(new CustomEvent('input', {
            detail: { value: v },
            bubbles: true,
            composed: true,
        }));
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: v },
            bubbles: true,
            composed: true,
        }));
    }

    _onPickPalette(entry) {
        if (this.disabled) return;
        this._emit(entry.dot);
    }

    _onClear(ev) {
        ev.preventDefault();
        if (this.disabled) return;
        this._emit('');
    }

    render() {
        const parsed = parsePickerValue(this.value);
        const hasSomething = parsed.mode !== 'empty';
        const showCustom = parsed.mode === 'custom';

        return html`
            <div class="wrap">
                ${this.allowClear && hasSomething
                    ? html`
                        <button
                            type="button"
                            class="clear"
                            ?disabled=${this.disabled}
                            @click=${this._onClear}
                        >
                            ${this.t('palette_color_picker.clear')}
                        </button>
                    `
                    : ''}
                <div class="swatches" role="list">
                    ${showCustom
                        ? html`
                            <button
                                type="button"
                                class="swatch active"
                                ?disabled=${this.disabled}
                                style=${`background:${parsed.emitted};`}
                                title=${parsed.emitted}
                                aria-label=${parsed.emitted}
                            ></button>
                        `
                        : ''}
                    ${COLOR_PALETTE.map((entry) => {
                        const isActive = parsed.mode === 'palette'
                            && entry.dot.toLowerCase() === parsed.emitted.toLowerCase();
                        return html`
                            <button
                                type="button"
                                class="swatch ${isActive ? 'active' : ''}"
                                ?disabled=${this.disabled}
                                style=${`background:${entry.dot};`}
                                title="${entry.key} ${entry.dot}"
                                aria-label="${entry.key} ${entry.dot}"
                                @click=${() => this._onPickPalette(entry)}
                            ></button>
                        `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('platform-palette-color-picker', PlatformPaletteColorPicker);
