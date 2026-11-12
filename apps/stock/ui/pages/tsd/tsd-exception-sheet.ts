/**
 * Лист «проблема по строке задания» (`stock/tsd_exception` bottom sheet).
 *
 * Оператор физически не может выполнить строку: товара нет на полке,
 * он битый или не тот. Лист спрашивает причину и недостачу — backend
 * (`move_lines/report_exception`) укорачивает строку, отпускает резерв
 * недостачи и ставит задание пересчёта ячейки. После репорта сессия
 * исполнения закрывается — следующую работу даст очередь.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { createRef, ref } from 'lit/directives/ref.js';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import { buildFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import {
    tsdOffline,
    tsdOutboxItem,
} from '../../events/resources/stock-tsd.resource.js';
import type { StockTsdContextState } from '../../events/resources/stock-tsd.resource.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';

const REASONS = ['not_on_shelf', 'damaged', 'wrong_item', 'other'] as const;
const MAX_PHOTOS = 8;

interface PhotoEntry {
    file: File;
    preview: string;
    file_id: string;
    uploading: boolean;
    failed: boolean;
}

export class StockTsdExceptionSheet extends PlatformBottomSheet {
    static i18nNamespace = 'stock_tsd';
    static bottomSheetKind = 'stock.tsd_exception';

    static override properties: PropertyDeclarations = {
        ...PlatformBottomSheet.properties,
        move_line_id: { type: String },
        max_qty: { type: String },
        _reason: { state: true },
        _qty: { state: true },
        _photos: { state: true },
    };

    declare move_line_id: string;
    declare max_qty: string;
    declare private _reason: string;
    declare private _qty: string;
    declare private _photos: PhotoEntry[];

    private _contextSel: SelectController<StockTsdContextState>;
    private _exception: ControllerFor<'stock/move_lines_exception'>;
    private _fileCreate: ControllerFor<'platform/file_create'>;
    private _session: ControllerFor<'stock/tsd_session'>;
    private _outbox: ControllerFor<'stock/tsd_outbox'>;
    private readonly _photoInput = createRef<HTMLInputElement>();

    static override styles = [
        PlatformBottomSheet.styles,
        css`
            /* Глухая панель терминала — см. entity-sheet. */
            .panel { background: var(--bg-surface); }
            .exc {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding-bottom: var(--space-2);
            }
            .exc-title {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-size: var(--text-xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }
            .exc-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 52px;
                height: 52px;
                border-radius: var(--radius-xl);
                background: var(--tsd-error-subtle);
                color: var(--tsd-error);
                flex-shrink: 0;
            }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .reasons {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            .reason {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: var(--tsd-touch-lg);
                padding: var(--space-3);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-2xl);
                background: var(--bg-surface);
                color: var(--text-primary);
                font-size: var(--tsd-text-body);
                font-weight: var(--font-medium);
                cursor: pointer;
                text-align: center;
            }
            .reason.selected {
                border-color: var(--tsd-error);
                background: var(--tsd-error-subtle);
                color: var(--tsd-error);
                font-weight: var(--font-semibold);
            }
            .qty-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .qty-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: var(--tsd-touch-xl);
                height: var(--tsd-touch-xl);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                color: var(--text-primary);
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                cursor: pointer;
            }
            .qty-display {
                flex: 1;
                text-align: center;
                font-size: 48px;
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .qty-max {
                text-align: center;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .photo-input { display: none; }
            .photos {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
            }
            .photo-add {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                width: 84px;
                height: 84px;
                border: 1.5px dashed var(--border-strong, var(--border-default));
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                cursor: pointer;
            }
            .photo-thumb {
                position: relative;
                width: 84px;
                height: 84px;
                border-radius: var(--radius-xl);
                overflow: hidden;
                border: 1px solid var(--border-default);
                background: var(--bg-subtle, var(--bg-surface));
            }
            .photo-thumb img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .photo-thumb.busy img,
            .photo-thumb.failed img { opacity: 0.35; }
            .photo-state {
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--tsd-error);
            }
            .photo-remove {
                position: absolute;
                top: 2px;
                right: 2px;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: none;
                border-radius: 50%;
                background: rgba(0, 0, 0, 0.55);
                color: #fff;
                cursor: pointer;
            }
            .submit {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                min-height: var(--tsd-touch-xl);
                border: none;
                border-radius: var(--radius-2xl);
                background: var(--tsd-error);
                color: var(--text-inverse);
                font-size: var(--tsd-text-title);
                font-weight: var(--font-bold);
                cursor: pointer;
            }
            .submit:disabled { opacity: 0.6; }
        `,
    ];

    constructor() {
        super();
        this._contextSel = this.select((s) => s.stockTsdContext as StockTsdContextState);
        this._exception = this.useOp('stock/move_lines_exception');
        this._fileCreate = this.useOp('platform/file_create');
        this._session = this.useSlice('stock/tsd_session');
        this._outbox = this.useSlice('stock/tsd_outbox');
        this._reason = REASONS[0];
        this._qty = '1';
        this._photos = [];
    }

    private _max(): number {
        const max = Number(this.max_qty);
        return Number.isFinite(max) && max > 0 ? max : 999999;
    }

    private _bump(delta: number): void {
        const next = Math.min(this._max(), Math.max(1, (Number(this._qty) || 0) + delta));
        this._qty = String(next);
    }

    private _photoSpec(): string {
        return buildFileCreateSpecJson({
            sourceKind: 'stock_entity',
            sourceRef: { entity_id: this.move_line_id, entity_type: 'move_line' },
        });
    }

    private _onPhotoPicked(event: Event): void {
        const input = event.target as HTMLInputElement;
        const files = Array.from(input.files ?? []);
        input.value = '';
        for (const file of files.slice(0, MAX_PHOTOS - this._photos.length)) {
            void this._uploadPhoto(file);
        }
    }

    private async _uploadPhoto(file: File): Promise<void> {
        const entry: PhotoEntry = {
            file,
            preview: URL.createObjectURL(file),
            file_id: '',
            uploading: true,
            failed: false,
        };
        this._photos = [...this._photos, entry];
        try {
            const uploaded = await this._fileCreate.run({ file, spec: this._photoSpec() });
            const fileId = uploaded !== null && typeof uploaded.file_id === 'string'
                ? uploaded.file_id
                : '';
            if (fileId === '') throw new Error('platform/file_create: file_id missing');
            this._photos = this._photos.map((item) =>
                item === entry ? { ...item, file_id: fileId, uploading: false } : item,
            );
        } catch {
            this._photos = this._photos.map((item) =>
                item === entry ? { ...item, uploading: false, failed: true } : item,
            );
        }
    }

    private _removePhoto(entry: PhotoEntry): void {
        URL.revokeObjectURL(entry.preview);
        this._photos = this._photos.filter((item) => item !== entry);
    }

    private _retryPhoto(entry: PhotoEntry): void {
        this._photos = this._photos.filter((item) => item !== entry);
        URL.revokeObjectURL(entry.preview);
        void this._uploadPhoto(entry.file);
    }

    private async _submit(): Promise<void> {
        if (this._photos.some((photo) => photo.uploading)) return;
        const warehouseId = this._contextSel.value.warehouse_id;
        const fileIds = this._photos
            .map((photo) => photo.file_id)
            .filter((fileId) => fileId !== '');
        if (tsdOffline()) {
            // Мёртвая зона: репорт встаёт в outbox — недостача, резерв
            // и задание пересчёта применятся при возврате связи.
            this._outbox.enqueued(tsdOutboxItem('stock/move_lines_exception', {
                warehouse_id: warehouseId,
                move_line_id: this.move_line_id,
                shortage: this._qty,
                reason: this._reason,
                file_ids: fileIds,
            }));
            for (const photo of this._photos) URL.revokeObjectURL(photo.preview);
            this._session.sessionCleared(null);
            this.toast('exc.queued', { type: 'info' });
            this._requestClose();
            return;
        }
        const result = await this._exception.run({
            warehouse_id: warehouseId,
            move_line_id: this.move_line_id,
            shortage: this._qty,
            reason: this._reason,
            file_ids: fileIds,
            idempotency_key: null,
        });
        if (result === null) return;
        for (const photo of this._photos) URL.revokeObjectURL(photo.preview);
        this._session.sessionCleared(null);
        this.toast('exc.reported', { type: 'success' });
        this._requestClose();
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="exc">
                <div class="exc-title">
                    <span class="exc-icon"><platform-icon name="alert-triangle" size="26"></platform-icon></span>
                    ${this.t('exc.title')}
                </div>
                <div class="section-title">${this.t('exc.reason_title')}</div>
                <div class="reasons">
                    ${REASONS.map((reason) => html`
                        <button
                            class="reason ${this._reason === reason ? 'selected' : ''}"
                            @click=${() => { this._reason = reason; }}
                        >${this.t(`exc.reason_${reason}`)}</button>
                    `)}
                </div>
                <div class="section-title">${this.t('exc.qty_title')}</div>
                <div class="qty-row">
                    <button class="qty-btn" @click=${() => this._bump(-1)} aria-label="−">−</button>
                    <div class="qty-display">${this._qty}</div>
                    <button class="qty-btn" @click=${() => this._bump(1)} aria-label="+">+</button>
                </div>
                <div class="qty-max">${this.t('exc.qty_max', { qty: String(this._max()) })}</div>
                <div class="section-title">${this.t('exc.photos_title')}</div>
                <div class="photos">
                    ${this._photos.map(
                        (photo) => html`
                            <div class="photo-thumb ${photo.uploading ? 'busy' : ''} ${photo.failed ? 'failed' : ''}">
                                <img src=${photo.preview} alt="" />
                                ${photo.uploading
                                    ? html`<span class="photo-state"><platform-spinner size="s"></platform-spinner></span>`
                                    : ''}
                                ${photo.failed
                                    ? html`<button class="photo-state" @click=${() => this._retryPhoto(photo)} aria-label="retry">
                                        <platform-icon name="refresh-cw" size="22"></platform-icon>
                                    </button>`
                                    : html`<button class="photo-remove" @click=${() => this._removePhoto(photo)} aria-label="remove">
                                        <platform-icon name="x" size="14"></platform-icon>
                                    </button>`}
                            </div>
                        `,
                    )}
                    ${this._photos.length < MAX_PHOTOS
                        ? html`
                            <button class="photo-add" @click=${() => this._photoInput.value?.click()}>
                                <platform-icon name="camera" size="24"></platform-icon>
                                ${this.t('exc.photo_add')}
                            </button>
                        `
                        : ''}
                </div>
                <input
                    ${ref(this._photoInput)}
                    class="photo-input"
                    type="file"
                    accept="image/*"
                    capture="environment"
                    multiple
                    @change=${(event: Event) => this._onPhotoPicked(event)}
                />
                <button class="submit" ?disabled=${this._exception.busy || this._photos.some((p) => p.uploading)} @click=${() => void this._submit()}>
                    ${this._exception.busy
                        ? html`<platform-spinner size="s"></platform-spinner>`
                        : html`<platform-icon name="alert-triangle" size="24"></platform-icon>`}
                    ${this.t('exc.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('stock-tsd-exception-sheet', StockTsdExceptionSheet);
registerBottomSheetKind(StockTsdExceptionSheet.bottomSheetKind, 'stock-tsd-exception-sheet');
