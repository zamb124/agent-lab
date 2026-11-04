/**
 * ShopMenuImportModal — импорт меню заведения.
 *
 * Два источника:
 * - `agent` — фото или PDF меню: файлы загружаются `platform/file_create`,
 *   `shop/menu_import_start` ставит WorkItem агенту `shop_menu_agent`;
 *   ход задачи показывает `shop-agent-jobs-banner` страницы.
 * - `file` — Excel или ответ Яндекс Еды: `shop/menu_file_import_run`
 *   разбирает файл синхронно, модалка показывает отчёт.
 *
 * Цель (`catalog` / `new_menu` / `into_menu`) задаёт, куда попадут блюда.
 */

import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type {
    ShopMenuFileFormat,
    ShopMenuFileImportReport,
    ShopMenuImportTarget,
} from '@platform/lib/events/wire/shop.gen.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { buildPlatformAuxiliaryFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

type ImportSource = 'agent' | 'file';

interface UploadedFile {
    file_id: string;
    name: string;
}

const TARGETS: readonly ShopMenuImportTarget[] = ['catalog', 'new_menu', 'into_menu'];
const MAX_AGENT_FILES = 20;

function isTarget(value: unknown): value is ShopMenuImportTarget {
    return value === 'catalog' || value === 'new_menu' || value === 'into_menu';
}

function isFileFormat(value: unknown): value is ShopMenuFileFormat {
    return value === 'xlsx' || value === 'yandex_json';
}

function formatFromName(name: string): ShopMenuFileFormat | null {
    const lower = name.toLowerCase();
    if (lower.endsWith('.xlsx')) return 'xlsx';
    if (lower.endsWith('.json')) return 'yandex_json';
    return null;
}

export class ShopMenuImportModal extends PlatformModal {
    static modalKind = 'shop.menu_import';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare target: ShopMenuImportTarget;
    declare shopMenuId: string | null;

    private _menusOp: ControllerFor<'shop/menus_list'>;
    private _uploadOp: ControllerFor<'platform/file_create'>;
    private _startOp: ControllerFor<'shop/menu_import_start'>;
    private _fileImportOp: ControllerFor<'shop/menu_file_import_run'>;

    declare _source: ImportSource;
    declare _target: ShopMenuImportTarget;
    declare _menuId: string;
    declare _menuName: string;
    declare _files: UploadedFile[];
    declare _format: ShopMenuFileFormat;
    declare _enrichAfter: boolean;
    declare _report: ShopMenuFileImportReport | null;

    static override properties = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        target: { attribute: false },
        shopMenuId: { attribute: false },
        _source: { state: true },
        _target: { state: true },
        _menuId: { state: true },
        _menuName: { state: true },
        _files: { state: true },
        _format: { state: true },
        _enrichAfter: { state: true },
        _report: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            :host { --modal-width: min(600px, 100%); }
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); line-height: 1.5; }
            .drop {
                display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-2);
                border: 1px dashed var(--glass-border-subtle); border-radius: var(--radius-lg);
                padding: var(--space-5); color: var(--text-tertiary); font-size: var(--text-sm);
                background: color-mix(in srgb, var(--text-primary) 3%, transparent);
                cursor: pointer; width: 100%; font: inherit;
            }
            .drop:hover { border-color: var(--accent); color: var(--accent); }
            .files { display: flex; flex-direction: column; gap: var(--space-1); }
            .file {
                display: flex; align-items: center; gap: var(--space-2);
                font-size: var(--text-sm); color: var(--text-secondary);
            }
            .file span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .report { display: flex; flex-direction: column; gap: var(--space-2); }
            .stats { display: flex; gap: var(--space-4); font-size: var(--text-sm); color: var(--text-primary); }
            .stats .warn { color: var(--warning); }
            .errors { font-size: var(--text-xs); color: var(--text-tertiary); max-height: 160px; overflow-y: auto; }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
        `,
    ];

    constructor() {
        super();
        this.target = 'catalog';
        this.shopMenuId = null;
        this._source = 'agent';
        this._target = 'catalog';
        this._menuId = '';
        this._menuName = '';
        this._files = [];
        this._format = 'xlsx';
        this._enrichAfter = true;
        this._report = null;
        this._menusOp = this.useOp('shop/menus_list');
        this._uploadOp = this.useOp('platform/file_create');
        this._startOp = this.useOp('shop/menu_import_start');
        this._fileImportOp = this.useOp('shop/menu_file_import_run');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopMenuImportModal: prop "shopId" required');
        }
        if (!isTarget(this.target)) {
            throw new Error('ShopMenuImportModal: prop "target" must be catalog | new_menu | into_menu');
        }
        if (this.target === 'into_menu' && (typeof this.shopMenuId !== 'string' || this.shopMenuId === '')) {
            throw new Error('ShopMenuImportModal: target into_menu requires prop "shopMenuId"');
        }
        this._target = this.target;
        this._menuId = typeof this.shopMenuId === 'string' ? this.shopMenuId : '';
        void this._menusOp.run({ shop_id: this.shopId });
    }

    private _menuOptions(): Array<{ value: string; label: string }> {
        const result = this._menusOp.lastResult;
        if (result === null) return [];
        return result.items
            .filter((menu) => menu.shop_id === this.shopId && menu.status !== 'archived')
            .map((menu) => ({ value: menu.shop_menu_id, label: menu.name }));
    }

    private _targetLabel(target: ShopMenuImportTarget): string {
        switch (target) {
            case 'catalog': return this.t('menu_import.target_catalog');
            case 'new_menu': return this.t('menu_import.target_new_menu');
            case 'into_menu': return this.t('menu_import.target_into_menu');
        }
    }

    private _setSource(value: unknown) {
        if (value !== 'agent' && value !== 'file') return;
        this._source = value;
        this._files = [];
        this._report = null;
    }

    private _pickFiles() {
        const input = this.renderRoot.querySelector<HTMLInputElement>('#import-files');
        if (input !== null) input.click();
    }

    private async _onFilesPicked(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement) || input.files === null) return;
        const picked = Array.from(input.files);
        input.value = '';
        if (this._source === 'file') {
            const file = picked[0];
            if (file === undefined) return;
            const format = formatFromName(file.name);
            if (format !== null) this._format = format;
            const uploaded = await this._upload(file);
            if (uploaded !== null) this._files = [uploaded];
            this._report = null;
            return;
        }
        for (const file of picked.slice(0, MAX_AGENT_FILES - this._files.length)) {
            const uploaded = await this._upload(file);
            if (uploaded === null) return;
            this._files = [...this._files, uploaded];
        }
    }

    private async _upload(file: File): Promise<UploadedFile | null> {
        const result = await this._uploadOp.run({ file, spec: buildPlatformAuxiliaryFileCreateSpecJson({}) });
        if (result === null) return null;
        const fileId = result.file_id;
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error('ShopMenuImportModal: platform/file_create must return result.file_id');
        }
        return { file_id: fileId, name: file.name };
    }

    private _removeFile(fileId: string) {
        this._files = this._files.filter((f) => f.file_id !== fileId);
    }

    private _targetReady(): boolean {
        if (this._target === 'new_menu') return this._menuName.trim() !== '';
        if (this._target === 'into_menu') return this._menuId !== '';
        return true;
    }

    private _targetPayload(): { shop_id: string; target: ShopMenuImportTarget; shop_menu_id: string | null; menu_name: string | null } {
        return {
            shop_id: this.shopId,
            target: this._target,
            shop_menu_id: this._target === 'into_menu' ? this._menuId : null,
            menu_name: this._target === 'new_menu' ? this._menuName.trim() : null,
        };
    }

    private async _submit() {
        if (this._files.length === 0 || !this._targetReady()) return;
        if (this._source === 'agent') {
            const started = await this._startOp.run({
                ...this._targetPayload(),
                file_ids: this._files.map((f) => f.file_id),
            });
            if (started !== null) this.close();
            return;
        }
        const file = this._files[0];
        if (file === undefined) return;
        const report = await this._fileImportOp.run({
            ...this._targetPayload(),
            file_id: file.file_id,
            format: this._format,
            enrich_after: this._enrichAfter,
        });
        if (report !== null) this._report = report;
    }

    override renderHeader() {
        return this.t('menu_import.title');
    }

    private _renderReport(report: ShopMenuFileImportReport): TemplateResult {
        return html`
            <div class="report">
                <div class="stats">
                    <span>${this.t('menu_import.report_created', { count: report.created })}</span>
                    ${report.similar > 0 ? html`<span class="warn">${this.t('menu_import.report_similar', { count: report.similar })}</span>` : nothing}
                    ${report.errors.length > 0 ? html`<span class="warn">${this.t('menu_import.report_errors', { count: report.errors.length })}</span>` : nothing}
                </div>
                ${report.enrich_work_item_id !== null ? html`<div class="hint">${this.t('menu_import.report_enrich')}</div>` : nothing}
                ${report.errors.length > 0 ? html`
                    <div class="errors">
                        ${report.errors.map((err) => html`<div>${this.t('menu_import.report_error_row', { row: err.row, code: err.error_code })}</div>`)}
                    </div>` : nothing}
            </div>`;
    }

    override renderBody(): TemplateResult {
        const agent = this._source === 'agent';
        const busy = this._uploadOp.busy || this._startOp.busy || this._fileImportOp.busy;
        return html`
            <div class="body">
                <platform-segmented-control
                    full-width
                    .value=${this._source}
                    .items=${[
                        { value: 'agent', label: this.t('menu_import.source_agent'), icon: 'image' },
                        { value: 'file', label: this.t('menu_import.source_file'), icon: 'table' },
                    ]}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._setSource(e.detail.value)}
                ></platform-segmented-control>
                <div class="hint">${agent ? this.t('menu_import.hint_agent') : this.t('menu_import.hint_file')}</div>

                <platform-field type="enum" mode="edit" label=${this.t('menu_import.field_target')} .value=${this._target}
                    .config=${{ values: TARGETS.map((target) => ({ value: target, label: this._targetLabel(target) })) }}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { if (isTarget(e.detail.value)) this._target = e.detail.value; }}
                ></platform-field>
                ${this._target === 'new_menu' ? html`
                    <platform-field type="string" mode="edit" label=${this.t('menu_import.field_menu_name')} .value=${this._menuName}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._menuName = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-field>` : nothing}
                ${this._target === 'into_menu' ? html`
                    <platform-field type="enum" mode="edit" label=${this.t('menu_import.field_menu')} .value=${this._menuId}
                        .config=${{ values: this._menuOptions() }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._menuId = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-field>` : nothing}

                <input id="import-files" type="file" hidden
                    ?multiple=${agent}
                    accept=${agent ? 'image/*,application/pdf' : '.xlsx,.json,application/json'}
                    @change=${(e: Event) => this._onFilesPicked(e)}>
                <button type="button" class="drop" ?disabled=${this._uploadOp.busy} @click=${() => this._pickFiles()}>
                    <platform-icon name="upload" size="20"></platform-icon>
                    <span>${agent ? this.t('menu_import.pick_agent', { max: MAX_AGENT_FILES }) : this.t('menu_import.pick_file')}</span>
                </button>
                ${this._files.length > 0 ? html`
                    <div class="files">
                        ${this._files.map((f) => html`
                            <div class="file">
                                <platform-icon name="file" size="14"></platform-icon>
                                <span title=${f.name}>${f.name}</span>
                                <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu_import.remove_file')}
                                    @click=${() => this._removeFile(f.file_id)}
                                ><platform-icon name="close" size="12"></platform-icon></platform-button>
                            </div>`)}
                    </div>` : nothing}

                ${agent ? nothing : html`
                    <platform-field type="enum" mode="edit" label=${this.t('menu_import.field_format')} .value=${this._format}
                        .config=${{ values: [
                            { value: 'xlsx', label: this.t('menu_import.format_xlsx') },
                            { value: 'yandex_json', label: this.t('menu_import.format_yandex_json') },
                        ] }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { if (isFileFormat(e.detail.value)) this._format = e.detail.value; }}
                    ></platform-field>
                    <platform-switch
                        label=${this.t('menu_import.field_enrich_after')}
                        ?checked=${this._enrichAfter}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._enrichAfter = e.detail.value === true; }}
                    ></platform-switch>`}

                ${this._report !== null ? this._renderReport(this._report) : nothing}

                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>
                        ${this._report !== null ? this.t('menu_import.done') : this.t('menu_import.cancel')}
                    </platform-button>
                    <platform-button variant="primary" ?loading=${busy}
                        ?disabled=${this._files.length === 0 || !this._targetReady()}
                        @click=${() => this._submit()}
                    ><platform-icon name="import" size="14"></platform-icon> ${agent ? this.t('menu_import.run_agent') : this.t('menu_import.run_file')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-menu-import-modal', ShopMenuImportModal);
registerModalKind(ShopMenuImportModal.modalKind, 'shop-menu-import-modal');
