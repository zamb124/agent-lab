/**
 * Модалка добавления Custom OpenAI-compatible провайдера компании.
 *
 * Открывается из settings-page (вкладка AI providers, блок Custom providers).
 * При submit: create → aiCustomProviderCreateOp, редактирование → aiCustomProviderUpdateOp.
 * Открытие: openModal(kind, { initialProvider: null }) или { initialProvider: {...} }.
 * resource перезагружает aiProvidersLoadOp по onSuccess.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-switch.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function thrownMessage(error: unknown): string {
    if (!(error instanceof Error)) throw error;
    return error.message;
}

const ALL_CAPABILITIES = Object.freeze([
    'llm_chat',
    'llm_summarize',
    'llm_format_markdown',
    'llm_codegen',
    'llm_vision',
    'embedding',
    'rerank',
    'image_gen',
    'voice_stt',
    'voice_tts',
]);

export class FrontendAiCustomProviderModal extends PlatformFormModal {
    static modalKind = 'frontend.ai_custom_provider_create';
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                width: 100%;
                min-width: 0;
            }
            .form-row-2 {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            @media (max-width: 600px) {
                .form-row-2 { grid-template-columns: 1fr; }
            }
            .caps-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                margin-top: var(--space-1);
            }
            .caps-grid .cap-row {
                display: flex; align-items: center; gap: var(--space-2);
                color: var(--text-primary);
                cursor: pointer;
                user-select: none;
            }
            .caps-grid .cap-row span { line-height: 1.2; }
            .caps-block { display: flex; flex-direction: column; gap: var(--space-1); }
            .help { color: var(--text-tertiary); font-size: var(--text-xs); margin: 0; }
        `,
    ];

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        /** @type {Record<string, unknown>|null|undefined} сырой объект из API — сидирует форму в режиме правки */
        initialProvider: { type: Object, attribute: false },
        _editingId: { state: true },
        _id: { state: true },
        _label: { state: true },
        _baseUrl: { state: true },
        _apiKey: { state: true },
        _rerankPath: { state: true },
        _capabilities: { state: true },
        _modelByCapJson: { state: true },
        _headersJson: { state: true },
        _extraBodyJson: { state: true },
    }
    declare initialProvider: Record<string, unknown> | null;
    declare _editingId: any;
    declare _id: string;
    declare _label: string;
    declare _baseUrl: string;
    declare _apiKey: string;
    declare _rerankPath: string;
    declare _capabilities: any[];
    declare _modelByCapJson: string;
    declare _headersJson: string;
    declare _extraBodyJson: string;
;

    constructor() {
        super();
        this.initialProvider = null;
        this._editingId = null;
        this._id = '';
        this._label = '';
        this._baseUrl = '';
        this._apiKey = '';
        this._rerankPath = '';
        this._capabilities = [];
        this._modelByCapJson = '';
        this._headersJson = '';
        this._extraBodyJson = '';
        this.size = 'lg';
        this._create = this.useOp('frontend/ai_custom_provider_create');
        this._update = this.useOp('frontend/ai_custom_provider_update');
    }
    private _create: OpController;
    private _update: OpController;


    _resetForm() {
        this._editingId = null;
        this._id = '';
        this._label = '';
        this._baseUrl = '';
        this._apiKey = '';
        this._rerankPath = '';
        this._capabilities = [];
        this._modelByCapJson = '';
        this._headersJson = '';
        this._extraBodyJson = '';
    }

    _seedFromProvider(p: Record<string, unknown>) {
        if (!p || typeof p !== 'object') {
            this._resetForm();
            return;
        }
        const pid = p.id != null ? String(p.id) : '';
        this._editingId = pid.length > 0 ? pid : null;
        this._id = pid;
        this._label = p.label != null ? String(p.label) : '';
        const bu = p.base_url != null ? String(p.base_url) : (p.baseUrl != null ? String(p.baseUrl) : '');
        this._baseUrl = bu;
        this._apiKey = '';
        this._rerankPath = p.rerank_path != null
            ? String(p.rerank_path)
            : (p.rerankPath != null ? String(p.rerankPath) : '');
        const caps = Array.isArray(p.capabilities) ? p.capabilities.map((c) => String(c)) : [];
        this._capabilities = caps;
        const mbc = p.model_by_capability && typeof p.model_by_capability === 'object' && !Array.isArray(p.model_by_capability)
            ? p.model_by_capability
            : {};
        this._modelByCapJson = Object.keys(mbc).length ? JSON.stringify(mbc, null, 2) : '';
        const hdr = p.extra_request_headers && typeof p.extra_request_headers === 'object' && !Array.isArray(p.extra_request_headers)
            ? p.extra_request_headers
            : {};
        this._headersJson = Object.keys(hdr).length ? JSON.stringify(hdr, null, 2) : '';
        const eb = p.extra_request_body && typeof p.extra_request_body === 'object' && !Array.isArray(p.extra_request_body)
            ? p.extra_request_body
            : {};
        this._extraBodyJson = Object.keys(eb).length ? JSON.stringify(eb, null, 2) : '';
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('initialProvider')) {
            const p = this.initialProvider;
            if (p && typeof p === 'object' && (p.id != null && String(p.id).length > 0)) {
                this._seedFromProvider(p);
            } else {
                this._resetForm();
            }
            this.isDirty = false;
        }
        this.title = this._editingId
            ? this.t('settings_page.ai_providers.custom_modal_title_edit')
            : this.t('settings_page.ai_providers.custom_modal_title');
    }

    _fieldString(event: CustomEvent, label: string): string {
        const detail = event.detail;
        if (!isPlainRecord(detail) || typeof detail.value !== 'string') {
            throw new Error(`ai-custom-provider: ${label} expects detail.value string`);
        }
        return detail.value;
    }

    _toggleCapability(cap: string, checked: boolean) {
        const set = new Set(this._capabilities);
        if (checked) set.add(cap);
        else set.delete(cap);
        this._capabilities = Array.from(set);
        this.isDirty = true;
    }

    _parseJsonObject(raw: string, label: string) {
        const trimmed = raw.trim();
        if (!trimmed) return null;
        let parsed;
        try {
            parsed = JSON.parse(trimmed);
        } catch (e) {
            throw new Error(this.t('settings_page.ai_providers.custom_modal_json_invalid', { field: label }));
        }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error(this.t('settings_page.ai_providers.custom_modal_json_invalid', { field: label }));
        }
        return parsed;
    }

    override validateForm() {
        const errors: Record<string, unknown> = {};
        const id = this._id.trim();
        if (!id || !/^[a-z0-9_-]{1,32}$/.test(id)) {
            errors.id = this.t('settings_page.ai_providers.custom_modal_id_invalid');
        }
        if (!this._label.trim()) {
            errors.label = this.t('settings_page.ai_providers.custom_modal_label_required');
        }
        const url = this._baseUrl.trim();
        if (!url || !(url.startsWith('http://') || url.startsWith('https://'))) {
            errors.base_url = this.t('settings_page.ai_providers.custom_modal_base_url_invalid');
        }
        if (!this._editingId && !this._apiKey.trim()) {
            errors.api_key = this.t('settings_page.ai_providers.custom_modal_api_key_required');
        }
        if (!this._capabilities.length) {
            errors.capabilities = this.t('settings_page.ai_providers.custom_modal_caps_required');
        }
        if (this._capabilities.includes('rerank') && !this._rerankPath.trim()) {
            errors.rerank_path = this.t('settings_page.ai_providers.custom_modal_rerank_path_required');
        }
        try {
            this._parseJsonObject(this._modelByCapJson, 'model_by_capability');
        } catch (error) {
            errors.model_by_capability = thrownMessage(error);
        }
        try {
            this._parseJsonObject(this._headersJson, 'extra_request_headers');
        } catch (error) {
            errors.extra_request_headers = thrownMessage(error);
        }
        try {
            this._parseJsonObject(this._extraBodyJson, 'extra_request_body');
        } catch (error) {
            errors.extra_request_body = thrownMessage(error);
        }
        return errors;
    }

    override async handleSubmit() {
        if (this._editingId) {
            const body: Record<string, unknown> = {
                provider_id: this._editingId,
                label: this._label.trim(),
                base_url: this._baseUrl.trim(),
                capabilities: [...this._capabilities],
            };
            const keyTrim = this._apiKey.trim();
            if (keyTrim) body.api_key = keyTrim;
            const rerankPath = this._rerankPath.trim();
            if (rerankPath) body.rerank_path = rerankPath;
            const modelByCap = this._parseJsonObject(this._modelByCapJson, 'model_by_capability');
            if (modelByCap) body.model_by_capability = modelByCap;
            const headers = this._parseJsonObject(this._headersJson, 'extra_request_headers');
            if (headers) body.extra_request_headers = headers;
            const extraBody = this._parseJsonObject(this._extraBodyJson, 'extra_request_body');
            if (extraBody) body.extra_request_body = extraBody;
            this._update.run(body);
        } else {
            const body: Record<string, unknown> = {
                id: this._id.trim(),
                label: this._label.trim(),
                base_url: this._baseUrl.trim(),
                api_key: this._apiKey.trim(),
                capabilities: [...this._capabilities],
            };
            const rerankPath = this._rerankPath.trim();
            if (rerankPath) body.rerank_path = rerankPath;
            const modelByCap = this._parseJsonObject(this._modelByCapJson, 'model_by_capability');
            if (modelByCap) body.model_by_capability = modelByCap;
            const headers = this._parseJsonObject(this._headersJson, 'extra_request_headers');
            if (headers) body.extra_request_headers = headers;
            const extraBody = this._parseJsonObject(this._extraBodyJson, 'extra_request_body');
            if (extraBody) body.extra_request_body = extraBody;
            this._create.run(body);
        }
        this.closeAfterSave();
    }

    override renderBody() {
        return html`
            <div class="form-grid">
                <p class="help">${this.t('settings_page.ai_providers.custom_modal_help')}</p>
                <div class="form-row-2">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_id_label')}
                        .value=${this._id}
                        ?disabled=${!!this._editingId}
                        @change=${(e: CustomEvent) => { this._id = this._fieldString(e, 'id'); this.isDirty = true; }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_label_label')}
                        .value=${this._label}
                        @change=${(e: CustomEvent) => { this._label = this._fieldString(e, 'label'); this.isDirty = true; }}
                    ></platform-field>
                </div>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('settings_page.ai_providers.custom_modal_base_url_label')}
                    .value=${this._baseUrl}
                    .placeholder=${'https://api.your-provider.com/v1'}
                    @change=${(e: CustomEvent) => { this._baseUrl = this._fieldString(e, 'base_url'); this.isDirty = true; }}
                ></platform-field>
                <platform-field
                    type="password"
                    mode="edit"
                    .label=${this.t('settings_page.ai_providers.custom_modal_api_key_label')}
                    .value=${this._apiKey}
                    .placeholder=${this._editingId ? this.t('settings_page.ai_providers.custom_modal_api_key_placeholder_edit') : 'sk-...'}
                    @change=${(e: CustomEvent) => { this._apiKey = this._fieldString(e, 'api_key'); this.isDirty = true; }}
                ></platform-field>
                ${this._editingId ? html`<small class="help">${this.t('settings_page.ai_providers.custom_modal_api_key_keep_edit')}</small>` : ''}
                <div class="caps-block">
                    <div class="help">${this.t('settings_page.ai_providers.custom_modal_caps_label')}</div>
                    <div class="caps-grid">
                        ${ALL_CAPABILITIES.map((cap) => html`
                            <label class="cap-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._capabilities.includes(cap)}
                                    @change=${(e: CustomEvent) => this._toggleCapability(String(cap), !!(e.detail && e.detail.value))}
                                ></platform-switch>
                                <span>${this.t(`settings_page.ai_providers.cap_${cap}`)}</span>
                            </label>
                        `)}
                    </div>
                </div>
                ${this._capabilities.includes('rerank') ? html`
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_rerank_path_label')}
                        .value=${this._rerankPath}
                        @change=${(e: CustomEvent) => { this._rerankPath = this._fieldString(e, 'rerank_path'); this.isDirty = true; }}
                    ></platform-field>
                ` : ''}
                <div class="caps-block">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_model_by_cap_label')}
                        .value=${this._modelByCapJson}
                        .placeholder=${'{\n  "llm_chat": "llama-3.1-70b",\n  "embedding": "bge-m3"\n}'}
                        @change=${(e: CustomEvent) => { this._modelByCapJson = this._fieldString(e, 'model_by_capability'); this.isDirty = true; }}
                    ></platform-field>
                    <small class="help">${this.t('settings_page.ai_providers.custom_modal_model_by_cap_help')}</small>
                </div>
                <div class="caps-block">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_headers_label')}
                        .value=${this._headersJson}
                        .placeholder=${'{\n  "X-Org": "acme",\n  "X-Project": "internal-rag"\n}'}
                        @change=${(e: CustomEvent) => { this._headersJson = this._fieldString(e, 'extra_request_headers'); this.isDirty = true; }}
                    ></platform-field>
                    <small class="help">${this.t('settings_page.ai_providers.custom_modal_headers_help')}</small>
                </div>
                <div class="caps-block">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('settings_page.ai_providers.custom_modal_extra_body_label')}
                        .value=${this._extraBodyJson}
                        .placeholder=${'{\n  "top_p": 0.9,\n  "safety_settings": {\n    "harassment": "block_none"\n  }\n}'}
                        @change=${(e: CustomEvent) => { this._extraBodyJson = this._fieldString(e, 'extra_request_body'); this.isDirty = true; }}
                    ></platform-field>
                    <small class="help">${this.t('settings_page.ai_providers.custom_modal_extra_body_help')}</small>
                </div>
            </div>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('settings_page.ai_providers.custom_modal_cancel')}
                </button>
                <button type="button" class="btn btn-primary" @click=${() => this._performSave()}>
                    ${this._editingId
                        ? this.t('settings_page.ai_providers.custom_modal_save')
                        : this.t('settings_page.ai_providers.custom_modal_create')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-ai-custom-provider-modal', FrontendAiCustomProviderModal);
registerModalKind(FrontendAiCustomProviderModal.modalKind, 'frontend-ai-custom-provider-modal');
