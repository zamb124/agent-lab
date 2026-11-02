/**
 * ShopHoursEditor — недельное расписание заведения.
 *
 * День — строка: имя дня, два enum-выпадающих списка времени (слоты 30 мин),
 * переключатель «работаем/выходной» и копия расписания дня на всю неделю.
 * Значение — массив из 7 `{ open, close, closed }`, вход через prop `hours`,
 * наружу — событие `change` `{ hours }`.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';

export interface ShopDayHours {
    open: string;
    close: string;
    closed: boolean;
}

const TIME_SLOTS: string[] = Array.from({ length: 48 }, (_, i) => {
    const hh = String(Math.floor(i / 2)).padStart(2, '0');
    const mm = i % 2 === 0 ? '00' : '30';
    return `${hh}:${mm}`;
});

const TIME_RE = /^\d{2}:\d{2}$/;

function _slotOptions(value: string): Array<{ value: string; label: string }> {
    const options: Array<{ value: string; label: string }> = TIME_SLOTS.map((v) => ({ value: v, label: v }));
    if (value !== '' && TIME_RE.test(value) && !TIME_SLOTS.includes(value)) {
        options.push({ value, label: value });
        options.sort((a, b) => a.value.localeCompare(b.value));
    }
    return options;
}

export class ShopHoursEditor extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        hours: { attribute: false },
    };
    declare hours: ShopDayHours[];

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .presets {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                margin-bottom: var(--space-4);
            }
            .preset {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                transition: border-color var(--motion-duration-micro),
                            color var(--motion-duration-micro),
                            background var(--motion-duration-micro);
            }
            .preset:hover {
                border-color: var(--accent);
                color: var(--accent);
            }
            .days { display: flex; flex-direction: column; gap: var(--space-2); }
            .day {
                display: grid;
                grid-template-columns: minmax(96px, 130px) minmax(0, 1fr) auto auto;
                grid-template-areas: "name range toggle copy";
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
                transition: opacity var(--motion-duration-micro);
            }
            .day.off { opacity: 0.65; }
            .day-name {
                grid-area: name;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            .day.off .day-name { color: var(--text-tertiary); }
            .range {
                grid-area: range;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .range platform-field { flex: 1; min-width: 0; }
            .dash { color: var(--text-tertiary); flex-shrink: 0; }
            .closed-tag {
                grid-area: range;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            platform-switch { grid-area: toggle; }
            .copy-day {
                grid-area: copy;
                border: 0;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-sm);
                padding: 0;
            }
            .copy-day:hover { color: var(--accent); }
            @media (max-width: 640px) {
                .day {
                    grid-template-columns: 1fr auto;
                    grid-template-areas: "name toggle" "range range";
                    gap: var(--space-2) var(--space-3);
                }
                .copy-day { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this.hours = [];
    }

    private _emit(hours: ShopDayHours[]) {
        this.emit('change', { hours });
    }

    private _setDay(index: number, patch: Partial<ShopDayHours>) {
        this._emit(this.hours.map((day, i) => (i === index ? { ...day, ...patch } : day)));
    }

    private _applyPreset(mode: 'daily' | 'weekdays' | 'clear') {
        if (mode === 'daily') {
            this._emit(Array.from({ length: 7 }, () => ({ open: '09:00', close: '22:00', closed: false })));
            return;
        }
        if (mode === 'weekdays') {
            this._emit(Array.from({ length: 7 }, (_, i) =>
                i < 5 ? { open: '09:00', close: '18:00', closed: false } : { open: '', close: '', closed: true }));
            return;
        }
        this._emit(Array.from({ length: 7 }, () => ({ open: '', close: '', closed: true })));
    }

    private _copyToAll(index: number) {
        const source = this.hours[index];
        if (source === undefined) return;
        this._emit(this.hours.map(() => ({ ...source })));
    }

    private _onTimeChange(index: number, key: 'open' | 'close', e: CustomEvent<{ value?: unknown }>) {
        const value = typeof e.detail.value === 'string' ? e.detail.value : '';
        this._setDay(index, { [key]: value });
    }

    private _onToggle(index: number, e: CustomEvent<{ value?: unknown }>) {
        const day = this.hours[index];
        if (day === undefined) return;
        const working = Boolean(e.detail.value);
        if (!working) {
            this._setDay(index, { closed: true });
            return;
        }
        this._setDay(index, {
            closed: false,
            open: day.open === '' ? '09:00' : day.open,
            close: day.close === '' ? '22:00' : day.close,
        });
    }

    override render(): TemplateResult {
        return html`
            <div class="presets">
                <button class="preset" @click=${() => this._applyPreset('daily')}>${this.t('settings.preset_daily')}</button>
                <button class="preset" @click=${() => this._applyPreset('weekdays')}>${this.t('settings.preset_weekdays')}</button>
                <button class="preset" @click=${() => this._applyPreset('clear')}>${this.t('settings.preset_clear')}</button>
            </div>
            <div class="days">
                ${this.hours.map((day, index) => html`
                    <div class="day ${day.closed ? 'off' : ''}">
                        <span class="day-name">${this.t(`settings.day_${index}`)}</span>
                        ${day.closed
                            ? html`<span class="closed-tag">${this.t('settings.closed_label')}</span>`
                            : html`
                                <span class="range">
                                    <platform-field
                                        type="enum"
                                        mode="edit"
                                        .value=${day.open}
                                        .config=${{ values: _slotOptions(day.open) }}
                                        pill-density="compact"
                                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onTimeChange(index, 'open', e)}
                                    ></platform-field>
                                    <span class="dash">—</span>
                                    <platform-field
                                        type="enum"
                                        mode="edit"
                                        .value=${day.close}
                                        .config=${{ values: _slotOptions(day.close) }}
                                        pill-density="compact"
                                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onTimeChange(index, 'close', e)}
                                    ></platform-field>
                                </span>`}
                        <platform-switch
                            ?checked=${!day.closed}
                            title=${this.t('settings.day_toggle')}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._onToggle(index, e)}
                        ></platform-switch>
                        <button class="copy-day" title=${this.t('settings.copy_all')} @click=${() => this._copyToAll(index)}>
                            <platform-icon name="copy" size="15"></platform-icon>
                        </button>
                    </div>
                `)}
            </div>
        `;
    }
}

customElements.define('shop-hours-editor', ShopHoursEditor);
