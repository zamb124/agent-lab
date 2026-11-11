/**
 * Экран исполнения ТСД (`<stock-tsd-run>`).
 *
 * Подчинён `stock/tsd_session`: backend-машина `ScanContext` диктует шаг —
 * экран показывает ЧТО сканировать дальше, подсказку `expected` из первой
 * открытой строки документа, набранные слоты и строки. Количество вводится
 * клавиатурой (`scan/quantity`), коммит — одной атомарной проводкой.
 * Сам компонент не читает сканер: ввод живёт на рабочем столе и шаги
 * едут через `scan/step` (любой экран, любой скан → своё действие).
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type {
    ScanContext,
    ScanLineDraft,
} from '@platform/lib/events/wire/stock.gen.js';
import type { StockTsdSessionState } from '../../events/resources/stock-tsd.resource.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';

export class StockTsdRun extends PlatformElement {
    static i18nNamespace = 'stock_tsd';

    private _session: ControllerFor<'stock/tsd_session'>;
    private _sessionSel: SelectController<StockTsdSessionState>;
    private _products: ControllerFor<'stock/products'>;
    private _locations: ControllerFor<'stock/locations'>;
    private _quantity: ControllerFor<'stock/scan_quantity'>;
    private _commit: ControllerFor<'stock/scan_commit'>;
    private _countCommit: ControllerFor<'stock/scan_count_commit'>;
    private _qtyInput = '';

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .run {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .run-head {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .run-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 52px;
                height: 52px;
                border-radius: var(--radius-xl);
                background: var(--accent);
                color: var(--text-inverse);
                flex-shrink: 0;
            }
            .run-title {
                margin: 0;
                font-size: var(--text-xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                line-height: var(--leading-tight);
            }
            .run-sub {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .run-close {
                display: flex;
                align-items: center;
                justify-content: center;
                width: var(--tsd-touch-min);
                height: var(--tsd-touch-min);
                margin-left: auto;
                border: 1px solid var(--border-default);
                border-radius: 50%;
                background: var(--bg-surface);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .expected {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px solid var(--tsd-info);
                border-radius: var(--radius-2xl);
                background: var(--tsd-info-subtle);
                font-size: var(--tsd-text-body);
                color: var(--text-primary);
            }
            .expected-icon { color: var(--tsd-info); flex-shrink: 0; }
            .expected-body {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }
            .expected-route {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: var(--font-semibold);
                flex-wrap: wrap;
            }
            .expected-meta {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .step-banner {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6) var(--space-4);
                border: 2px dashed var(--accent);
                border-radius: var(--radius-2xl);
                background: var(--accent-subtle);
                text-align: center;
            }
            .step-banner.review { border-style: solid; border-color: var(--tsd-ok); background: var(--tsd-ok-subtle); }
            .step-banner.error { border-color: var(--tsd-error); background: var(--tsd-error-subtle); }
            .step-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 72px;
                height: 72px;
                border-radius: 50%;
                background: var(--accent);
                color: var(--text-inverse);
            }
            .step-banner.review .step-icon { background: var(--tsd-ok); }
            .step-banner.error .step-icon { background: var(--tsd-error); }
            .step-title {
                margin: 0;
                font-size: var(--tsd-text-title);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }
            .step-hint {
                margin: 0;
                font-size: var(--tsd-text-body);
                color: var(--text-secondary);
            }
            .slots {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .slot {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 40px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                background: var(--tsd-ok-subtle);
                color: var(--tsd-ok);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }
            .qty-panel {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
            }
            .qty-display {
                display: flex;
                align-items: baseline;
                justify-content: center;
                min-height: 72px;
                font-size: 56px;
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .qty-display .empty { color: var(--text-tertiary); font-size: var(--text-2xl); font-weight: var(--font-medium); }
            .qty-fill {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                min-height: 48px;
                border: 1px dashed var(--accent);
                border-radius: var(--radius-xl);
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                cursor: pointer;
            }
            .numpad {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: var(--space-2);
            }
            .numpad button {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 64px;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }
            .numpad button:active { background: var(--bg-secondary); }
            .numpad button.ok {
                grid-column: span 3;
                min-height: 72px;
                border: none;
                background: var(--accent);
                color: var(--text-inverse);
                font-size: var(--tsd-text-title);
            }
            .lines {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .line-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                font-size: var(--text-sm);
            }
            .line-product {
                flex: 1;
                min-width: 0;
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .line-route {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                color: var(--text-secondary);
            }
            .line-qty {
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .commit-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                min-height: var(--tsd-touch-xl);
                border: none;
                border-radius: var(--radius-2xl);
                background: var(--tsd-ok);
                color: var(--text-inverse);
                font-size: var(--tsd-text-title);
                font-weight: var(--font-bold);
                cursor: pointer;
                box-shadow: 0 8px 24px rgba(22, 163, 74, 0.3);
            }
            .commit-btn:disabled { opacity: 0.6; }
        `,
    ];

    constructor() {
        super();
        this._session = this.useSlice('stock/tsd_session');
        this._sessionSel = this.select((s) => s.stockTsdSession as StockTsdSessionState);
        this._products = this.useResource('stock/products');
        this._locations = this.useResource('stock/locations');
        this._quantity = this.useOp('stock/scan_quantity');
        this._commit = this.useOp('stock/scan_commit');
        this._countCommit = this.useOp('stock/scan_count_commit');
    }

    private _productName(productId: string): string {
        const product = this._products.items.find((row) => row.product_id === productId);
        return product === undefined ? productId : product.name;
    }

    private _locationName(locationId: string): string {
        const location = this._locations.items.find((row) => row.location_id === locationId);
        return location === undefined ? locationId : (location.complete_name ?? location.name);
    }

    private _slot(icon: string, text: string): TemplateResult {
        return html`<span class="slot"><platform-icon name=${icon} size="15"></platform-icon>${text}</span>`;
    }

    private _renderExpected(session: StockTsdSessionState): TemplateResult | string {
        const expected = session.expected;
        if (expected === null) return '';
        const parts: TemplateResult[] = [];
        if (expected.location_id !== null && expected.location_id !== undefined) {
            parts.push(html`<span>${this._locationName(expected.location_id)}</span>`);
        }
        if (expected.product_id !== null && expected.product_id !== undefined) {
            parts.push(html`<span>${this._productName(expected.product_id)}</span>`);
        }
        const dest = expected.location_dest_id !== null && expected.location_dest_id !== undefined
            ? this._locationName(expected.location_dest_id) : '';
        if (parts.length === 0 && dest === '') return '';
        return html`
            <div class="expected">
                <platform-icon class="expected-icon" name="zap" size="22"></platform-icon>
                <div class="expected-body">
                    <div class="expected-route">
                        ${parts}
                        ${expected.quantity !== null && expected.quantity !== undefined
                            ? html`<span>×${expected.quantity}</span>` : ''}
                        ${dest !== '' ? html`<platform-icon name="arrow-right" size="16"></platform-icon><span>${dest}</span>` : ''}
                    </div>
                    <div class="expected-meta">${this.t('run.expected_hint')}</div>
                </div>
            </div>
        `;
    }

    private _renderSlots(context: ScanContext): TemplateResult | string {
        const slots: TemplateResult[] = [];
        if (context.source_id !== null && context.source_id !== undefined) {
            slots.push(this._slot('map-pin', this._locationName(context.source_id)));
        }
        if (context.product_id !== null && context.product_id !== undefined) {
            slots.push(this._slot('package', this._productName(context.product_id)));
        }
        if (context.quantity !== null && context.quantity !== undefined) {
            slots.push(this._slot('hash', `×${context.quantity}`));
        }
        if (context.dest_id !== null && context.dest_id !== undefined) {
            slots.push(this._slot('map-pin', `→ ${this._locationName(context.dest_id)}`));
        }
        if (context.container_id !== null && context.container_id !== undefined) {
            slots.push(this._slot('box', this._locationName(context.container_id)));
        }
        if (slots.length === 0) return '';
        return html`<div class="slots">${slots}</div>`;
    }

    private _qtyConfirm(): void {
        const value = Number(this._qtyInput);
        if (this._qtyInput === '' || !Number.isFinite(value) || value <= 0) return;
        const session = this._sessionSel.value;
        if (session.context === null) return;
        const context = session.context;
        void this._quantity.run({
            warehouse_id: this._warehouseId(),
            context,
            quantity: value,
            move_id: session.move_id === '' ? null : session.move_id,
        }).then((response) => {
            if (response === null) throw new Error('stock/scan_quantity: empty response');
            this._session.stepApplied({
                context: response.context,
                resolution: null,
                barcode: '',
                error: response.error ?? null,
                hint: response.hint ?? '',
                expected: response.expected ?? null,
            });
            this._qtyInput = '';
        });
    }

    private _warehouseId(): string {
        const state = this.bus.getState() as Record<string, unknown>;
        const context = state.stockTsdContext as Record<string, unknown> | undefined;
        const warehouseId = context !== undefined ? context.warehouse_id : undefined;
        if (typeof warehouseId !== 'string' || warehouseId === '') {
            throw new Error('stock-tsd-run: warehouse context required');
        }
        return warehouseId;
    }

    private _renderQuantity(session: StockTsdSessionState): TemplateResult | string {
        const context = session.context;
        if (context === null || context.step !== 'quantity') return '';
        const expectedQty = session.expected !== null ? session.expected.quantity : null;
        return html`
            <div class="qty-panel">
                <div class="qty-display">
                    ${this._qtyInput === '' ? html`<span class="empty">${this.t('run.qty_empty')}</span>` : this._qtyInput}
                </div>
                ${expectedQty !== null && expectedQty !== undefined ? html`
                    <button class="qty-fill" @click=${() => { this._qtyInput = String(expectedQty); }}>
                        <platform-icon name="zap" size="16"></platform-icon>
                        ${this.t('run.qty_fill', { qty: String(expectedQty) })}
                    </button>
                ` : ''}
                <div class="numpad">
                    ${['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '.', '⌫'].map((key) => html`
                        <button @click=${() => this._qtyKey(key)}>${key}</button>
                    `)}
                    <button class="ok" ?disabled=${this._quantity.busy || this._qtyInput === ''} @click=${() => this._qtyConfirm()}>
                        ${this._quantity.busy ? html`<platform-spinner size="s"></platform-spinner>` : this.t('run.qty_ok')}
                    </button>
                </div>
            </div>
        `;
    }

    private _qtyKey(key: string): void {
        if (key === '⌫') {
            this._qtyInput = this._qtyInput.slice(0, -1);
        } else if (key === '.' && this._qtyInput.includes('.')) {
            return;
        } else if (this._qtyInput.length < 12) {
            this._qtyInput += key;
        }
        this.requestUpdate();
    }

    private _renderLine(line: ScanLineDraft): TemplateResult {
        const productId = line.product_id ?? '';
        return html`
            <div class="line-row">
                <span class="line-product">${this._productName(productId)}</span>
                <span class="line-route">
                    ${line.location_id !== null && line.location_id !== undefined ? this._locationName(line.location_id) : ''}
                    <platform-icon name="arrow-right" size="13"></platform-icon>
                    ${line.location_dest_id !== null && line.location_dest_id !== undefined ? this._locationName(line.location_dest_id) : ''}
                </span>
                <span class="line-qty">×${line.quantity ?? ''}</span>
            </div>
        `;
    }

    private _commitRun(): void {
        const session = this._sessionSel.value;
        const context = session.context;
        if (context === null) return;
        const warehouseId = this._warehouseId();
        const isCount = context.flow === 'count';
        const run = isCount
            ? this._countCommit.run({ warehouse_id: warehouseId, context, idempotency_key: null })
            : this._commit.run({ move_id: session.move_id, context, idempotency_key: null });
        void run.then(() => {
            this.toast('run.commit_done', { type: 'success' });
            this._session.sessionCleared(null);
        });
    }

    private _renderReview(session: StockTsdSessionState): TemplateResult | string {
        const context = session.context;
        if (context === null || context.step !== 'review') return '';
        const lines = context.lines ?? [];
        const busy = this._commit.busy || this._countCommit.busy;
        return html`
            ${lines.length === 0 ? '' : html`
                <div class="lines">
                    ${lines.map((line) => this._renderLine(line))}
                </div>
            `}
            <button class="commit-btn" ?disabled=${busy} @click=${() => this._commitRun()}>
                ${busy
                    ? html`<platform-spinner size="s"></platform-spinner>`
                    : html`<platform-icon name="check" size="26"></platform-icon>`}
                <span>${this.t('run.commit', { count: lines.length })}</span>
            </button>
        `;
    }

    override render(): TemplateResult {
        const session = this._sessionSel.value;
        const context = session.context;
        if (context === null) return html``;
        const flow = String(context.flow);
        const step = String(context.step);
        const errored = session.outcome === 'error';
        const review = step === 'review';
        return html`
            <div class="run">
                <div class="run-head">
                    <div class="run-icon"><platform-icon name="scan" size="26"></platform-icon></div>
                    <div>
                        <h2 class="run-title">${this.t(`run.flow_${flow}`)}</h2>
                        <p class="run-sub">${this.t(`run.step_${step}`)}</p>
                    </div>
                    <button class="run-close" @click=${() => this._session.sessionCleared(null)}
                        aria-label=${this.t('run.exit')}>
                        <platform-icon name="x" size="22"></platform-icon>
                    </button>
                </div>
                ${this._renderExpected(session)}
                <div class="step-banner ${review ? 'review' : ''} ${errored ? 'error' : ''}">
                    <div class="step-icon">
                        <platform-icon name=${review ? 'check' : 'scan'} size="34"></platform-icon>
                    </div>
                    <p class="step-title">${this.t(`run.banner_${step}`)}</p>
                    ${session.hint !== '' ? html`<p class="step-hint">${session.hint}</p>` : ''}
                </div>
                ${this._renderSlots(context)}
                ${this._renderQuantity(session)}
                ${this._renderReview(session)}
            </div>
        `;
    }
}

customElements.define('stock-tsd-run', StockTsdRun);
