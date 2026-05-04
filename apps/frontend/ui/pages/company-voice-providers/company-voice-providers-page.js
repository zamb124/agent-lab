/**
 * Per-company override провайдеров речи: stt / tts / vad.
 *
 * Данные: `frontend/company_voice_providers_load`, каталог
 * `frontend/voice_providers_catalog_load`. Списки провайдеров без `mock`
 * (deployment-only). Меняют только owner/admin (BE).
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/layout/page-header.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';

const KINDS = ['stt', 'tts', 'vad'];
const STT_TTS_UI = ['litserve', 'cloud_ru', 'yandex', 'sber'];
const VAD_UI = ['litserve', 'silero_local'];
const RESPONSE_FORMATS = ['', 'wav', 'mp3', 'ogg', 'pcm', 'lpcm'];

function _providersFor(kind) {
    return kind === 'vad' ? VAD_UI : STT_TTS_UI;
}

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

function _needsModel(kind, provider) {
    if (provider === '') return false;
    if (provider === 'silero_local' && kind === 'vad') return false;
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
        this._drafts = { stt: _emptyDraft(), tts: _emptyDraft(), vad: _emptyDraft() };
        this._credEditedByKind = { stt: false, tts: false, vad: false };
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
                vad: _emptyDraft(),
            };
            for (const item of result.items) {
                if (typeof item.kind === 'string') {
                    drafts[item.kind] = _itemToDraft(item);
                }
            }
            this._drafts = drafts;
        }
        this._credEditedByKind = { stt: false, tts: false, vad: false };
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
            return [...catalog.vad_litserve_models];
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
        if (!_needsModel(kind, draft.provider)) return nothing;
        const opts = this._modelOptions(kind, draft.provider);
        if (!Array.isArray(opts) || opts.length === 0) return nothing;
        const litserveHint =
            draft.provider === 'litserve'
                ? html`<div class="hint">
                      ${this.t('company_voice_providers_page.model_default_litserve')}
                  </div>`
                : nothing;
        return html`
            <label>
                ${this.t('company_voice_providers_page.field_model')}
                <select
                    .value=${draft.model}
                    @change=${(e) => this._setField(kind, 'model', e.target.value)}
                >
                    <option value="">
                        ${this.t('company_voice_providers_page.option_default')}
                    </option>
                    ${opts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
                ${litserveHint}
            </label>
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
                ? html`<label>
                      ${this.t('company_voice_providers_page.field_api_key')}
                      <glass-input
                          type="password"
                          .value=${draft.secrets.api_key}
                          placeholder=${this._apiKeyPlaceholder(secretsMeta)}
                          @input=${(e) =>
                              this._setSecret(kind, 'api_key', e.detail.value)}
                      ></glass-input>
                  </label>`
                : nothing;

        const yandexFolder =
            p === 'yandex'
                ? html`<label>
                      ${this.t('company_voice_providers_page.field_folder_id')}
                      <glass-input
                          .value=${draft.secrets.folder_id}
                          @input=${(e) =>
                              this._setSecret(kind, 'folder_id', e.detail.value)}
                      ></glass-input>
                  </label>`
                : nothing;

        const sberBlock =
            p === 'sber'
                ? html`
                      <label>
                          ${this.t('company_voice_providers_page.field_client_id')}
                          <glass-input
                              .value=${draft.secrets.client_id}
                              @input=${(e) =>
                                  this._setSecret(
                                      kind,
                                      'client_id',
                                      e.detail.value,
                                  )}
                          ></glass-input>
                      </label>
                      <label>
                          ${this.t('company_voice_providers_page.field_client_secret')}
                          <glass-input
                              type="password"
                              .value=${draft.secrets.client_secret}
                              placeholder=${secretsMeta &&
                              secretsMeta.client_secret_set === true
                                  ? this.t(
                                        'company_voice_providers_page.placeholder_secret_set',
                                    )
                                  : ''}
                              @input=${(e) =>
                                  this._setSecret(
                                      kind,
                                      'client_secret',
                                      e.detail.value,
                                  )}
                          ></glass-input>
                      </label>
                      <label>
                          ${this.t('company_voice_providers_page.field_scope')}
                          <glass-input
                              .value=${draft.secrets.scope}
                              @input=${(e) =>
                                  this._setSecret(kind, 'scope', e.detail.value)}
                          ></glass-input>
                      </label>
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
        const providers = _providersFor(kind);
        const busy = this._upsert.busy || this._remove.busy;
        return html`
            <div class="card">
                <h3>${this.t(`company_voice_providers_page.title_${kind}`)}</h3>
                <div class="hint">${this.t(`company_voice_providers_page.hint_${kind}`)}</div>
                <label>
                    ${this.t('company_voice_providers_page.field_provider')}
                    <select
                        .value=${draft.provider}
                        @change=${(e) =>
                            this._setField(kind, 'provider', e.target.value)}
                    >
                        <option value="">
                            ${this.t('company_voice_providers_page.option_default')}
                        </option>
                        ${providers.map((p) => html`<option value=${p}>${p}</option>`)}
                    </select>
                </label>
                ${this._renderModelRow(kind, draft)}
                ${kind === 'tts'
                    ? html`
                          <label>
                              ${this.t('company_voice_providers_page.field_voice')}
                              <glass-input
                                  .value=${draft.voice}
                                  @input=${(e) =>
                                      this._setField(kind, 'voice', e.detail.value)}
                              ></glass-input>
                          </label>
                          <label>
                              ${this.t(
                                  'company_voice_providers_page.field_response_format',
                              )}
                              <select
                                  .value=${draft.response_format}
                                  @change=${(e) =>
                                      this._setField(
                                          kind,
                                          'response_format',
                                          e.target.value,
                                      )}
                              >
                                  ${RESPONSE_FORMATS.map(
                                      (f) =>
                                          html`<option value=${f}>${f === ''
                                              ? this.t(
                                                    'company_voice_providers_page.option_default',
                                                )
                                              : f}</option>`,
                                  )}
                              </select>
                          </label>
                      `
                    : nothing}
                ${kind !== 'vad'
                    ? html`
                          <label>
                              ${this.t(
                                  'company_voice_providers_page.field_language',
                              )}
                              <glass-input
                                  .value=${draft.language}
                                  placeholder="ru-RU"
                                  @input=${(e) =>
                                      this._setField(
                                          kind,
                                          'language',
                                          e.detail.value,
                                      )}
                              ></glass-input>
                          </label>
                      `
                    : nothing}
                <label>
                    ${this.t('company_voice_providers_page.field_sample_rate')}
                    <glass-input
                        .value=${draft.sample_rate}
                        placeholder="16000"
                        @input=${(e) =>
                            this._setField(kind, 'sample_rate', e.detail.value)}
                    ></glass-input>
                </label>
                ${kind === 'vad'
                    ? html`
                          <label>
                              ${this.t(
                                  'company_voice_providers_page.field_threshold',
                              )}
                              <glass-input
                                  .value=${draft.threshold}
                                  placeholder="0.5"
                                  @input=${(e) =>
                                      this._setField(
                                          kind,
                                          'threshold',
                                          e.detail.value,
                                      )}
                              ></glass-input>
                          </label>
                      `
                    : nothing}
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
