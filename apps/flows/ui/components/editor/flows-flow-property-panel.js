/**
 * flows-flow-property-panel — лимиты flow и профиль речи (уровень flow / ветки).
 *
 * Показывается в правом столбе по кнопке в сайдбаре (`flows-node-types-sidebar`).
 * Не привязана к выбранной ноде.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { asObject } from '../../_helpers/flows-resolvers.js';

/** @param {string} provider */
function _needsSttTtsModel(provider) {
    return (
        provider === 'litserve' ||
        provider === 'cloud_ru' ||
        provider === 'yandex' ||
        provider === 'sber'
    );
}

const VAD_THRESHOLD_OPTS = Object.freeze(
    Array.from({ length: 21 }, (_, i) => (i * 0.05).toFixed(2)),
);

export class FlowsFlowPropertyPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String },
        branchId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                flex-shrink: 0;
                max-height: min(56vh, 520px);
                min-height: 0;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-xl);
                box-shadow: var(--glass-shadow-strong);
                overflow: hidden;
            }
            .card-inner {
                padding: var(--space-3) var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: inherit;
                overflow-y: auto;
                box-sizing: border-box;
            }
            .card-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                flex-shrink: 0;
            }
            .speech-field {
                display: flex;
                flex-direction: column;
                gap: 2px;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .speech-field select,
            .speech-field input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
            }
            .speech-subtitle {
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-top: var(--space-2);
            }
            .speech-actions {
                margin-top: var(--space-2);
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .speech-actions button {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .speech-actions button:hover {
                color: var(--text-primary);
                border-color: var(--border-medium);
            }
            .flow-timeout-input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .flow-timeout-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .flow-settings-heading {
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-1);
            }
            .flow-timeout-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .speech-catalog-pending {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
                padding: var(--space-2) 0;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._editor = this.useOp('flows/editor');
        this._voiceCatalog = this.useOp('flows/voice_providers_catalog_load');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._voiceCatalog
            .run({})
            .catch((err) => {
                const detail = err instanceof Error ? err.message : String(err);
                this.toast('flows:property_panel.speech_catalog_error', {
                    type: 'error',
                    vars: { detail },
                });
            })
            .finally(() => {
                this.requestUpdate();
            });
    }

    /**
     * @param {Record<string, unknown>|null|undefined} prevSpeech
     * @param {'stt'|'tts'|'vad'} block
     * @param {string} field
     * @param {unknown} value — null удаляет поле
     */
    _mergeSpeechBlock(prevSpeech, block, field, value) {
        const speech =
            prevSpeech && typeof prevSpeech === 'object' && !Array.isArray(prevSpeech)
                ? { ...prevSpeech }
                : {};
        const prevBlock =
            speech[block] && typeof speech[block] === 'object' && !Array.isArray(speech[block])
                ? { ...speech[block] }
                : {};
        const nextBlock = { ...prevBlock };
        if (value === null || value === undefined || value === '') {
            delete nextBlock[field];
        } else {
            nextBlock[field] = value;
        }
        if (Object.keys(nextBlock).length === 0) {
            delete speech[block];
        } else {
            speech[block] = nextBlock;
        }
        return Object.keys(speech).length === 0 ? null : speech;
    }

    _commitFlowSpeech(block, field, value) {
        const fc = asObject(this._editor.state).flowConfig;
        const prev = fc && fc.speech && typeof fc.speech === 'object' ? fc.speech : null;
        const next = this._mergeSpeechBlock(prev, block, field, value);
        this._editor.patchFlowConfig({ patch: { speech: next } });
    }

    _commitBranchSpeech(branchKey, block, field, value) {
        const fc = asObject(this._editor.state).flowConfig;
        const branchesIn =
            fc && fc.branches && typeof fc.branches === 'object' && !Array.isArray(fc.branches)
                ? fc.branches
                : {};
        const branches = { ...branchesIn };
        const rawBranch = branches[branchKey];
        if (!rawBranch || typeof rawBranch !== 'object' || Array.isArray(rawBranch)) {
            throw new Error('flows-flow-property-panel: branch config missing for speech patch');
        }
        const prevBranch = { ...rawBranch };
        const prevSpeech =
            prevBranch.speech && typeof prevBranch.speech === 'object' ? prevBranch.speech : null;
        const nextSpeech = this._mergeSpeechBlock(prevSpeech, block, field, value);
        const nextBranch = { ...prevBranch };
        if (nextSpeech === null) {
            delete nextBranch.speech;
        } else {
            nextBranch.speech = nextSpeech;
        }
        branches[branchKey] = nextBranch;
        this._editor.patchFlowConfig({ patch: { branches } });
    }

    _clearFlowSpeech() {
        this._editor.patchFlowConfig({ patch: { speech: null } });
    }

    _clearBranchSpeech(branchKey) {
        const fc = asObject(this._editor.state).flowConfig;
        const branchesIn =
            fc && fc.branches && typeof fc.branches === 'object' && !Array.isArray(fc.branches)
                ? fc.branches
                : {};
        const branches = { ...branchesIn };
        const rawBranch = branches[branchKey];
        if (!rawBranch || typeof rawBranch !== 'object' || Array.isArray(rawBranch)) {
            throw new Error('flows-flow-property-panel: branch config missing for speech clear');
        }
        const prevBranch = { ...rawBranch };
        delete prevBranch.speech;
        branches[branchKey] = prevBranch;
        this._editor.patchFlowConfig({ patch: { branches } });
    }

    _modelOptions(kind, provider, catalog) {
        if (!_needsSttTtsModel(provider)) {
            return [];
        }
        if (!catalog || typeof catalog !== 'object') {
            return [];
        }
        if (provider === 'litserve') {
            if (kind === 'stt') {
                return [...catalog.stt_litserve_models];
            }
            return [...catalog.tts_litserve_models];
        }
        if (provider === 'cloud_ru') {
            if (kind === 'stt') {
                return [...catalog.cloud_ru_stt_models];
            }
            return [...catalog.cloud_ru_tts_models];
        }
        if (provider === 'yandex') {
            return [...catalog.yandex_speech_models];
        }
        if (provider === 'sber') {
            return [...catalog.sber_speech_models];
        }
        return [];
    }

    _renderModelSelect(kind, provider, catalog, currentModel, onPick) {
        const opts = this._modelOptions(kind, provider, catalog);
        if (opts.length === 0) {
            return nothing;
        }
        return html`
            <label class="speech-field">
                ${this.t('property_panel.speech_field_model')}
                <select .value=${currentModel} @change=${onPick}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${opts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
        `;
    }

    /** @param {unknown} catalog */
    _speechLanguageIds(catalog) {
        if (!catalog || typeof catalog !== 'object' || !Array.isArray(catalog.speech_language_ids)) {
            return [];
        }
        return [...catalog.speech_language_ids];
    }

    /** @param {unknown} catalog */
    _ttsVoiceIds(ttsProv, ttsModel, catalog) {
        if (!catalog || typeof catalog !== 'object') return [];
        if (ttsProv === 'litserve') {
            const hints = catalog.tts_litserve_voice_hints;
            if (!Array.isArray(hints) || typeof ttsModel !== 'string' || ttsModel === '') return [];
            const h = hints.find((x) => x && x.api_model_id === ttsModel);
            if (!h || !Array.isArray(h.voice_ids)) return [];
            return [...h.voice_ids];
        }
        if (ttsProv === 'cloud_ru' && Array.isArray(catalog.cloud_ru_tts_voice_ids)) {
            return [...catalog.cloud_ru_tts_voice_ids];
        }
        if (ttsProv === 'yandex' && Array.isArray(catalog.yandex_tts_voice_ids)) {
            return [...catalog.yandex_tts_voice_ids];
        }
        if (ttsProv === 'sber' && Array.isArray(catalog.sber_tts_voice_ids)) {
            return [...catalog.sber_tts_voice_ids];
        }
        return [];
    }

    /** @param {unknown} catalog */
    _ttsSampleRateInts(ttsProv, catalog) {
        if (!catalog || typeof catalog !== 'object') return [];
        if (ttsProv === 'litserve' && Array.isArray(catalog.litserve_silero_tts_sample_rate_ids)) {
            return [...catalog.litserve_silero_tts_sample_rate_ids];
        }
        if (Array.isArray(catalog.tts_sample_rate_ids)) {
            return [...catalog.tts_sample_rate_ids];
        }
        return [];
    }

    /** @param {unknown} catalog */
    _vadSampleRateInts(catalog) {
        if (!catalog || typeof catalog !== 'object' || !Array.isArray(catalog.vad_sample_rate_ids)) {
            return [];
        }
        return [...catalog.vad_sample_rate_ids];
    }

    /** @param {unknown} catalog */
    _vadProviderIds(catalog) {
        if (!catalog || typeof catalog !== 'object' || !Array.isArray(catalog.vad_provider_ids)) {
            return [];
        }
        return [...catalog.vad_provider_ids];
    }

    _mergeStringOption(sortedBase, current) {
        if (typeof current !== 'string' || current === '') return [...sortedBase];
        const base = [...sortedBase];
        if (base.includes(current)) return base.sort();
        base.push(current);
        return base.sort();
    }

    _mergeIntOption(sortedBase, current) {
        const base = [...sortedBase];
        if (typeof current !== 'number' || !Number.isFinite(current)) return base.sort((a, b) => a - b);
        if (base.includes(current)) return base.sort((a, b) => a - b);
        base.push(current);
        return base.sort((a, b) => a - b);
    }

    _mergeThresholdOpts(currentNum) {
        const cur =
            typeof currentNum === 'number' && Number.isFinite(currentNum)
                ? currentNum.toFixed(2)
                : '';
        const opts = [...VAD_THRESHOLD_OPTS];
        if (cur !== '' && !opts.includes(cur)) {
            opts.push(cur);
            opts.sort((a, b) => Number(a) - Number(b));
        }
        return { opts, cur };
    }

    _renderSpeechStringSelect(labelKey, sortedIds, currentStr, emptyLabelKey, onChange) {
        const cur = typeof currentStr === 'string' ? currentStr : '';
        const ids = this._mergeStringOption(sortedIds, cur);
        if (ids.length === 0) return nothing;
        return html`
            <label class="speech-field">
                ${this.t(labelKey)}
                <select .value=${cur} @change=${onChange}>
                    <option value="">${this.t(emptyLabelKey)}</option>
                    ${ids.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
        `;
    }

    _renderSpeechIntSelect(labelKey, sortedInts, currentNum, emptyLabelKey, onChange) {
        const ints = this._mergeIntOption(sortedInts, typeof currentNum === 'number' ? currentNum : NaN);
        if (ints.length === 0) return nothing;
        const curStr =
            typeof currentNum === 'number' && Number.isFinite(currentNum) ? String(currentNum) : '';
        return html`
            <label class="speech-field">
                ${this.t(labelKey)}
                <select .value=${curStr} @change=${onChange}>
                    <option value="">${this.t(emptyLabelKey)}</option>
                    ${ints.map((n) => html`<option value=${String(n)}>${n}</option>`)}
                </select>
            </label>
        `;
    }

    _renderVadThresholdSelect(currentNum, onChange) {
        const { opts, cur } = this._mergeThresholdOpts(
            typeof currentNum === 'number' ? currentNum : NaN,
        );
        return html`
            <label class="speech-field">
                ${this.t('property_panel.speech_field_vad_threshold')}
                <select .value=${cur} @change=${onChange}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${opts.map((v) => html`<option value=${v}>${v}</option>`)}
                </select>
            </label>
        `;
    }

    /**
     * @param {'flow'|'branch'} scope
     * @param {string} [branchKey]
     */
    _speechHandlers(scope, branchKey) {
        const commit =
            scope === 'flow'
                ? (block, field, value) => this._commitFlowSpeech(block, field, value)
                : (block, field, value) => this._commitBranchSpeech(branchKey ?? '', block, field, value);
        return {
            provider: (block) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                commit(block, 'provider', t === '' ? null : t);
                commit(block, 'model', null);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                    commit(block, 'sample_rate', null);
                }
            },
            modelSelect: (block) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                commit(block, 'model', t === '' ? null : t);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                }
            },
            enumSelect: (block, field) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                commit(block, field, t === '' ? null : t);
            },
            intSelect: (block, field) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                if (t === '') {
                    commit(block, field, null);
                    return;
                }
                const n = parseInt(t, 10);
                if (!Number.isFinite(n)) {
                    this.toast('flows:property_panel.speech_invalid_number', { type: 'error' });
                    return;
                }
                commit(block, field, n);
            },
            vadThresholdSelect: () => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                if (t === '') {
                    commit('vad', 'threshold', null);
                    return;
                }
                const n = Number(t);
                if (!Number.isFinite(n)) {
                    this.toast('flows:property_panel.speech_invalid_number', { type: 'error' });
                    return;
                }
                commit('vad', 'threshold', n);
            },
            responseFormat: (block) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                commit(block, 'response_format', t === '' ? null : t);
            },
            vadProvider: (block) => (e) => {
                const raw = e.target.value;
                const t = typeof raw === 'string' ? raw.trim() : '';
                commit(block, 'provider', t === '' ? null : t);
            },
        };
    }

    _renderFlowSpeechSettingsInner(catalog, speech) {
        const stt = speech && typeof speech.stt === 'object' ? speech.stt : {};
        const tts = speech && typeof speech.tts === 'object' ? speech.tts : {};
        const vad = speech && typeof speech.vad === 'object' ? speech.vad : {};
        const provOpts =
            catalog && Array.isArray(catalog.stt_tts_provider_ids)
                ? catalog.stt_tts_provider_ids
                : [];
        const rfOpts =
            catalog && Array.isArray(catalog.response_format_ids)
                ? catalog.response_format_ids
                : [];
        const langOpts = this._speechLanguageIds(catalog);
        const sttProv = typeof stt.provider === 'string' ? stt.provider : '';
        const ttsProv = typeof tts.provider === 'string' ? tts.provider : '';
        const vadProv = typeof vad.provider === 'string' ? vad.provider : '';
        const sttModel = typeof stt.model === 'string' ? stt.model : '';
        const ttsModel = typeof tts.model === 'string' ? tts.model : '';
        const voiceOpts = this._ttsVoiceIds(ttsProv, ttsModel, catalog);
        const ttsSrOpts = this._ttsSampleRateInts(ttsProv, catalog);
        const vadSrOpts = this._vadSampleRateInts(catalog);
        const vadProvOpts = this._vadProviderIds(catalog);
        const h = this._speechHandlers('flow');
        return html`
            <div class="speech-subtitle">${this.t('property_panel.speech_section_stt')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${sttProv} @change=${h.provider('stt')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${provOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${_needsSttTtsModel(sttProv)
                ? this._renderModelSelect(
                      'stt',
                      sttProv,
                      catalog,
                      sttModel,
                      h.modelSelect('stt'),
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof stt.language === 'string' ? stt.language : '',
                'property_panel.speech_option_inherit_empty',
                h.enumSelect('stt', 'language'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_tts')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${ttsProv} @change=${h.provider('tts')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${provOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${_needsSttTtsModel(ttsProv)
                ? this._renderModelSelect(
                      'tts',
                      ttsProv,
                      catalog,
                      ttsModel,
                      h.modelSelect('tts'),
                  )
                : nothing}
            ${voiceOpts.length > 0
                ? this._renderSpeechStringSelect(
                      'property_panel.speech_field_voice',
                      voiceOpts,
                      typeof tts.voice === 'string' ? tts.voice : '',
                      'property_panel.speech_option_inherit_empty',
                      h.enumSelect('tts', 'voice'),
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof tts.language === 'string' ? tts.language : '',
                'property_panel.speech_option_inherit_empty',
                h.enumSelect('tts', 'language'),
            )}
            <label class="speech-field">
                ${this.t('property_panel.speech_field_response_format')}
                <select .value=${typeof tts.response_format === 'string' ? tts.response_format : ''} @change=${h.responseFormat('tts')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${rfOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                ttsSrOpts,
                typeof tts.sample_rate === 'number' ? tts.sample_rate : NaN,
                'property_panel.speech_option_inherit_empty',
                h.intSelect('tts', 'sample_rate'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${vadProv} @change=${h.vadProvider('vad')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_empty')}</option>
                    ${vadProvOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                vadSrOpts,
                typeof vad.sample_rate === 'number' ? vad.sample_rate : NaN,
                'property_panel.speech_option_inherit_empty',
                h.intSelect('vad', 'sample_rate'),
            )}
            ${this._renderVadThresholdSelect(
                typeof vad.threshold === 'number' ? vad.threshold : NaN,
                h.vadThresholdSelect(),
            )}
            <div class="speech-actions">
                <button type="button" @click=${() => this._clearFlowSpeech()}>
                    ${this.t('property_panel.speech_clear_flow')}
                </button>
            </div>
        `;
    }

    _renderBranchSpeechSettingsInner(catalog, speech, branchKey) {
        const stt = speech && typeof speech.stt === 'object' ? speech.stt : {};
        const tts = speech && typeof speech.tts === 'object' ? speech.tts : {};
        const vad = speech && typeof speech.vad === 'object' ? speech.vad : {};
        const provOpts =
            catalog && Array.isArray(catalog.stt_tts_provider_ids)
                ? catalog.stt_tts_provider_ids
                : [];
        const rfOpts =
            catalog && Array.isArray(catalog.response_format_ids)
                ? catalog.response_format_ids
                : [];
        const langOpts = this._speechLanguageIds(catalog);
        const sttProv = typeof stt.provider === 'string' ? stt.provider : '';
        const ttsProv = typeof tts.provider === 'string' ? tts.provider : '';
        const vadProv = typeof vad.provider === 'string' ? vad.provider : '';
        const sttModel = typeof stt.model === 'string' ? stt.model : '';
        const ttsModel = typeof tts.model === 'string' ? tts.model : '';
        const voiceOpts = this._ttsVoiceIds(ttsProv, ttsModel, catalog);
        const ttsSrOpts = this._ttsSampleRateInts(ttsProv, catalog);
        const vadSrOpts = this._vadSampleRateInts(catalog);
        const vadProvOpts = this._vadProviderIds(catalog);
        const h = this._speechHandlers('branch', branchKey);
        return html`
            <div style="font-weight: var(--font-semibold); margin-top: var(--space-3);">${this.t(
                'property_panel.speech_branch_title',
            )}</div>
            <div style="font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.4;">
                ${this.t('property_panel.speech_branch_hint')}
            </div>
            <div class="speech-subtitle">${this.t('property_panel.speech_section_stt')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${sttProv} @change=${h.provider('stt')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_flow')}</option>
                    ${provOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${_needsSttTtsModel(sttProv)
                ? this._renderModelSelect(
                      'stt',
                      sttProv,
                      catalog,
                      sttModel,
                      h.modelSelect('stt'),
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof stt.language === 'string' ? stt.language : '',
                'property_panel.speech_option_inherit_flow',
                h.enumSelect('stt', 'language'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_tts')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${ttsProv} @change=${h.provider('tts')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_flow')}</option>
                    ${provOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${_needsSttTtsModel(ttsProv)
                ? this._renderModelSelect(
                      'tts',
                      ttsProv,
                      catalog,
                      ttsModel,
                      h.modelSelect('tts'),
                  )
                : nothing}
            ${voiceOpts.length > 0
                ? this._renderSpeechStringSelect(
                      'property_panel.speech_field_voice',
                      voiceOpts,
                      typeof tts.voice === 'string' ? tts.voice : '',
                      'property_panel.speech_option_inherit_flow',
                      h.enumSelect('tts', 'voice'),
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof tts.language === 'string' ? tts.language : '',
                'property_panel.speech_option_inherit_flow',
                h.enumSelect('tts', 'language'),
            )}
            <label class="speech-field">
                ${this.t('property_panel.speech_field_response_format')}
                <select .value=${typeof tts.response_format === 'string' ? tts.response_format : ''} @change=${h.responseFormat('tts')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_flow')}</option>
                    ${rfOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                ttsSrOpts,
                typeof tts.sample_rate === 'number' ? tts.sample_rate : NaN,
                'property_panel.speech_option_inherit_flow',
                h.intSelect('tts', 'sample_rate'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <label class="speech-field">
                ${this.t('property_panel.speech_field_provider')}
                <select .value=${vadProv} @change=${h.vadProvider('vad')}>
                    <option value="">${this.t('property_panel.speech_option_inherit_flow')}</option>
                    ${vadProvOpts.map((id) => html`<option value=${id}>${id}</option>`)}
                </select>
            </label>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                vadSrOpts,
                typeof vad.sample_rate === 'number' ? vad.sample_rate : NaN,
                'property_panel.speech_option_inherit_flow',
                h.intSelect('vad', 'sample_rate'),
            )}
            ${this._renderVadThresholdSelect(
                typeof vad.threshold === 'number' ? vad.threshold : NaN,
                h.vadThresholdSelect(),
            )}
            <div class="speech-actions">
                <button type="button" @click=${() => this._clearBranchSpeech(branchKey)}>
                    ${this.t('property_panel.speech_clear_branch')}
                </button>
            </div>
        `;
    }

    _renderSpeechSettings() {
        const catalog = this._voiceCatalog.lastResult;
        const state = asObject(this._editor.state);
        const fc = state.flowConfig;
        const flowSpeech = fc && fc.speech && typeof fc.speech === 'object' ? fc.speech : {};
        const branchKey = typeof this.branchId === 'string' && this.branchId !== '' ? this.branchId : 'base';
        let branchSpeech = {};
        if (
            branchKey !== 'base' &&
            fc &&
            fc.branches &&
            typeof fc.branches === 'object' &&
            fc.branches[branchKey] &&
            typeof fc.branches[branchKey].speech === 'object'
        ) {
            branchSpeech = fc.branches[branchKey].speech;
        }
        const catalogReady = catalog !== null && catalog !== undefined && typeof catalog === 'object';
        return html`
            <div
                style="margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--glass-border-subtle); display: flex; flex-direction: column; gap: var(--space-2);"
            >
                <div style="font-weight: var(--font-semibold);">${this.t('property_panel.speech_title')}</div>
                <div style="font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.4;">
                    ${this.t('property_panel.speech_hint')}
                </div>
                ${catalogReady
                    ? this._renderFlowSpeechSettingsInner(catalog, flowSpeech)
                    : html`<div class="speech-catalog-pending">${this.t(
                          'property_panel.speech_catalog_pending',
                      )}</div>`}
                ${catalogReady && branchKey !== 'base'
                    ? this._renderBranchSpeechSettingsInner(catalog, branchSpeech, branchKey)
                    : nothing}
            </div>
        `;
    }

    _onFlowTimeout(e) {
        const v = e.target.value.trim();
        if (v === '') {
            this._editor.patchFlowConfig({ patch: { timeout: null } });
            return;
        }
        const n = parseInt(v, 10);
        if (!Number.isFinite(n) || n < 1) {
            return;
        }
        const clamped = Math.min(n, 3600);
        this._editor.patchFlowConfig({ patch: { timeout: clamped } });
    }

    render() {
        if (!this.flowId) {
            return html``;
        }
        const state = asObject(this._editor.state);
        const fc = state.flowConfig;
        const raw = fc && typeof fc.timeout === 'number' ? String(fc.timeout) : '';
        return html`
            <div class="card-inner">
                <div class="card-title">${this.t('flow_property_panel.card_title')}</div>
                <div class="flow-settings-heading">${this.t('property_panel.flow_settings_title')}</div>
                <label class="flow-timeout-label">${this.t('property_panel.flow_timeout_seconds')}</label>
                <input
                    type="number"
                    min="1"
                    max="3600"
                    class="flow-timeout-input"
                    .value=${raw}
                    @input=${this._onFlowTimeout}
                />
                <div class="flow-timeout-hint">${this.t('property_panel.flow_timeout_hint')}</div>
                ${this._renderSpeechSettings()}
            </div>
        `;
    }
}

customElements.define('flows-flow-property-panel', FlowsFlowPropertyPanel);
