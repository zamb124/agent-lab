/**
 * Per-company override провайдеров речи: stt / tts.
 *
 * Данные: `frontend/company_voice_providers_load`, каталог
 * `frontend/voice_providers_catalog_load`. Списки провайдеров без `mock`
 * (deployment-only). Меняют только owner/admin (BE).
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/layout/page-header.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';

const KINDS = ['stt', 'tts'];
const STT_TTS_UI = ['litserve', 'cloud_ru', 'yandex', 'sber'];
const RESPONSE_FORMATS = ['', 'wav', 'mp3', 'ogg', 'pcm', 'lpcm'];

function _emptySecretsDraft() {
    return {
        api_key: '',
        folder_id: '',
        client_id: '',
        client_secret: '',
        scope: '',
    };
}

function _emptyDraft() {
    return {
        provider: '',
        model: '',
        voice: '',
        language: '',
        sample_rate: '',
        threshold: '',
        response_format: '',
        secrets: _emptySecretsDraft(),
    };
}

function _trimOrEmpty(v) {
    if (typeof v !== 'string') return '';
    return v.trim();
}

function _needsModel(provider) {
    if (provider === '') return false;
    return (
        provider === 'litserve' ||
        provider === 'cloud_ru' ||
        provider === 'yandex' ||
        provider === 'sber'
    );
}

function _needsCredentials(provider) {
    return provider === 'cloud_ru' || provider === 'yandex' || provider === 'sber';
}

function _itemToDraft(item) {
    if (!item || typeof item !== 'object') return _emptyDraft();
    const prov = typeof item.provider === 'string' ? item.provider : '';
    const secrets = _emptySecretsDraft();
    const sm = item.secrets_meta;
    if (sm && typeof sm === 'object') {
        if (typeof sm.folder_id === 'string') secrets.folder_id = sm.folder_id;
        if (typeof sm.client_id === 'string') secrets.client_id = sm.client_id;
        if (typeof sm.scope === 'string') secrets.scope = sm.scope;
    }
    return {
        provider: prov,
        model: typeof item.model === 'string' ? item.model : '',
        voice: typeof item.voice === 'string' ? item.voice : '',
        language: typeof item.language === 'string' ? item.language : '',
        sample_rate:
            typeof item.sample_rate === 'number' ? String(item.sample_rate) : '',
        threshold:
            typeof item.threshold === 'number' ? String(item.threshold) : '',
        response_format:
            typeof item.response_format === 'string' ? item.response_format : '',
        secrets,
    };
}

export class FrontendCompanyVoiceProvidersPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
                gap: var(--space-4);
            }
            .card {
                padding: var(--space-4);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                display: flex; flex-direction: column; gap: var(--space-3);
            }
            .card h3 {
                margin: 0;
                color: var(--text-primary);
                font-size: var(--text-base);
            }
            .card h4 {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            label {
                display: flex;
                flex-direction: column;
                gap: 2px;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            select {
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
            .row {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
            }
            .hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    static properties = {
        _drafts: { state: true },
        _credEditedByKind: { state: true },
    };

    static i18nNamespace = 'frontend';

    constructor() {
        super();
        this._catalog = this.useOp('frontend/voice_providers_catalog_load');
        this._load = this.useOp('frontend/company_voice_providers_load');
        this._upsert = this.useOp('frontend/company_voice_providers_upsert');
        this._remove = this.useOp('frontend/company_voice_providers_remove');
        this._auth = this.select((s) => s.auth);
        this._drafts = { stt: _emptyDraft(), tts: _emptyDraft() };
        this._credEditedByKind = { stt: false, tts: false };
    }

    connectedCallback() {
        super.connectedCallback();
        this._reload();
    }

    _activeCompanyId() {
        const auth = this._auth.value;
        if (!auth) return null;
        const cid = auth.activeCompanyId;
        if (typeof cid !== 'string' || cid.length === 0) return null;
        return cid;
    }

    async _reload() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await Promise.all([
            this._catalog.run({}),
            this._load.run({ company_id }),
        ]);
        const result = this._load.lastResult;
        if (result && Array.isArray(result.items)) {
            const drafts = {
                stt: _emptyDraft(),
                tts: _emptyDraft(),
            };
            for (const item of result.items) {
                if (typeof item.kind === 'string') {
                    drafts[item.kind] = _itemToDraft(item);
                }
            }
            this._drafts = drafts;
        }
        this._credEditedByKind = { stt: false, tts: false };
    }

    _secretsMetaForKind(kind) {
        const r = this._load.lastResult;
        if (!r || !Array.isArray(r.items)) return null;
        for (let i = 0; i < r.items.length; i += 1) {
            const it = r.items[i];
            if (
                it &&
                typeof it.kind === 'string' &&
                it.kind === kind &&
                typeof it.secrets_meta === 'object' &&
                it.secrets_meta !== null
            ) {
                return it.secrets_meta;
            }
        }
        return null;
    }

    _setField(kind, field, value) {
        const base = this._drafts[kind];
        let nextSecrets = base.secrets;
        let nextDraft;
        if (field === 'provider') {
            nextSecrets = _emptySecretsDraft();
            nextDraft = { ...base, secrets: nextSecrets };
            nextDraft[field] = value;
        } else {
            nextDraft = { ...base, [field]: value };
        }
        this._drafts = { ...this._drafts, [kind]: nextDraft };
        if (field === 'provider') {
            this._credEditedByKind = {
                ...this._credEditedByKind,
                [kind]: false,
            };
        }
    }

    _setSecret(kind, field, value) {
        const sec = { ...this._drafts[kind].secrets };
        sec[field] = value;
        this._drafts = {
            ...this._drafts,
            [kind]: { ...this._drafts[kind], secrets: sec },
        };
        this._credEditedByKind = { ...this._credEditedByKind, [kind]: true };
    }

    _modelOptions(kind, provider) {
        const catalog = this._catalog.lastResult;
        if (!catalog) return [];
        if (provider === 'litserve') {
            if (kind === 'stt') return [...catalog.stt_litserve_models];
            if (kind === 'tts') return [...catalog.tts_litserve_models];
            return [];
        }
        if (provider === 'cloud_ru') {
            if (kind === 'stt') return [...catalog.cloud_ru_stt_models];
            if (kind === 'tts') return [...catalog.cloud_ru_tts_models];
            return [];
        }
        if (provider === 'yandex') return [...catalog.yandex_speech_models];
        if (provider === 'sber') return [...catalog.sber_speech_models];
        return [];
    }

    _secretsPayload(kind, provider) {
        const draft = this._drafts[kind];
        const s = draft.secrets;
        if (provider === 'cloud_ru') {
            const t = _trimOrEmpty(s.api_key);
            if (t !== '') return { api_key: t };
            return { api_key: null };
        }
        if (provider === 'yandex') {
            const out = {};
            const ak = _trimOrEmpty(s.api_key);
            if (ak !== '') out.api_key = ak;
            else out.api_key = null;
            const fd = _trimOrEmpty(s.folder_id);
            if (fd !== '') out.folder_id = fd;
            else out.folder_id = null;
            return out;
        }
        if (provider === 'sber') {
            const out = {};
            const cid = _trimOrEmpty(s.client_id);
            if (cid !== '') out.client_id = cid;
            else out.client_id = null;
            const cs = _trimOrEmpty(s.client_secret);
            if (cs !== '') out.client_secret = cs;
            else out.client_secret = null;
            const sc = _trimOrEmpty(s.scope);
            if (sc !== '') out.scope = sc;
            else out.scope = null;
            return out;
        }
        return {};
    }

    async _save(kind) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const draft = this._drafts[kind];
        if (typeof draft.provider !== 'string' || draft.provider.length === 0) {
            this.toast('frontend:company_voice_providers_page.err_provider_required', {
                type: 'error',
            });
            return;
        }
        let sample_rate = null;
        const srTxt = _trimOrEmpty(draft.sample_rate);
        if (srTxt !== '') {
            const sr = Number(srTxt);
            if (!Number.isFinite(sr)) {
                this.toast('frontend:company_voice_providers_page.err_sample_rate_nan', {
                    type: 'error',
                });
                return;
            }
            sample_rate = sr;
        }
        let threshold = null;
        const thTxt = _trimOrEmpty(draft.threshold);
        if (thTxt !== '') {
            const th = Number(thTxt);
            if (!Number.isFinite(th)) {
                this.toast('frontend:company_voice_providers_page.err_threshold_nan', {
                    type: 'error',
                });
                return;
            }
            threshold = th;
        }
        const modelTrim = _trimOrEmpty(draft.model);
        const model = modelTrim !== '' ? modelTrim : null;
        const voiceTrim = _trimOrEmpty(draft.voice);
        const voice = voiceTrim !== '' ? voiceTrim : null;
        const languageTrim = _trimOrEmpty(draft.language);
        const language = languageTrim !== '' ? languageTrim : null;
        const rfTrim = _trimOrEmpty(draft.response_format);
        const response_format = rfTrim !== '' ? rfTrim : null;

        const payload = {
            company_id,
            kind,
            provider: draft.provider,
            model,
            voice,
            language,
            sample_rate,
            threshold,
            response_format,
        };
        const edited = this._credEditedByKind[kind];
        if (edited && _needsCredentials(draft.provider)) {
            payload.secrets = this._secretsPayload(kind, draft.provider);
        }
        await this._upsert.run(payload);
        await this._reload();
    }

    async _resetToDefault(kind) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await this._remove.run({ company_id, kind });
        this._drafts = { ...this._drafts, [kind]: _emptyDraft() };
        this._credEditedByKind = { ...this._credEditedByKind, [kind]: false };
        await this._reload();
    }

    _renderModelRow(kind, draft) {
        if (!_needsModel(draft.provider)) return nothing;
        const opts = this._modelOptions(kind, draft.provider);
        if (!Array.isArray(opts) || opts.length === 0) return nothing;
        const values = [
            { value: '', label: this.t('company_voice_providers_page.option_default') },
            ...opts.map((id) => ({ value: id, label: id })),
        ];
        const hint = draft.provider === 'litserve'
            ? this.t('company_voice_providers_page.model_default_litserve')
            : '';
        return html`
            <platform-field
                type="enum"
                mode="edit"
                .label=${this.t('company_voice_providers_page.field_model')}
                .value=${draft.model}
                .config=${{ values }}
                .hint=${hint}
                @change=${(e) => this._setField(kind, 'model', e.detail.value)}
            ></platform-field>
        `;
    }

    _apiKeyPlaceholder(secretsMeta) {
        if (secretsMeta && secretsMeta.api_key_set === true) {
            return this.t('company_voice_providers_page.placeholder_secret_set');
        }
        return '';
    }

    _renderCredentials(kind, draft, secretsMeta) {
        const p = draft.provider;
        if (!_needsCredentials(p)) return nothing;

        let providerHint = nothing;
        if (p === 'cloud_ru') {
            providerHint = html`<div class="hint">
                ${this.t('company_voice_providers_page.hint_cloud_ru_credentials')}
            </div>`;
        }
        if (p === 'yandex') {
            providerHint = html`<div class="hint">
                ${this.t('company_voice_providers_page.hint_yandex_stub')}
            </div>`;
        }
        if (p === 'sber') {
            providerHint = html`<div class="hint">
                ${this.t('company_voice_providers_page.hint_sber_stub')}
            </div>`;
        }

        const cloudOrYandexKey =
            p === 'cloud_ru' || p === 'yandex'
                ? html`<platform-field
                      type="string"
                      input-type="password"
                      mode="edit"
                      .label=${this.t('company_voice_providers_page.field_api_key')}
                      .value=${draft.secrets.api_key}
                      .placeholder=${this._apiKeyPlaceholder(secretsMeta)}
                      @change=${(e) => this._setSecret(kind, 'api_key', e.detail.value)}
                  ></platform-field>`
                : nothing;

        const yandexFolder =
            p === 'yandex'
                ? html`<platform-field
                      type="string"
                      mode="edit"
                      .label=${this.t('company_voice_providers_page.field_folder_id')}
                      .value=${draft.secrets.folder_id}
                      @change=${(e) => this._setSecret(kind, 'folder_id', e.detail.value)}
                  ></platform-field>`
                : nothing;

        const sberBlock =
            p === 'sber'
                ? html`
                      <platform-field
                          type="string"
                          mode="edit"
                          .label=${this.t('company_voice_providers_page.field_client_id')}
                          .value=${draft.secrets.client_id}
                          @change=${(e) => this._setSecret(kind, 'client_id', e.detail.value)}
                      ></platform-field>
                      <platform-field
                          type="string"
                          input-type="password"
                          mode="edit"
                          .label=${this.t('company_voice_providers_page.field_client_secret')}
                          .value=${draft.secrets.client_secret}
                          .placeholder=${secretsMeta && secretsMeta.client_secret_set === true
                              ? this.t('company_voice_providers_page.placeholder_secret_set')
                              : ''}
                          @change=${(e) => this._setSecret(kind, 'client_secret', e.detail.value)}
                      ></platform-field>
                      <platform-field
                          type="string"
                          mode="edit"
                          .label=${this.t('company_voice_providers_page.field_scope')}
                          .value=${draft.secrets.scope}
                          @change=${(e) => this._setSecret(kind, 'scope', e.detail.value)}
                      ></platform-field>
                  `
                : nothing;

        return html`
            <h4>${this.t('company_voice_providers_page.credentials_heading')}</h4>
            ${providerHint}
            ${cloudOrYandexKey}
            ${yandexFolder}
            ${sberBlock}
        `;
    }

    _renderCard(kind) {
        const draft = this._drafts[kind];
        const secretsMeta = this._secretsMetaForKind(kind);
        const providers = STT_TTS_UI;
        const busy = this._upsert.busy || this._remove.busy;
        const providerValues = [
            { value: '', label: this.t('company_voice_providers_page.option_default') },
            ...providers.map((p) => ({ value: p, label: p })),
        ];
        const responseFormatValues = RESPONSE_FORMATS.map((f) => ({
            value: f,
            label: f === '' ? this.t('company_voice_providers_page.option_default') : f,
        }));
        return html`
            <div class="card">
                <h3>${this.t(`company_voice_providers_page.title_${kind}`)}</h3>
                <platform-field
                    type="enum"
                    mode="edit"
                    .label=${this.t('company_voice_providers_page.field_provider')}
                    .value=${draft.provider}
                    .config=${{ values: providerValues }}
                    .hint=${this.t(`company_voice_providers_page.hint_${kind}`)}
                    @change=${(e) => this._setField(kind, 'provider', e.detail.value)}
                ></platform-field>
                ${this._renderModelRow(kind, draft)}
                ${kind === 'tts'
                    ? html`
                          <platform-field
                              type="string"
                              mode="edit"
                              .label=${this.t('company_voice_providers_page.field_voice')}
                              .value=${draft.voice}
                              @change=${(e) => this._setField(kind, 'voice', e.detail.value)}
                          ></platform-field>
                          <platform-field
                              type="enum"
                              mode="edit"
                              .label=${this.t('company_voice_providers_page.field_response_format')}
                              .value=${draft.response_format}
                              .config=${{ values: responseFormatValues }}
                              @change=${(e) => this._setField(kind, 'response_format', e.detail.value)}
                          ></platform-field>
                      `
                    : nothing}
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('company_voice_providers_page.field_language')}
                    .value=${draft.language}
                    placeholder="ru-RU"
                    @change=${(e) => this._setField(kind, 'language', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('company_voice_providers_page.field_sample_rate')}
                    .value=${draft.sample_rate}
                    placeholder="16000"
                    @change=${(e) => this._setField(kind, 'sample_rate', e.detail.value)}
                ></platform-field>
                ${this._renderCredentials(kind, draft, secretsMeta)}
                <div class="row">
                    <glass-button
                        variant="ghost"
                        ?disabled=${busy}
                        @click=${() => this._resetToDefault(kind)}
                    >${this.t('company_voice_providers_page.action_reset')}</glass-button>
                    <glass-button
                        variant="primary"
                        ?disabled=${busy}
                        @click=${() => this._save(kind)}
                    >${this.t('company_voice_providers_page.action_save')}</glass-button>
                </div>
            </div>
        `;
    }

    render() {
        const company_id = this._activeCompanyId();
        if (!company_id) {
            return html`
                <page-header .title=${this.t('company_voice_providers_page.title')}></page-header>
                <div>${this.t('company_voice_providers_page.empty_no_company')}</div>
            `;
        }
        const loading = this._load.busy || this._catalog.busy;
        return html`
            <page-header
                .title=${this.t('company_voice_providers_page.title')}
                .subtitle=${this.t('company_voice_providers_page.subtitle')}
            ></page-header>
            ${loading
                ? html`<glass-spinner></glass-spinner>`
                : html`<div class="grid">${KINDS.map((k) => this._renderCard(k))}</div>`}
        `;
    }
}

customElements.define('frontend-company-voice-providers-page', FrontendCompanyVoiceProvidersPage);
