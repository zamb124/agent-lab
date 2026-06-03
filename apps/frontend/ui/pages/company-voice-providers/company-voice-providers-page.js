/**
 * Провайдеры речи компании — две вкладки:
 *   • «Провайдеры» — per-company override STT/TTS
 *   • «Произношение» — правила подмены слов перед TTS
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';

// ─── Voice providers constants ────────────────────────────────────────────────
const KINDS = ['stt', 'tts'];
const STT_TTS_UI = ['litserve', 'cloud_ru', 'yandex', 'sber'];
const RESPONSE_FORMATS = ['', 'wav', 'mp3', 'ogg', 'pcm', 'lpcm'];

function _emptySecretsDraft() {
    return { api_key: '', folder_id: '', client_id: '', client_secret: '', scope: '' };
}

function _emptyProviderDraft() {
    return {
        provider: '', model: '', voice: '', language: '',
        sample_rate: '', threshold: '', response_format: '',
        secrets: _emptySecretsDraft(),
    };
}

function _trimOrEmpty(v) {
    if (typeof v !== 'string') return '';
    return v.trim();
}

function _needsModel(provider) {
    return provider === 'litserve' || provider === 'cloud_ru'
        || provider === 'yandex' || provider === 'sber';
}

function _needsCredentials(provider) {
    return provider === 'cloud_ru' || provider === 'yandex' || provider === 'sber';
}

function _itemToDraft(item) {
    if (!item || typeof item !== 'object') return _emptyProviderDraft();
    const secrets = _emptySecretsDraft();
    const sm = item.secrets_meta;
    if (sm && typeof sm === 'object') {
        if (typeof sm.folder_id === 'string') secrets.folder_id = sm.folder_id;
        if (typeof sm.client_id === 'string') secrets.client_id = sm.client_id;
        if (typeof sm.scope === 'string') secrets.scope = sm.scope;
    }
    return {
        provider: typeof item.provider === 'string' ? item.provider : '',
        model:    typeof item.model === 'string' ? item.model : '',
        voice:    typeof item.voice === 'string' ? item.voice : '',
        language: typeof item.language === 'string' ? item.language : '',
        sample_rate:     typeof item.sample_rate === 'number' ? String(item.sample_rate) : '',
        threshold:       typeof item.threshold === 'number' ? String(item.threshold) : '',
        response_format: typeof item.response_format === 'string' ? item.response_format : '',
        secrets,
    };
}

// ─── Pronunciation constants ──────────────────────────────────────────────────
const KIND_OPTIONS = [
    { value: 'alias',  label: 'Алиас' },
    { value: 'regex',  label: 'Regex' },
    { value: 'stress', label: 'Ударение (+)' },
];

const PROVIDER_OPTIONS = [
    { value: 'litserve', label: 'Humanitec Voice' },
    { value: 'cloud_ru', label: 'Cloud.ru' },
    { value: 'yandex',   label: 'Yandex SpeechKit' },
    { value: 'sber',     label: 'Sber SmartSpeech' },
    { value: 'mock',     label: 'Mock (тесты)' },
];

const KIND_ICON  = { alias: 'edit', regex: 'settings', stress: 'microphone' };
const KIND_CLASS = { alias: 'kind-alias', regex: 'kind-regex', stress: 'kind-stress' };

function _emptyRuleDraft() {
    return {
        kind: 'alias', pattern: '', replacement: '',
        language: 'ru', case_sensitive: false,
        word_boundary: true, enabled: true, note: '',
    };
}

// ─── Page ─────────────────────────────────────────────────────────────────────
class FrontendCompanyVoiceProvidersPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static styles = [
        frontendIslandPageBodyStyles,
        css`
            :host { display: block; }

            /* Вкладки */
            .tabs {
                display: flex;
                gap: 0;
                border-bottom: 2px solid var(--glass-border-subtle);
                margin-bottom: var(--space-5);
            }

            .tab-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-5);
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                margin-bottom: -2px;
                cursor: pointer;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                transition: color 0.15s, border-color 0.15s;
                border-radius: var(--radius-md) var(--radius-md) 0 0;
            }

            .tab-btn:hover { color: var(--text-primary); }

            .tab-btn.active {
                color: var(--accent);
                border-bottom-color: var(--accent);
                font-weight: var(--font-semibold);
            }

            /* Карточки voice-провайдеров */
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
            }

            .card {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .card h3 { margin: 0; color: var(--text-primary); font-size: var(--text-base); }
            .card h4 { margin: 0; color: var(--text-secondary); font-size: var(--text-xs); }

            .hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .row {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
            }

            /* Произношение */
            .pron-card {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-5);
                margin-bottom: var(--space-4);
            }

            .pron-card-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .pron-card-title .count {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
            }

            .fields-grid {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .fields-grid.two-col { grid-template-columns: 1fr 1fr; }

            .toggles-row {
                display: flex;
                gap: var(--space-6);
                margin-bottom: var(--space-4);
                flex-wrap: wrap;
            }

            .actions-row { display: flex; gap: var(--space-2); }

            /* Список правил */
            .rules-list { display: flex; flex-direction: column; gap: var(--space-2); }

            .rule-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: background 0.12s;
            }

            .rule-item:hover { background: var(--glass-solid-strong); }
            .rule-item.rule-disabled { opacity: 0.45; }
            .rule-item.rule-editing { border-color: var(--accent); }

            .kind-badge {
                display: inline-flex;
                align-items: center;
                gap: 3px;
                padding: 3px 8px;
                border-radius: var(--radius-md);
                font-size: 11px;
                font-weight: var(--font-semibold);
                flex-shrink: 0;
                min-width: 76px;
            }

            .kind-alias  { background: #dbeafe; color: #1e40af; }
            .kind-regex  { background: #fef3c7; color: #92400e; }
            .kind-stress { background: #d1fae5; color: #065f46; }

            .rule-mono {
                font-family: monospace;
                font-size: var(--text-sm);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
            }

            .rule-pattern     { color: var(--text-secondary); background: var(--glass-solid-medium); }
            .rule-replacement { color: var(--text-primary); font-weight: var(--font-medium); }
            .rule-arrow       { color: var(--text-tertiary); flex-shrink: 0; }

            .rule-lang {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
                background: var(--glass-solid-medium);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
            }

            .rule-actions {
                display: flex;
                gap: var(--space-1);
                flex-shrink: 0;
                margin-left: auto;
            }

            .empty-state {
                text-align: center;
                padding: var(--space-8) var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            /* Секция тестирования */
            .test-result {
                margin-top: var(--space-4);
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
            }

            .test-result.result-changed { border-color: #22c55e; background: #f0fdf4; }

            .result-block { margin-bottom: var(--space-3); }
            .result-block:last-child { margin-bottom: 0; }

            .result-label {
                font-size: 11px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .result-code {
                font-family: monospace;
                font-size: var(--text-sm);
                color: var(--text-primary);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                border-radius: var(--radius-md);
                white-space: pre-wrap;
                word-break: break-all;
                border: 1px solid var(--glass-border-subtle);
            }

            .no-change-note {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
        `,
    ];

    static properties = {
        // общие
        _activeTab: { state: true },
        // черновики
        _drafts: { state: true },
        _credEditedByKind: { state: true },
        // произношение
        _ruleDraft: { state: true },
        _ruleEditId: { state: true },
        _testText: { state: true },
        _testProvider: { state: true },
        _testResult: { state: true },
    };

    constructor() {
        super();
        // ── Voice providers ops ──────────────────────────────────────
        this._catalog = this.useOp('frontend/voice_providers_catalog_load');
        this._load    = this.useOp('frontend/company_voice_providers_load');
        this._upsert  = this.useOp('frontend/company_voice_providers_upsert');
        this._remove  = this.useOp('frontend/company_voice_providers_remove');
        // ── Pronunciation ops ─────────────────────────────────────────
        this._rulesLoad   = this.useOp('frontend/company_pronunciation_rules_load');
        this._rulesCreate = this.useOp('frontend/company_pronunciation_rule_create');
        this._rulesUpdate = this.useOp('frontend/company_pronunciation_rule_update');
        this._rulesDelete = this.useOp('frontend/company_pronunciation_rule_delete');
        this._rulesTest   = this.useOp('frontend/company_pronunciation_rule_test');
        // ── Auth ──────────────────────────────────────────────────────
        this._auth = this.select(s => s.auth);
        // ── Реактивное состояние ──────────────────────────────────────
        this._activeTab        = 'providers';
        this._drafts           = { stt: _emptyProviderDraft(), tts: _emptyProviderDraft() };
        this._credEditedByKind = { stt: false, tts: false };
        this._ruleDraft        = _emptyRuleDraft();
        this._ruleEditId       = null;
        this._testText         = '';
        this._testProvider     = 'litserve';
        this._testResult       = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._reloadAll();
    }

    _activeCompanyId() {
        const auth = this._auth.value;
        if (!auth) return null;
        const cid = auth.activeCompanyId;
        if (typeof cid !== 'string' || cid.length === 0) return null;
        return cid;
    }

    async _reloadAll() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await Promise.all([
            this._catalog.run({}),
            this._load.run({ company_id }),
            this._rulesLoad.run({ company_id }),
        ]);
        const result = this._load.lastResult;
        if (result && Array.isArray(result.items)) {
            const drafts = { stt: _emptyProviderDraft(), tts: _emptyProviderDraft() };
            for (const item of result.items) {
                if (typeof item.kind === 'string') drafts[item.kind] = _itemToDraft(item);
            }
            this._drafts = drafts;
        }
        this._credEditedByKind = { stt: false, tts: false };
    }

    async _reloadRules() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await this._rulesLoad.run({ company_id });
    }

    // ── Voice providers helpers ──────────────────────────────────────────────

    _secretsMetaForKind(kind) {
        const r = this._load.lastResult;
        if (!r || !Array.isArray(r.items)) return null;
        for (const it of r.items) {
            if (it && it.kind === kind && it.secrets_meta) return it.secrets_meta;
        }
        return null;
    }

    _setField(kind, field, value) {
        const base = this._drafts[kind];
        let nextDraft;
        if (field === 'provider') {
            nextDraft = { ...base, provider: value, secrets: _emptySecretsDraft() };
            this._credEditedByKind = { ...this._credEditedByKind, [kind]: false };
        } else {
            nextDraft = { ...base, [field]: value };
        }
        this._drafts = { ...this._drafts, [kind]: nextDraft };
    }

    _setSecret(kind, field, value) {
        const sec = { ...this._drafts[kind].secrets, [field]: value };
        this._drafts = { ...this._drafts, [kind]: { ...this._drafts[kind], secrets: sec } };
        this._credEditedByKind = { ...this._credEditedByKind, [kind]: true };
    }

    _modelOptions(kind, provider) {
        const catalog = this._catalog.lastResult;
        if (!catalog) return [];
        if (provider === 'litserve') return kind === 'stt' ? [...catalog.stt_litserve_models] : [...catalog.tts_litserve_models];
        if (provider === 'cloud_ru')  return kind === 'stt' ? [...catalog.cloud_ru_stt_models] : [...catalog.cloud_ru_tts_models];
        if (provider === 'yandex')    return [...catalog.yandex_speech_models];
        if (provider === 'sber')      return [...catalog.sber_speech_models];
        return [];
    }

    _secretsPayload(kind, provider) {
        const s = this._drafts[kind].secrets;
        if (provider === 'cloud_ru') {
            const ak = _trimOrEmpty(s.api_key);
            return { api_key: ak !== '' ? ak : null };
        }
        if (provider === 'yandex') {
            const ak = _trimOrEmpty(s.api_key);
            const fd = _trimOrEmpty(s.folder_id);
            return { api_key: ak !== '' ? ak : null, folder_id: fd !== '' ? fd : null };
        }
        if (provider === 'sber') {
            const ci = _trimOrEmpty(s.client_id);
            const cs = _trimOrEmpty(s.client_secret);
            const sc = _trimOrEmpty(s.scope);
            return { client_id: ci !== '' ? ci : null, client_secret: cs !== '' ? cs : null, scope: sc !== '' ? sc : null };
        }
        return {};
    }

    async _saveProvider(kind) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const draft = this._drafts[kind];
        if (typeof draft.provider !== 'string' || draft.provider.length === 0) {
            this.toast('frontend:company_voice_providers_page.err_provider_required', { type: 'error' });
            return;
        }
        let sample_rate = null;
        const srTxt = _trimOrEmpty(draft.sample_rate);
        if (srTxt !== '') {
            const sr = Number(srTxt);
            if (!Number.isFinite(sr)) {
                this.toast('frontend:company_voice_providers_page.err_sample_rate_nan', { type: 'error' });
                return;
            }
            sample_rate = sr;
        }
        let threshold = null;
        const thTxt = _trimOrEmpty(draft.threshold);
        if (thTxt !== '') {
            const th = Number(thTxt);
            if (!Number.isFinite(th)) {
                this.toast('frontend:company_voice_providers_page.err_threshold_nan', { type: 'error' });
                return;
            }
            threshold = th;
        }
        const modelTrim = _trimOrEmpty(draft.model);
        const voiceTrim = _trimOrEmpty(draft.voice);
        const langTrim  = _trimOrEmpty(draft.language);
        const rfTrim    = _trimOrEmpty(draft.response_format);
        const payload = {
            company_id,
            kind,
            provider:        draft.provider,
            model:           modelTrim !== '' ? modelTrim : null,
            voice:           voiceTrim !== '' ? voiceTrim : null,
            language:        langTrim  !== '' ? langTrim  : null,
            sample_rate,
            threshold,
            response_format: rfTrim    !== '' ? rfTrim    : null,
        };
        if (this._credEditedByKind[kind] && _needsCredentials(draft.provider)) {
            payload.secrets = this._secretsPayload(kind, draft.provider);
        }
        await this._upsert.run(payload);
        await this._reloadAll();
    }

    async _resetProvider(kind) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await this._remove.run({ company_id, kind });
        this._drafts = { ...this._drafts, [kind]: _emptyProviderDraft() };
        this._credEditedByKind = { ...this._credEditedByKind, [kind]: false };
        await this._reloadAll();
    }

    // ── Pronunciation helpers ────────────────────────────────────────────────

    _getRules() {
        const result = this._rulesLoad.lastResult;
        if (!result || !Array.isArray(result.items)) return [];
        return result.items;
    }

    _setRuleDraft(field, value) {
        this._ruleDraft = { ...this._ruleDraft, [field]: value };
    }

    _startEditRule(item) {
        this._ruleEditId = item.id;
        this._ruleDraft = {
            kind:           item.kind,
            pattern:        item.pattern,
            replacement:    item.replacement,
            language:       typeof item.language === 'string' ? item.language : '',
            case_sensitive: item.case_sensitive === true,
            word_boundary:  item.word_boundary !== false,
            enabled:        item.enabled !== false,
            note:           typeof item.note === 'string' ? item.note : '',
        };
    }

    _cancelEditRule() {
        this._ruleEditId = null;
        this._ruleDraft = _emptyRuleDraft();
    }

    async _saveRule() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const pattern     = this._ruleDraft.pattern.trim();
        const replacement = this._ruleDraft.replacement.trim();
        if (!pattern || !replacement) return;

        const lang = this._ruleDraft.language.trim();
        const note = this._ruleDraft.note.trim();
        const base = {
            company_id,
            kind:           this._ruleDraft.kind,
            pattern,
            replacement,
            language:       lang.length > 0 ? lang : null,
            case_sensitive: this._ruleDraft.case_sensitive,
            word_boundary:  this._ruleDraft.word_boundary,
            enabled:        this._ruleDraft.enabled,
            note:           note.length > 0 ? note : null,
        };
        const result = this._ruleEditId
            ? await this._rulesUpdate.run({ ...base, rule_id: this._ruleEditId })
            : await this._rulesCreate.run(base);
        if (result) {
            this._ruleEditId = null;
            this._ruleDraft = _emptyRuleDraft();
            await this._reloadRules();
        }
    }

    async _deleteRule(ruleId) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const result = await this._rulesDelete.run({ company_id, rule_id: ruleId });
        if (result) {
            if (this._ruleEditId === ruleId) {
                this._ruleEditId = null;
                this._ruleDraft = _emptyRuleDraft();
            }
            await this._reloadRules();
        }
    }

    async _runTest() {
        const company_id = this._activeCompanyId();
        if (!company_id || !this._testText) return;
        this._testResult = null;
        const result = await this._rulesTest.run({
            company_id,
            text:     this._testText,
            provider: this._testProvider,
        });
        if (result) this._testResult = result;
    }

    // ── Render ───────────────────────────────────────────────────────────────

    render() {
        const company_id = this._activeCompanyId();
        if (!company_id) {
            return html`
                <page-header .title=${this.t('company_voice_providers_page.title')}></page-header>
                <p>${this.t('company_voice_providers_page.empty_no_company')}</p>
            `;
        }
        return html`
            <page-header
                .title=${this.t('company_voice_providers_page.title')}
                .subtitle=${this.t('company_voice_providers_page.subtitle')}
            ></page-header>

            <div class="tabs">
                <button
                    class="tab-btn ${this._activeTab === 'providers' ? 'active' : ''}"
                    @click=${() => { this._activeTab = 'providers'; }}
                >
                    <platform-icon name="microphone" size="14"></platform-icon>
                    ${this.t('company_voice_providers_page.tab_providers')}
                </button>
                <button
                    class="tab-btn ${this._activeTab === 'pronunciation' ? 'active' : ''}"
                    @click=${() => { this._activeTab = 'pronunciation'; }}
                >
                    <platform-icon name="edit" size="14"></platform-icon>
                    ${this.t('company_voice_providers_page.tab_pronunciation')}
                    ${this._getRules().length > 0
                        ? html`<span style="font-size:11px;background:var(--accent-subtle);color:var(--accent);border-radius:99px;padding:1px 7px;font-weight:var(--font-semibold)">${this._getRules().length}</span>`
                        : nothing}
                </button>
            </div>

            ${this._activeTab === 'providers'
                ? this._renderProviders()
                : this._renderPronunciation()}
        `;
    }

    // ── Providers tab ─────────────────────────────────────────────────────────

    _renderProviders() {
        const loading = this._load.busy || this._catalog.busy;
        return loading
            ? html`<glass-spinner></glass-spinner>`
            : html`<div class="grid">${KINDS.map(k => this._renderProviderCard(k))}</div>`;
    }

    _renderProviderCard(kind) {
        const draft       = this._drafts[kind];
        const secretsMeta = this._secretsMetaForKind(kind);
        const busy        = this._upsert.busy || this._remove.busy;
        const providerValues = [
            { value: '', label: this.t('company_voice_providers_page.option_default') },
            ...STT_TTS_UI.map(p => ({ value: p, label: p })),
        ];
        const rfValues = RESPONSE_FORMATS.map(f => ({
            value: f,
            label: f === '' ? this.t('company_voice_providers_page.option_default') : f,
        }));
        const opts = this._modelOptions(kind, draft.provider);
        const modelValues = [
            { value: '', label: this.t('company_voice_providers_page.option_default') },
            ...opts.map(id => ({ value: id, label: id })),
        ];
        return html`
            <div class="card">
                <h3>${this.t(`company_voice_providers_page.title_${kind}`)}</h3>
                <platform-field
                    type="enum" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_provider')}
                    .value=${draft.provider}
                    .config=${{ values: providerValues }}
                    .hint=${this.t(`company_voice_providers_page.hint_${kind}`)}
                    @change=${e => this._setField(kind, 'provider', e.detail.value)}
                ></platform-field>
                ${_needsModel(draft.provider) && opts.length > 0 ? html`
                    <platform-field
                        type="enum" mode="edit"
                        .label=${this.t('company_voice_providers_page.field_model')}
                        .value=${draft.model}
                        .config=${{ values: modelValues }}
                        .hint=${draft.provider === 'litserve' ? this.t('company_voice_providers_page.model_default_litserve') : ''}
                        @change=${e => this._setField(kind, 'model', e.detail.value)}
                    ></platform-field>
                ` : nothing}
                ${kind === 'tts' ? html`
                    <platform-field type="string" mode="edit"
                        .label=${this.t('company_voice_providers_page.field_voice')}
                        .value=${draft.voice}
                        @change=${e => this._setField(kind, 'voice', e.detail.value)}
                    ></platform-field>
                    <platform-field type="enum" mode="edit"
                        .label=${this.t('company_voice_providers_page.field_response_format')}
                        .value=${draft.response_format}
                        .config=${{ values: rfValues }}
                        @change=${e => this._setField(kind, 'response_format', e.detail.value)}
                    ></platform-field>
                ` : nothing}
                <platform-field type="string" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_language')}
                    .value=${draft.language}
                    placeholder="ru-RU"
                    @change=${e => this._setField(kind, 'language', e.detail.value)}
                ></platform-field>
                <platform-field type="string" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_sample_rate')}
                    .value=${draft.sample_rate}
                    placeholder="16000"
                    @change=${e => this._setField(kind, 'sample_rate', e.detail.value)}
                ></platform-field>
                ${this._renderCredentials(kind, draft, secretsMeta)}
                <div class="row">
                    <glass-button variant="ghost" ?disabled=${busy}
                        @click=${() => this._resetProvider(kind)}
                    >${this.t('company_voice_providers_page.action_reset')}</glass-button>
                    <glass-button variant="primary" ?disabled=${busy}
                        @click=${() => this._saveProvider(kind)}
                    >${this.t('company_voice_providers_page.action_save')}</glass-button>
                </div>
            </div>
        `;
    }

    _renderCredentials(kind, draft, secretsMeta) {
        if (!_needsCredentials(draft.provider)) return nothing;
        const p = draft.provider;
        const set = secretsMeta;
        const placeholder = (flag) =>
            flag ? this.t('company_voice_providers_page.placeholder_secret_set') : '';
        return html`
            <h4>${this.t('company_voice_providers_page.credentials_heading')}</h4>
            ${p === 'cloud_ru' || p === 'yandex' ? html`
                <platform-field type="string" input-type="password" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_api_key')}
                    .value=${draft.secrets.api_key}
                    .placeholder=${placeholder(set && set.api_key_set)}
                    @change=${e => this._setSecret(kind, 'api_key', e.detail.value)}
                ></platform-field>
            ` : nothing}
            ${p === 'yandex' ? html`
                <platform-field type="string" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_folder_id')}
                    .value=${draft.secrets.folder_id}
                    @change=${e => this._setSecret(kind, 'folder_id', e.detail.value)}
                ></platform-field>
            ` : nothing}
            ${p === 'sber' ? html`
                <platform-field type="string" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_client_id')}
                    .value=${draft.secrets.client_id}
                    @change=${e => this._setSecret(kind, 'client_id', e.detail.value)}
                ></platform-field>
                <platform-field type="string" input-type="password" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_client_secret')}
                    .value=${draft.secrets.client_secret}
                    .placeholder=${placeholder(set && set.client_secret_set)}
                    @change=${e => this._setSecret(kind, 'client_secret', e.detail.value)}
                ></platform-field>
                <platform-field type="string" mode="edit"
                    .label=${this.t('company_voice_providers_page.field_scope')}
                    .value=${draft.secrets.scope}
                    @change=${e => this._setSecret(kind, 'scope', e.detail.value)}
                ></platform-field>
            ` : nothing}
        `;
    }

    // ── Pronunciation tab ─────────────────────────────────────────────────────

    _renderPronunciation() {
        return html`
            ${this._renderRuleForm()}
            ${this._renderRulesList()}
            ${this._renderTestSection()}
        `;
    }

    _renderRuleForm() {
        const d      = this._ruleDraft;
        const isEdit = Boolean(this._ruleEditId);
        const isBusy = this._rulesCreate.busy || this._rulesUpdate.busy;
        const canSave = d.pattern.trim().length > 0 && d.replacement.trim().length > 0 && !isBusy;

        return html`
            <div class="pron-card">
                <h3 class="pron-card-title">
                    <platform-icon name="${isEdit ? 'edit' : 'plus'}" size="16"></platform-icon>
                    ${isEdit
                        ? this.t('pronunciation_rules_page.form_edit')
                        : this.t('pronunciation_rules_page.form_add')}
                </h3>

                <div class="fields-grid">
                    <platform-field type="enum" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_kind')}"
                        .value=${d.kind}
                        .config=${{ values: KIND_OPTIONS }}
                        @change=${e => this._setRuleDraft('kind', e.detail.value)}
                    ></platform-field>
                    <platform-field type="string" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_pattern')}"
                        .value=${d.pattern}
                        placeholder="Хуманитик"
                        @change=${e => this._setRuleDraft('pattern', e.detail.value)}
                    ></platform-field>
                    <platform-field type="string" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_replacement')}"
                        .value=${d.replacement}
                        placeholder="хуманитэк"
                        @change=${e => this._setRuleDraft('replacement', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="fields-grid two-col">
                    <platform-field type="string" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_language')}"
                        .value=${d.language}
                        placeholder="ru"
                        .hint=${this.t('pronunciation_rules_page.hint_language')}
                        @change=${e => this._setRuleDraft('language', e.detail.value)}
                    ></platform-field>
                    <platform-field type="text" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_note')}"
                        .value=${d.note}
                        placeholder="${this.t('pronunciation_rules_page.placeholder_note')}"
                        @change=${e => this._setRuleDraft('note', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="toggles-row">
                    <platform-field type="boolean" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_word_boundary')}"
                        .value=${d.word_boundary}
                        .hint=${this.t('pronunciation_rules_page.hint_word_boundary')}
                        @change=${e => this._setRuleDraft('word_boundary', e.detail.value)}
                    ></platform-field>
                    <platform-field type="boolean" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_case_sensitive')}"
                        .value=${d.case_sensitive}
                        @change=${e => this._setRuleDraft('case_sensitive', e.detail.value)}
                    ></platform-field>
                    <platform-field type="boolean" mode="edit"
                        label="${this.t('pronunciation_rules_page.field_enabled')}"
                        .value=${d.enabled}
                        @change=${e => this._setRuleDraft('enabled', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="actions-row">
                    <glass-button ?disabled=${!canSave} @click=${this._saveRule}>
                        ${isBusy
                            ? html`<glass-spinner size="sm"></glass-spinner>`
                            : html`<platform-icon name="${isEdit ? 'check' : 'plus'}" size="14"></platform-icon>`}
                        ${isEdit
                            ? this.t('pronunciation_rules_page.btn_update')
                            : this.t('pronunciation_rules_page.btn_add')}
                    </glass-button>
                    ${isEdit ? html`
                        <glass-button variant="ghost" @click=${this._cancelEditRule}>
                            ${this.t('pronunciation_rules_page.btn_cancel')}
                        </glass-button>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _renderRulesList() {
        const rules      = this._getRules();
        const isLoading  = this._rulesLoad.busy;
        const isDeleting = this._rulesDelete.busy;
        return html`
            <div class="pron-card">
                <h3 class="pron-card-title">
                    <platform-icon name="database" size="16"></platform-icon>
                    ${this.t('pronunciation_rules_page.section_rules')}
                    ${rules.length > 0
                        ? html`<span class="count">(${rules.length})</span>`
                        : nothing}
                </h3>
                ${isLoading
                    ? html`<glass-spinner></glass-spinner>`
                    : rules.length === 0
                        ? html`
                            <div class="empty-state">
                                <div style="margin-bottom:var(--space-2)">
                                    <platform-icon name="microphone" size="28"></platform-icon>
                                </div>
                                ${this.t('pronunciation_rules_page.empty')}
                            </div>`
                        : html`
                            <div class="rules-list">
                                ${rules.map(r => this._renderRuleItem(r, isDeleting))}
                            </div>`}
            </div>
        `;
    }

    _renderRuleItem(item, isDeleting) {
        const isEditing = this._ruleEditId === item.id;
        return html`
            <div class="rule-item
                ${!item.enabled ? 'rule-disabled' : ''}
                ${isEditing ? 'rule-editing' : ''}
            ">
                <span class="kind-badge ${KIND_CLASS[item.kind] || 'kind-alias'}">
                    <platform-icon name="${KIND_ICON[item.kind] || 'edit'}" size="11"></platform-icon>
                    ${item.kind}
                </span>
                <span class="rule-mono rule-pattern">${item.pattern}</span>
                <span class="rule-arrow">→</span>
                <span class="rule-mono rule-replacement">${item.replacement}</span>
                ${item.language ? html`<span class="rule-lang">${item.language}</span>` : nothing}
                <span class="rule-actions">
                    <glass-button size="sm" variant="ghost"
                        title="${this.t('pronunciation_rules_page.btn_edit')}"
                        ?disabled=${Boolean(this._ruleEditId)}
                        @click=${() => this._startEditRule(item)}
                    ><platform-icon name="edit" size="14"></platform-icon></glass-button>
                    <glass-button size="sm" variant="ghost"
                        title="${this.t('pronunciation_rules_page.btn_delete')}"
                        ?disabled=${isDeleting}
                        @click=${() => this._deleteRule(item.id)}
                    ><platform-icon name="trash" size="14"></platform-icon></glass-button>
                </span>
            </div>
        `;
    }

    _renderTestSection() {
        const result = this._testResult;
        const isBusy = this._rulesTest.busy;
        return html`
            <div class="pron-card">
                <h3 class="pron-card-title">
                    <platform-icon name="settings" size="16"></platform-icon>
                    ${this.t('pronunciation_rules_page.test_title')}
                </h3>
                <div class="fields-grid two-col">
                    <platform-field type="text" mode="edit"
                        label="${this.t('pronunciation_rules_page.test_input')}"
                        .value=${this._testText}
                        placeholder="Хуманитик — платформа автоматизации"
                        @change=${e => { this._testText = e.detail.value; this._testResult = null; }}
                    ></platform-field>
                    <platform-field type="enum" mode="edit"
                        label="${this.t('pronunciation_rules_page.test_provider')}"
                        .value=${this._testProvider}
                        .config=${{ values: PROVIDER_OPTIONS }}
                        @change=${e => { this._testProvider = e.detail.value; this._testResult = null; }}
                    ></platform-field>
                </div>
                <glass-button ?disabled=${!this._testText || isBusy} @click=${this._runTest}>
                    ${isBusy
                        ? html`<glass-spinner size="sm"></glass-spinner>`
                        : html`<platform-icon name="check" size="14"></platform-icon>`}
                    ${this.t('pronunciation_rules_page.test_run')}
                </glass-button>
                ${result ? html`
                    <div class="test-result ${result.changed ? 'result-changed' : ''}">
                        <div class="result-block">
                            <div class="result-label">${this.t('pronunciation_rules_page.test_original')}</div>
                            <div class="result-code">${result.original}</div>
                        </div>
                        <div class="result-block">
                            <div class="result-label">${this.t('pronunciation_rules_page.test_transformed')}</div>
                            <div class="result-code">${result.transformed}</div>
                        </div>
                        ${!result.changed ? html`
                            <div class="no-change-note">
                                <platform-icon name="check" size="13"></platform-icon>
                                ${this.t('pronunciation_rules_page.test_no_change')}
                            </div>
                        ` : nothing}
                    </div>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('frontend-company-voice-providers-page', FrontendCompanyVoiceProvidersPage);
