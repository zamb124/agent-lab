/**
 * Рабочий стол ТСД: контекст склада оператора.
 *
 * Экран подчинён `stock/tsd_context`: без склада — выбор из справочника
 * (одна карта = один склад, тач-цель в полширины ладони); со складом —
 * рабочая зона, из которой следующие слои запускают очередь и скан-сессии.
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { formatPlatformError } from '@platform/lib/utils/platform-error-message.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { NetworkState } from '@platform/lib/events/reducers/network.js';
import type { ScanResolution, StockMoveLine, StockWarehouse } from '@platform/lib/events/wire/stock.gen.js';
import type {
    StockTsdContextState,
    StockTsdOutboxState,
    StockTsdSessionState,
    TsdOutboxItem,
} from '../../events/resources/stock-tsd.resource.js';
import { TsdScanInput } from './scan/scan-input.js';
import { tsdFormatQty, tsdVirtualLocationKey } from './tsd-format.js';
import { tsdScanFeedback } from './scan/scan-feedback.js';
import { tsdCameraScanSupported } from './scan/scan-camera.js';
import './scan/scan-camera.js';
import './stock-tsd-run.js';
import './tsd-entity-sheet.js';
import './tsd-exception-sheet.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';

const OUTBOX_OP_LABEL: Record<string, string> = {
    'stock/scan_commit': 'commit',
    'stock/scan_count_commit': 'count_commit',
    'stock/scan_adhoc_commit': 'adhoc_commit',
    'stock/move_lines_exception': 'exception',
    'stock/container_move': 'container_move',
};

export class StockTsdHomePage extends PlatformPage {
    static i18nNamespace = 'stock_tsd';

    private _warehouses: ControllerFor<'stock/warehouses'>;
    private _context: ControllerFor<'stock/tsd_context'>;
    private _contextSel: SelectController<StockTsdContextState>;
    private _scanStep: ControllerFor<'stock/scan_step'>;
    private _scanOpen: ControllerFor<'stock/scan_open'>;
    private _resourceLogin: ControllerFor<'stock/resource_login'>;
    private _queue: ControllerFor<'stock/queue'>;
    private _next: ControllerFor<'stock/move_lines_next'>;
    private _release: ControllerFor<'stock/move_lines_release'>;
    private _countDue: ControllerFor<'stock/locations_count_due'>;
    private _waves: ControllerFor<'stock/waves'>;
    private _products: ControllerFor<'stock/products'>;
    private _locations: ControllerFor<'stock/locations'>;
    private _session: ControllerFor<'stock/tsd_session'>;
    private _sessionSel: SelectController<StockTsdSessionState>;
    private _authSel: SelectController<AuthUser | null>;
    private _outbox: ControllerFor<'stock/tsd_outbox'>;
    private _outboxSel: SelectController<StockTsdOutboxState>;
    private _networkSel: SelectController<NetworkState>;
    private _scanCommit: ControllerFor<'stock/scan_commit'>;
    private _scanCountCommit: ControllerFor<'stock/scan_count_commit'>;
    private _scanAdhocCommit: ControllerFor<'stock/scan_adhoc_commit'>;
    private _moveLinesException: ControllerFor<'stock/move_lines_exception'>;
    private _containerMove: ControllerFor<'stock/container_move'>;
    private _pulse: ControllerFor<'stock/operator_pulse'>;
    private _scanInput: TsdScanInput | null = null;
    private _flash: '' | 'ok' | 'error' = '';
    private _flashTimer: ReturnType<typeof setTimeout> | null = null;
    private _cameraOpen = false;
    private _pending: '' | 'zone' | 'resource' | 'wave' = '';
    private _loadedFor = '';
    private _hadSession = false;
    private _draining = false;
    private _drainCooldownUntil = 0;
    private _outboxOpen = false;
    private readonly _cameraSupported = tsdCameraScanSupported();

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                padding: var(--space-5);
                padding-top: max(var(--space-5), var(--platform-safe-top));
                padding-bottom: calc(var(--app-content-bottom-padding-mobile, 96px) + var(--space-4));
                min-height: 100%;
                box-sizing: border-box;
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .head-icon {
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
            h1 {
                margin: 0;
                font-size: var(--text-2xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                line-height: var(--leading-tight);
            }
            .sub {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .warehouse-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .warehouse-card {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                min-height: var(--tsd-touch-lg);
                padding: var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
                cursor: pointer;
                text-align: left;
                font: inherit;
                color: inherit;
                -webkit-tap-highlight-color: transparent;
            }
            .warehouse-card:active {
                background: var(--bg-secondary);
            }
            .warehouse-card.selected {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .warehouse-card-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border-radius: var(--radius-lg);
                background: var(--bg-secondary);
                color: var(--text-secondary);
                flex-shrink: 0;
            }
            .warehouse-card.selected .warehouse-card-icon {
                background: var(--accent);
                color: var(--text-inverse);
            }
            .warehouse-card-body {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
                flex: 1;
            }
            .warehouse-card-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .warehouse-card-code {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            .warehouse-card-check {
                color: var(--accent);
                flex-shrink: 0;
            }
            .context-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 44px;
                padding: 0 var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-full);
                background: var(--bg-surface);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }
            .chip.filled {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .chip.armed {
                border-color: var(--tsd-info);
                background: var(--tsd-info-subtle);
                color: var(--tsd-info);
            }
            .pending-banner {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 2px solid var(--tsd-info);
                border-radius: var(--radius-2xl);
                background: var(--tsd-info-subtle);
            }
            .pending-banner-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background: var(--tsd-info);
                color: var(--text-inverse);
                flex-shrink: 0;
                animation: tsd-pulse 1.2s ease-in-out infinite;
            }
            @keyframes tsd-pulse {
                0%, 100% { transform: scale(1); opacity: 1; }
                50% { transform: scale(1.08); opacity: 0.85; }
            }
            .pending-banner-text {
                flex: 1;
                font-size: var(--tsd-text-body);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .wave-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .wave-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: var(--tsd-touch-md);
                padding: var(--space-3) var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                color: var(--text-primary);
                font-size: var(--tsd-text-body);
                font-weight: var(--font-medium);
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }
            .wave-item.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .wave-name { flex: 1; text-align: start; }
            .wave-empty {
                padding: var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                text-align: center;
            }
            .outbox-banner {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: var(--tsd-touch-md);
                padding: var(--space-3) var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }
            .outbox-banner.offline {
                border-color: var(--tsd-warning, #b45309);
                background: var(--tsd-warning-subtle, rgba(245, 158, 11, 0.12));
                color: var(--tsd-warning, #b45309);
            }
            .outbox-banner.syncing {
                border-color: var(--tsd-info);
                background: var(--tsd-info-subtle);
                color: var(--tsd-info);
            }
            .outbox-text { flex: 1; text-align: start; }
            .outbox-count {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 26px;
                height: 26px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-full);
                background: currentColor;
                color: var(--bg-surface);
                font-size: var(--text-xs);
                font-weight: var(--font-bold);
            }
            .outbox-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .outbox-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
            }
            .outbox-item-body {
                display: flex;
                flex-direction: column;
                gap: 2px;
                flex: 1;
                min-width: 0;
            }
            .outbox-item-op {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .outbox-item-time {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .outbox-drop {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border: 1px solid var(--border-default);
                border-radius: 50%;
                background: var(--bg-surface);
                color: var(--text-tertiary);
                cursor: pointer;
            }
            .outbox-drop:active { background: var(--tsd-error-subtle); color: var(--tsd-error); }
            .pulse {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: var(--space-3);
            }
            .pulse-stat {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2px;
                padding: var(--space-3);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
            }
            .pulse-value {
                font-size: var(--text-2xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .pulse-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                text-align: center;
            }
            .pending-cancel {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border: none;
                border-radius: 50%;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .give-work {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                min-height: var(--tsd-touch-xl);
                border: none;
                border-radius: var(--radius-2xl);
                background: linear-gradient(135deg, var(--accent), var(--accent-strong, var(--accent)));
                color: var(--text-inverse);
                font-size: var(--tsd-text-title);
                font-weight: var(--font-bold);
                letter-spacing: 0.01em;
                cursor: pointer;
                box-shadow: 0 8px 24px var(--accent-glow, rgba(79, 124, 255, 0.35));
                -webkit-tap-highlight-color: transparent;
            }
            .give-work:active { transform: scale(0.985); }
            .give-work:disabled { opacity: 0.6; }
            .task-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .task-card {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                min-height: var(--tsd-touch-lg);
                padding: var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
            }
            .task-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 48px;
                height: 48px;
                border-radius: var(--radius-xl);
                background: var(--accent-subtle);
                color: var(--accent);
                flex-shrink: 0;
            }
            .task-body {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
                flex: 1;
            }
            .task-name {
                font-size: var(--tsd-text-body);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .task-route {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .task-wave {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--tsd-info);
            }
            .task-side {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: var(--space-2);
                flex-shrink: 0;
            }
            .task-qty {
                font-size: var(--text-lg);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .task-release {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border: 1px solid var(--border-default);
                border-radius: 50%;
                background: var(--bg-surface);
                color: var(--text-tertiary);
                cursor: pointer;
            }
            .task-release:active { background: var(--tsd-error-subtle); color: var(--tsd-error); }
            .count-due {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .count-due-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .count-due-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .ready {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-4);
                padding: var(--space-8) var(--space-4);
                border: 1px dashed var(--border-strong);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
                text-align: center;
            }
            .ready-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 72px;
                height: 72px;
                border-radius: 50%;
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .ready-title {
                margin: 0;
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .ready-hint {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .center {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 40vh;
            }
            .scan-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-5);
                border-radius: var(--radius-2xl);
                border: 2px solid var(--border-default);
                background: var(--bg-surface);
            }
            .scan-card.ok { border-color: var(--tsd-ok); background: var(--tsd-ok-subtle); }
            .scan-card.error { border-color: var(--tsd-error); background: var(--tsd-error-subtle); }
            .scan-kind {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-secondary);
            }
            .scan-barcode {
                font-size: var(--tsd-text-title);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                word-break: break-all;
            }
            .scan-hint {
                font-size: var(--tsd-text-body);
                color: var(--text-secondary);
            }
            .manual {
                display: flex;
                gap: var(--space-3);
            }
            .manual-input {
                flex: 1;
                min-height: var(--tsd-touch-min);
                padding: 0 var(--space-4);
                font-size: var(--tsd-text-body);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                color: var(--text-primary);
            }
            .manual-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: var(--tsd-touch-min);
                min-height: var(--tsd-touch-min);
                border: none;
                border-radius: var(--radius-xl);
                background: var(--accent);
                color: var(--text-inverse);
                cursor: pointer;
            }
            .manual-btn:disabled { opacity: 0.5; }
            .flash {
                position: fixed;
                inset: 0;
                pointer-events: none;
                z-index: 999;
                animation: tsd-flash 0.45s ease-out forwards;
            }
            .flash.ok { background: var(--tsd-ok); }
            .flash.error { background: var(--tsd-error); }
            @keyframes tsd-flash {
                from { opacity: 0.35; }
                to { opacity: 0; }
            }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._context = this.useSlice('stock/tsd_context');
        this._contextSel = this.select((s) => s.stockTsdContext as StockTsdContextState);
        this._scanStep = this.useOp('stock/scan_step');
        this._scanOpen = this.useOp('stock/scan_open');
        this._resourceLogin = this.useOp('stock/resource_login');
        this._queue = this.useResource('stock/queue');
        this._next = this.useOp('stock/move_lines_next');
        this._release = this.useOp('stock/move_lines_release');
        this._countDue = this.useOp('stock/locations_count_due');
        this._waves = this.useResource('stock/waves');
        this._products = this.useResource('stock/products');
        this._locations = this.useResource('stock/locations');
        this._session = this.useSlice('stock/tsd_session');
        this._sessionSel = this.select((s) => s.stockTsdSession as StockTsdSessionState);
        this._authSel = this.select((s) => s.auth.user);
        this._outbox = this.useSlice('stock/tsd_outbox');
        this._outboxSel = this.select((s) => s.stockTsdOutbox as StockTsdOutboxState);
        this._networkSel = this.select((s) => s.network as NetworkState);
        this._scanCommit = this.useOp('stock/scan_commit');
        this._scanCountCommit = this.useOp('stock/scan_count_commit');
        this._scanAdhocCommit = this.useOp('stock/scan_adhoc_commit');
        this._moveLinesException = this.useOp('stock/move_lines_exception');
        this._containerMove = this.useOp('stock/container_move');
        this._pulse = this.useOp('stock/operator_pulse');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._scanInput = new TsdScanInput((code) => this._onScan(code));
        this._scanInput.attach();
    }

    override disconnectedCallback(): void {
        this._scanInput?.detach();
        this._scanInput = null;
        if (this._flashTimer !== null) clearTimeout(this._flashTimer);
        super.disconnectedCallback();
    }

    override updated(): void {
        const context = this._contextSel.value;
        if (context.warehouse_id !== '' && context.warehouse_id !== this._loadedFor) {
            this._loadedFor = context.warehouse_id;
            this._reloadWork();
        }
        if (context.warehouse_id === '' && this._loadedFor !== '') {
            this._loadedFor = '';
        }
        // Сессия закрылась (коммит, исключение, выход) — задание ушло
        // в леджер: очередь и показатели оператора обновляем сразу.
        const running = this._sessionSel.value.context !== null;
        if (this._hadSession && !running) {
            this._hadSession = false;
            this._refreshQueue();
        } else if (running) {
            this._hadSession = true;
        }
        if (this._deliverable() && this._outboxSel.value.items.length > 0 && !this._draining
            && Date.now() >= this._drainCooldownUntil) {
            void this._drainOutbox();
        }
    }

    /** Очередь + пульс оператора — единая точка обновления после изменения работы. */
    private _refreshQueue(): void {
        this._queue.load(this._queueQuery());
        const warehouseId = this._contextSel.value.warehouse_id;
        if (warehouseId !== '') {
            void this._pulse.run({ warehouse_id: warehouseId, window_hours: 8 });
        }
    }

    /** Доставляемо: браузер онлайн и командный WS-транспорт открыт. */
    private _deliverable(): boolean {
        const net = this._networkSel.value;
        return net.online && net.ws.status === 'open';
    }

    private _outboxTargets(): Record<string, { run(p?: unknown): Promise<unknown> }> {
        return {
            'stock/scan_commit': this._scanCommit,
            'stock/scan_count_commit': this._scanCountCommit,
            'stock/scan_adhoc_commit': this._scanAdhocCommit,
            'stock/move_lines_exception': this._moveLinesException,
            'stock/container_move': this._containerMove,
        };
    }

    /** Дрейн outbox FIFO: успех снимает элемент, отказ останавливает
     *  очередь — конфликт мог каскадить на следующие команды. */
    private async _drainOutbox(): Promise<void> {
        if (this._draining) return;
        this._draining = true;
        try {
            for (;;) {
                const item = this._outboxSel.value.items[0];
                if (item === undefined || !this._deliverable()) break;
                const target = this._outboxTargets()[item.op];
                if (target === undefined) {
                    this._outbox.dropped(item.outbox_id);
                    continue;
                }
                const result = await target.run(item.payload);
                if (result !== null) {
                    this._outbox.delivered(item.outbox_id);
                    this._refreshQueue();
                    continue;
                }
                this._outbox.attemptFailed({ outbox_id: item.outbox_id, error: 'delivery_failed' });
                this._drainCooldownUntil = Date.now() + 30_000;
                break;
            }
        } finally {
            this._draining = false;
        }
    }

    private _outboxWhen(item: TsdOutboxItem): string {
        const at = new Date(item.enqueued_at);
        return Number.isNaN(at.getTime())
            ? item.enqueued_at
            : at.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }

    private _queueQuery(): Record<string, unknown> {
        const context = this._contextSel.value;
        const user = this._authSel.value;
        return {
            warehouse_id: context.warehouse_id,
            assigned_user_id: user === null ? undefined : user.user_id,
            zone_location_id: context.zone_location_id === '' ? undefined : context.zone_location_id,
            wave_id: context.wave_id === '' ? undefined : context.wave_id,
            limit: 50,
        };
    }

    private _reloadWork(): void {
        const context = this._contextSel.value;
        this._queue.load(this._queueQuery());
        this._products.load({ limit: 500 });
        this._locations.load({ warehouse_id: context.warehouse_id, include_virtual: true });
        this._waves.load({ warehouse_id: context.warehouse_id, state: 'released' });
        void this._countDue.run({ warehouse_id: context.warehouse_id, limit: 20 });
        void this._pulse.run({ warehouse_id: context.warehouse_id, window_hours: 8 });
    }

    private _startCount(locationId: string): void {
        this._session.stepApplied({
            context: { flow: 'count', step: 'product', source_id: locationId },
            resolution: null,
            barcode: '',
            error: null,
            hint: '',
            expected: null,
        });
    }

    private async _giveWork(): Promise<void> {
        const context = this._contextSel.value;
        try {
            const response = await this._next.run({
                warehouse_id: context.warehouse_id,
                resource_id: context.resource_id === '' ? undefined : context.resource_id,
                zone_location_id: context.zone_location_id === '' ? undefined : context.zone_location_id,
                wave_id: context.wave_id === '' ? undefined : context.wave_id,
                claim: true,
            });
            if (response === null) {
                throw new Error('stock/move_lines_next: empty response');
            }
            if (response.line === null || response.line === undefined) {
                this.toast('home.no_work', { type: 'info' });
                return;
            }
            this._refreshQueue();
            this._applyOutcome('ok', '', '');
            await this._openLine(response.line);
        } catch {
            this.toast('home.give_work_failed', { type: 'error' });
        }
    }

    private async _openLine(line: StockMoveLine): Promise<void> {
        const context = this._contextSel.value;
        try {
            const opened = await this._scanOpen.run({
                warehouse_id: context.warehouse_id,
                move_id: line.move_id,
                transfer_id: null,
                move_line_id: line.move_line_id,
            });
            if (opened === null) {
                throw new Error('stock/scan_open: empty response');
            }
            this._session.runOpened({
                context: opened.context,
                move_id: opened.move_id,
                expected: opened.expected ?? null,
            });
        } catch {
            this.toast('home.open_failed', { type: 'error' });
        }
    }

    private async _releaseLine(line: StockMoveLine): Promise<void> {
        const context = this._contextSel.value;
        try {
            await this._release.run({
                warehouse_id: context.warehouse_id,
                move_line_ids: [line.move_line_id],
                idempotency_key: null,
            });
            this._refreshQueue();
        } catch {
            this.toast('home.release_failed', { type: 'error' });
        }
    }

    private _lineName(line: StockMoveLine): string {
        const product = this._products.items.find((row) => row.product_id === line.product_id);
        return product === undefined ? line.product_id : product.name;
    }

    private _locationName(locationId: string): string {
        const location = this._locations.items.find((row) => row.location_id === locationId);
        if (location === undefined) return locationId;
        const virtual = tsdVirtualLocationKey(location.usage, location.partner_role);
        return virtual !== null ? this.t(virtual) : (location.complete_name ?? location.name);
    }

    private _waveName(waveId: string): string {
        const wave = this._waves.items.find((row) => row.wave_id === waveId);
        return wave === undefined ? waveId : wave.name;
    }

    // Сканы сериализуются: hardware-сканер шлёт коды подряд быстрее
    // ответа scan_step — без очереди второй скан уходил бы со старым
    // контекстом и применялся к чужому шагу.
    private _scanQueue: string[] = [];
    private _scanBusy = false;

    private _onScan(code: string): void {
        this._scanQueue.push(code);
        void this._drainScans();
    }

    private async _drainScans(): Promise<void> {
        if (this._scanBusy) return;
        this._scanBusy = true;
        try {
            let code = this._scanQueue.shift();
            while (code !== undefined) {
                await this._handleScan(code);
                code = this._scanQueue.shift();
            }
        } finally {
            this._scanBusy = false;
        }
    }

    private async _handleScan(code: string): Promise<void> {
        const warehouseId = this._contextSel.value.warehouse_id;
        if (warehouseId === '') {
            this._applyOutcome('error', code, '');
            return;
        }
        const session = this._sessionSel.value;
        // Открытая сессия владеет сканами — «взведённый» чип зоны,
        // ресурса или волны гасим, иначе первый шаг потока ушёл бы
        // на биндинг контекста, а не на работу.
        if (session.context !== null) {
            this._pending = '';
        }
        if (this._pending === 'resource') {
            this._pending = '';
            await this._bindResource(code, warehouseId);
            return;
        }
        const context = session.context ?? { flow: 'inquiry' };
        try {
            const response = await this._scanStep.run({
                warehouse_id: warehouseId,
                context,
                barcode: code,
                move_id: session.move_id === '' ? null : session.move_id,
            });
            if (response === null) {
                throw new Error('stock/scan_step: empty response');
            }
            if (this._pending === 'zone') {
                this._pending = '';
                const resolution = response.resolution;
                if (resolution !== null && resolution !== undefined && resolution.entity_kind === 'location' && resolution.entity_id !== null && resolution.entity_id !== undefined) {
                    this._context.setZone({ zone_location_id: resolution.entity_id, zone_code: code });
                    this._applyOutcome('ok', code, '');
                } else {
                    this._applyOutcome('error', code, this.t('home.zone_not_location'));
                }
                return;
            }
            this._session.stepApplied({
                context: response.context,
                resolution: response.resolution ?? null,
                barcode: code,
                error: response.error ?? null,
                hint: response.hint ?? '',
                expected: response.expected ?? null,
            });
            this._applyOutcome(response.error !== null && response.error !== undefined ? 'error' : 'ok', code, response.hint ?? '');
            const resolution = response.resolution;
            if (session.context === null && resolution !== null && resolution !== undefined) {
                this._openEntity(code, resolution);
            }
        } catch {
            this._pending = '';
            this._session.scanRejected({ barcode: code, hint: this.t('home.scan_failed') });
            this._applyOutcome('error', code, '');
        }
    }

    private _openEntity(code: string, resolution: ScanResolution): void {
        const entityId = resolution.entity_id;
        if (entityId === null || entityId === undefined || entityId === '') {
            return;
        }
        this.openBottomSheet('stock.tsd_entity', {
            barcode: code,
            entity_kind: resolution.entity_kind,
            entity_id: entityId,
            product_id: resolution.product_id ?? '',
            serial: resolution.serial ?? '',
            quantity: resolution.quantity ?? null,
            warehouse_id: this._contextSel.value.warehouse_id,
        });
    }

    private async _bindResource(code: string, warehouseId: string): Promise<void> {
        try {
            const resource = await this._resourceLogin.run({
                warehouse_id: warehouseId,
                barcode: code,
                resource_id: null,
                idempotency_key: null,
            });
            if (resource === null) {
                throw new Error('stock/resource_login: empty response');
            }
            this._context.setResource({ resource_id: resource.resource_id, resource_code: resource.code });
            this._applyOutcome('ok', code, '');
        } catch {
            this._session.scanRejected({ barcode: code, hint: this.t('home.resource_bind_failed') });
            this._applyOutcome('error', code, '');
        }
    }

    private _applyOutcome(outcome: 'ok' | 'error', _code: string, _hint: string): void {
        this._flash = outcome;
        tsdScanFeedback(outcome);
        if (this._flashTimer !== null) clearTimeout(this._flashTimer);
        this._flashTimer = setTimeout(() => {
            this._flash = '';
            this.requestUpdate();
        }, 450);
        this.requestUpdate();
    }

    private _selectWarehouse(warehouse: StockWarehouse): void {
        this._context.setWarehouse({
            warehouse_id: warehouse.warehouse_id,
            warehouse_name: warehouse.name,
        });
    }

    private _renderPicker(): TemplateResult {
        const warehouses = this._warehouses.items;
        if (this._warehouses.loading && warehouses.length === 0) {
            return html`<div class="center"><platform-spinner size="l"></platform-spinner></div>`;
        }
        if (warehouses.length === 0) {
            return html`<platform-empty-state
                icon="building"
                .title=${this.t('home.no_warehouses')}
                .hint=${this.t('home.no_warehouses_hint')}
            ></platform-empty-state>`;
        }
        const selectedId = this._contextSel.value.warehouse_id;
        return html`
            <div class="head">
                <div class="head-icon"><platform-icon name="building" size="26"></platform-icon></div>
                <div>
                    <h1>${this.t('home.pick_warehouse')}</h1>
                    <p class="sub">${this.t('home.pick_warehouse_hint')}</p>
                </div>
            </div>
            <div class="warehouse-list" role="listbox">
                ${warehouses.map((warehouse) => {
                    const selected = warehouse.warehouse_id === selectedId;
                    return html`
                        <button
                            class="warehouse-card ${selected ? 'selected' : ''}"
                            role="option"
                            aria-selected=${selected}
                            @click=${() => this._selectWarehouse(warehouse)}
                        >
                            <span class="warehouse-card-icon"><platform-icon name="building" size="22"></platform-icon></span>
                            <span class="warehouse-card-body">
                                <span class="warehouse-card-name">${warehouse.name}</span>
                                <span class="warehouse-card-code">${warehouse.code}</span>
                            </span>
                            ${selected
                                ? html`<span class="warehouse-card-check"><platform-icon name="check" size="24"></platform-icon></span>`
                                : ''}
                        </button>
                    `;
                })}
            </div>
        `;
    }

    private _renderSession(): TemplateResult {
        const session = this._sessionSel.value;
        if (session.last_barcode === '') {
            return html`
                <div class="ready">
                    <div class="ready-icon"><platform-icon name="qr-code" size="36"></platform-icon></div>
                    <p class="ready-title">${this.t('home.ready_title')}</p>
                    <p class="ready-hint">${this.t('home.ready_hint')}</p>
                </div>
            `;
        }
        const kind = session.resolution?.entity_kind ?? 'unknown';
        const kindLabel = this.t(`home.kind_${kind}`);
        return html`
            <div class="scan-card ${session.outcome}">
                <div class="scan-kind">${kindLabel}</div>
                <div class="scan-barcode">${session.last_barcode}</div>
                ${session.error !== null && session.error !== undefined
                    ? html`<div class="scan-hint">${formatPlatformError(session.error)}</div>`
                    : session.hint !== '' ? html`<div class="scan-hint">${session.hint}</div>` : ''}
            </div>
        `;
    }

    private _renderContextChips(context: StockTsdContextState): TemplateResult {
        const zoneSet = context.zone_location_id !== '';
        const resourceSet = context.resource_id !== '';
        const waveSet = context.wave_id !== '';
        return html`
            <div class="context-chips">
                <button class="chip ${this._pending === 'zone' ? 'armed' : zoneSet ? 'filled' : ''}"
                    @click=${() => { this._pending = this._pending === 'zone' ? '' : 'zone'; }}>
                    <platform-icon name="map-pin" size="16"></platform-icon>
                    ${zoneSet ? context.zone_code : this.t('home.chip_zone')}
                </button>
                <button class="chip ${this._pending === 'resource' ? 'armed' : resourceSet ? 'filled' : ''}"
                    @click=${() => { this._pending = this._pending === 'resource' ? '' : 'resource'; }}>
                    <platform-icon name="truck" size="16"></platform-icon>
                    ${resourceSet ? context.resource_code : this.t('home.chip_resource')}
                </button>
                <button class="chip ${this._pending === 'wave' ? 'armed' : waveSet ? 'filled' : ''}"
                    @click=${() => { this._pending = this._pending === 'wave' ? '' : 'wave'; }}>
                    <platform-icon name="layers" size="16"></platform-icon>
                    ${waveSet ? context.wave_name : this.t('home.chip_wave')}
                </button>
            </div>
        `;
    }

    private _renderOutbox(): TemplateResult | string {
        const net = this._networkSel.value;
        const items = this._outboxSel.value.items;
        const offline = !net.online;
        if (!offline && items.length === 0) return '';
        const syncing = items.length > 0 && this._deliverable();
        return html`
            <button class="outbox-banner ${offline ? 'offline' : syncing ? 'syncing' : 'pending'}"
                @click=${() => { this._outboxOpen = !this._outboxOpen; }}>
                <platform-icon name=${offline ? 'wifi-off' : syncing ? 'refresh-cw' : 'cloud-upload'} size="20"></platform-icon>
                <span class="outbox-text">${this.t(offline ? 'outbox.offline' : syncing ? 'outbox.syncing' : 'outbox.pending')}</span>
                ${items.length > 0 ? html`<span class="outbox-count">${items.length}</span>` : ''}
            </button>
            ${this._outboxOpen && items.length > 0 ? html`
                <div class="outbox-list">
                    ${items.map((item) => html`
                        <div class="outbox-item">
                            <div class="outbox-item-body">
                                <span class="outbox-item-op">${this.t(`outbox.op_${OUTBOX_OP_LABEL[item.op] ?? 'op'}`)}</span>
                                <span class="outbox-item-time">${this._outboxWhen(item)}${item.attempts > 0 ? ` · ${this.t('outbox.retries', { count: String(item.attempts) })}` : ''}</span>
                            </div>
                            <button class="outbox-drop" @click=${(e: Event) => { e.stopPropagation(); this._outbox.dropped(item.outbox_id); }}
                                aria-label=${this.t('outbox.drop')}>
                                <platform-icon name="trash-2" size="16"></platform-icon>
                            </button>
                        </div>
                    `)}
                </div>
            ` : ''}
        `;
    }

    private _renderPulse(): TemplateResult | string {
        const pulse = this._pulse.lastResult;
        if (pulse === null || pulse === undefined || pulse.lines_done === 0) return '';
        return html`
            <div class="pulse">
                <div class="pulse-stat">
                    <span class="pulse-value">${pulse.lines_done}</span>
                    <span class="pulse-label">${this.t('pulse.lines')}</span>
                </div>
                <div class="pulse-stat">
                    <span class="pulse-value">${tsdFormatQty(pulse.units_done)}</span>
                    <span class="pulse-label">${this.t('pulse.units')}</span>
                </div>
                <div class="pulse-stat">
                    <span class="pulse-value">${tsdFormatQty(pulse.lines_per_hour)}</span>
                    <span class="pulse-label">${this.t('pulse.per_hour')}</span>
                </div>
            </div>
        `;
    }

    private _pickWave(waveId: string, waveName: string): void {
        this._context.setWave({ wave_id: waveId, wave_name: waveName });
        this._pending = '';
        this._refreshQueue();
    }

    private _renderWavePicker(): TemplateResult {
        const context = this._contextSel.value;
        const waves = this._waves.items;
        return html`
            <div class="pending-banner">
                <span class="pending-banner-icon"><platform-icon name="layers" size="22"></platform-icon></span>
                <span class="pending-banner-text">${this.t('home.pending_wave')}</span>
                <button class="pending-cancel" @click=${() => { this._pending = ''; }}>
                    <platform-icon name="x" size="20"></platform-icon>
                </button>
            </div>
            <div class="wave-list">
                ${context.wave_id !== ''
                    ? html`
                        <button class="wave-item" @click=${() => this._pickWave('', '')}>
                            <platform-icon name="inbox" size="20"></platform-icon>
                            <span class="wave-name">${this.t('home.wave_all')}</span>
                        </button>
                    `
                    : ''}
                ${waves.map(
                    (wave) => html`
                        <button class="wave-item ${wave.wave_id === context.wave_id ? 'active' : ''}"
                            @click=${() => this._pickWave(wave.wave_id, wave.name)}>
                            <platform-icon name="layers" size="20"></platform-icon>
                            <span class="wave-name">${wave.name}</span>
                            ${wave.wave_id === context.wave_id
                                ? html`<platform-icon name="check" size="18"></platform-icon>`
                                : ''}
                        </button>
                    `,
                )}
                ${waves.length === 0
                    ? html`<div class="wave-empty">${this.t('home.wave_empty')}</div>`
                    : ''}
            </div>
        `;
    }

    private _renderPending(): TemplateResult {
        if (this._pending === '') {
            return html``;
        }
        if (this._pending === 'wave') {
            return this._renderWavePicker();
        }
        const key = this._pending === 'zone' ? 'home.pending_zone' : 'home.pending_resource';
        const icon = this._pending === 'zone' ? 'map-pin' : 'truck';
        return html`
            <div class="pending-banner">
                <span class="pending-banner-icon"><platform-icon name=${icon} size="22"></platform-icon></span>
                <span class="pending-banner-text">${this.t(key)}</span>
                <button class="pending-cancel" @click=${() => { this._pending = ''; }}>
                    <platform-icon name="x" size="20"></platform-icon>
                </button>
            </div>
        `;
    }

    private _renderWork(): TemplateResult {
        const lines = this._queue.items;
        return html`
            <button class="give-work" ?disabled=${this._next.busy} @click=${() => void this._giveWork()}>
                ${this._next.busy
                    ? html`<platform-spinner size="m"></platform-spinner>`
                    : html`<platform-icon name="zap" size="30"></platform-icon>`}
                <span>${this.t('home.give_work')}</span>
            </button>
            ${lines.length === 0
                ? ''
                : html`
                    <div class="task-list">
                        ${lines.map((line) => this._renderLine(line))}
                    </div>
                `}
            ${this._renderCountDue()}
        `;
    }

    private _renderCountDue(): TemplateResult {
        const due = this._countDue.lastResult;
        const items = due === null || due === undefined ? [] : due.items;
        if (items.length === 0) return html``;
        return html`
            <div class="count-due">
                <div class="count-due-title">${this.t('home.count_due_title')}</div>
                <div class="count-due-list">
                    ${items.map((location) => html`
                        <button class="chip" @click=${() => this._startCount(location.location_id)}>
                            <platform-icon name="checklist" size="16"></platform-icon>
                            ${location.complete_name ?? location.name}
                        </button>
                    `)}
                </div>
            </div>
        `;
    }

    private _renderLine(line: StockMoveLine): TemplateResult {
        // У задания пересчёта «сколько взять» не существует — факт и
        // есть содержимое ячейки: 0/0 на карточке только путает.
        const qty = line.kind === 'count'
            ? ''
            : line.done_quantity !== undefined && line.done_quantity !== null
              ? `${tsdFormatQty(line.done_quantity)}/${tsdFormatQty(line.quantity ?? '')}`
              : `${tsdFormatQty(line.quantity ?? '')}`;
        return html`
            <div class="task-card" @click=${() => void this._openLine(line)}>
                <div class="task-icon"><platform-icon name=${line.kind === 'container' ? 'box' : line.kind === 'count' ? 'checklist' : 'package'} size="22"></platform-icon></div>
                <div class="task-body">
                    <div class="task-name">${this._lineName(line)}</div>
                    <div class="task-route">
                        <platform-icon name="map-pin" size="14"></platform-icon>
                        ${this._locationName(line.location_id)}
                        ${line.location_dest_id !== line.location_id
                            ? html`
                                <platform-icon name="arrow-right" size="14"></platform-icon>
                                ${this._locationName(line.location_dest_id)}
                            `
                            : ''}
                    </div>
                    ${line.wave_id !== null && line.wave_id !== undefined && line.wave_id !== ''
                        ? html`<div class="task-wave"><platform-icon name="layers" size="12"></platform-icon> ${this._waveName(line.wave_id)}</div>`
                        : ''}
                </div>
                <div class="task-side">
                    <div class="task-qty">${qty}</div>
                    <button class="task-release" ?disabled=${this._release.busy}
                        @click=${(e: Event) => { e.stopPropagation(); void this._releaseLine(line); }}
                        aria-label=${this.t('home.release')}
                    ><platform-icon name="x" size="18"></platform-icon></button>
                </div>
            </div>
        `;
    }

    private _renderReady(warehouseName: string, context: StockTsdContextState): TemplateResult {
        const session = this._sessionSel.value;
        const running = session.context !== null;
        return html`
            <div class="head">
                <div class="head-icon"><platform-icon name="building" size="26"></platform-icon></div>
                <div>
                    <h1>${warehouseName}</h1>
                    <p class="sub">${this.t('home.warehouse_active')}</p>
                </div>
            </div>
            ${this._renderContextChips(context)}
            ${this._renderOutbox()}
            ${this._renderPulse()}
            ${this._renderPending()}
            ${running ? html`<stock-tsd-run></stock-tsd-run>` : html`
                ${this._renderWork()}
                ${this._renderSession()}
            `}
            <div class="manual">
                <input
                    class="manual-input"
                    type="text"
                    inputmode="text"
                    data-canon="search-as-you-type"
                    autocomplete="off"
                    placeholder=${this.t('home.manual_placeholder')}
                    @keydown=${(e: KeyboardEvent) => {
                        if (e.key === 'Enter') {
                            this._scanInput?.submit((e.target as HTMLInputElement).value);
                            (e.target as HTMLInputElement).value = '';
                        }
                    }}
                >
                <button
                    class="manual-btn"
                    ?disabled=${this._scanStep.busy}
                    @click=${(e: Event) => {
                        const input = (e.currentTarget as HTMLElement).previousElementSibling as HTMLInputElement;
                        this._scanInput?.submit(input.value);
                        input.value = '';
                    }}
                ><platform-icon name="scan" size="22"></platform-icon></button>
                ${this._cameraSupported ? html`
                    <button class="manual-btn" @click=${() => { this._cameraOpen = true; this.requestUpdate(); }}>
                        <platform-icon name="qr-code" size="22"></platform-icon>
                    </button>
                ` : ''}
            </div>
            <stock-tsd-camera-scanner
                ?active=${this._cameraOpen}
                @tsd-scan=${(e: CustomEvent<{ code: string }>) => { this._cameraOpen = false; void this._onScan(e.detail.code); }}
                @tsd-scan-close=${() => { this._cameraOpen = false; }}
            ><span slot="error">${this.t('home.camera_error')}</span></stock-tsd-camera-scanner>
            ${this._scanStep.busy ? html`<div class="center"><platform-spinner size="m"></platform-spinner></div>` : ''}
            <button class="warehouse-card" @click=${() => { this._session.sessionCleared(null); this._context.resetContext(null); }}>
                <span class="warehouse-card-icon"><platform-icon name="swap" size="22"></platform-icon></span>
                <span class="warehouse-card-body">
                    <span class="warehouse-card-name">${this.t('home.change_warehouse')}</span>
                </span>
            </button>
        `;
    }

    override render(): TemplateResult {
        const context = this._contextSel.value;
        return html`
            <div class="wrap">
                ${context.warehouse_id === ''
                    ? this._renderPicker()
                    : this._renderReady(context.warehouse_name, context)}
            </div>
            ${this._flash !== '' ? html`<div class="flash ${this._flash}"></div>` : ''}
        `;
    }
}

customElements.define('stock-tsd-home-page', StockTsdHomePage);
