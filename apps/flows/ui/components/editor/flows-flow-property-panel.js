/**
 * flows-flow-property-panel — лимиты flow и профиль речи (уровень flow / ветки).
 *
 * Показывается в правом столбе по кнопке в сайдбаре (`flows-node-types-sidebar`).
 * Не привязана к выбранной ноде.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
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
            .flow-settings-heading {
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-1);
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

    _enumChangeString(e, ctx) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`${ctx}: change detail object required`);
        }
        if (!('value' in d)) {
            throw new Error(`${ctx}: detail.value required`);
        }
        const raw = d.value;
        if (typeof raw !== 'string') {
            throw new Error(`${ctx}: detail.value must be string`);
        }
        return raw;
    }

    _renderModelSelect(kind, provider, catalog, currentModel, onPick, emptyLabelKey) {
        const opts = this._modelOptions(kind, provider, catalog);
        if (opts.length === 0) {
            return nothing;
        }
        const cur = typeof currentModel === 'string' ? currentModel : '';
        const values = [
            { value: '', label: this.t(emptyLabelKey) },
            ...opts.map((id) => ({ value: id, label: id })),
        ];
        return html`
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_model')}
                    .value=${cur}
                    .config=${{ values }}
                    @change=${onPick}
                ></platform-field>
            </div>
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
        const values = [{ value: '', label: this.t(emptyLabelKey) }, ...ids.map((id) => ({ value: id, label: id }))];
        return html`
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t(labelKey)}
                    .value=${cur}
                    .config=${{ values }}
                    @change=${onChange}
                ></platform-field>
            </div>
        `;
    }

    _renderSpeechIntSelect(labelKey, sortedInts, currentNum, emptyLabelKey, onChange) {
        const ints = this._mergeIntOption(sortedInts, typeof currentNum === 'number' ? currentNum : NaN);
        if (ints.length === 0) return nothing;
        const curStr =
            typeof currentNum === 'number' && Number.isFinite(currentNum) ? String(currentNum) : '';
        const values = [
            { value: '', label: this.t(emptyLabelKey) },
            ...ints.map((n) => ({ value: String(n), label: String(n) })),
        ];
        return html`
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t(labelKey)}
                    .value=${curStr}
                    .config=${{ values }}
                    @change=${onChange}
                ></platform-field>
            </div>
        `;
    }

    _renderVadThresholdSelect(emptyLabelKey, currentNum, onChange) {
        const { opts, cur } = this._mergeThresholdOpts(
            typeof currentNum === 'number' ? currentNum : NaN,
        );
        const values = [
            { value: '', label: this.t(emptyLabelKey) },
            ...opts.map((v) => ({ value: v, label: v })),
        ];
        return html`
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_vad_threshold')}
                    .value=${cur}
                    .config=${{ values }}
                    @change=${onChange}
                ></platform-field>
            </div>
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
                : (block, field, value) => {
                    const bk = typeof branchKey === 'string' ? branchKey : '';
                    this._commitBranchSpeech(bk, block, field, value);
                };
        return {
            provider: (block) => (e) => {
                const raw = this._enumChangeString(e, `speech provider (${block})`);
                const trimmed = raw.trim();
                commit(block, 'provider', trimmed === '' ? null : trimmed);
                commit(block, 'model', null);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                    commit(block, 'sample_rate', null);
                }
            },
            modelSelect: (block) => (e) => {
                const raw = this._enumChangeString(e, `speech model (${block})`);
                const trimmed = raw.trim();
                commit(block, 'model', trimmed === '' ? null : trimmed);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                }
            },
            enumSelect: (block, field) => (e) => {
                const raw = this._enumChangeString(e, `speech ${block}.${field}`);
                const trimmed = raw.trim();
                commit(block, field, trimmed === '' ? null : trimmed);
            },
            intSelect: (block, field) => (e) => {
                const raw = this._enumChangeString(e, `speech int ${block}.${field}`);
                const trimmed = raw.trim();
                if (trimmed === '') {
                    commit(block, field, null);
                    return;
                }
                const n = parseInt(trimmed, 10);
                if (!Number.isFinite(n)) {
                    this.toast('flows:property_panel.speech_invalid_number', { type: 'error' });
                    return;
                }
                commit(block, field, n);
            },
            vadThresholdSelect: () => (e) => {
                const raw = this._enumChangeString(e, 'speech vad.threshold');
                const trimmed = raw.trim();
                if (trimmed === '') {
                    commit('vad', 'threshold', null);
                    return;
                }
                const n = Number(trimmed);
                if (!Number.isFinite(n)) {
                    this.toast('flows:property_panel.speech_invalid_number', { type: 'error' });
                    return;
                }
                commit('vad', 'threshold', n);
            },
            responseFormat: (block) => (e) => {
                const raw = this._enumChangeString(e, `speech ${block}.response_format`);
                const trimmed = raw.trim();
                commit(block, 'response_format', trimmed === '' ? null : trimmed);
            },
            vadProvider: (block) => (e) => {
                const raw = this._enumChangeString(e, `speech ${block}.provider`);
                const trimmed = raw.trim();
                commit(block, 'provider', trimmed === '' ? null : trimmed);
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
        const sttProvValues = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...provOpts.map((id) => ({ value: id, label: id })),
        ];
        const ttsProvValuesFlow = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...provOpts.map((id) => ({ value: id, label: id })),
        ];
        const rfValuesFlow = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...rfOpts.map((id) => ({ value: id, label: id })),
        ];
        const vadProvValuesFlow = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...vadProvOpts.map((id) => ({ value: id, label: id })),
        ];
        const ttsRfStr = typeof tts.response_format === 'string' ? tts.response_format : '';
        return html`
            <div class="speech-subtitle">${this.t('property_panel.speech_section_stt')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${sttProv}
                    .config=${{ values: sttProvValues }}
                    @change=${h.provider('stt')}
                ></platform-field>
            </div>
            ${_needsSttTtsModel(sttProv)
                ? this._renderModelSelect(
                      'stt',
                      sttProv,
                      catalog,
                      sttModel,
                      h.modelSelect('stt'),
                      'property_panel.speech_option_inherit_empty',
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
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${ttsProv}
                    .config=${{ values: ttsProvValuesFlow }}
                    @change=${h.provider('tts')}
                ></platform-field>
            </div>
            ${_needsSttTtsModel(ttsProv)
                ? this._renderModelSelect(
                      'tts',
                      ttsProv,
                      catalog,
                      ttsModel,
                      h.modelSelect('tts'),
                      'property_panel.speech_option_inherit_empty',
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
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_response_format')}
                    .value=${ttsRfStr}
                    .config=${{ values: rfValuesFlow }}
                    @change=${h.responseFormat('tts')}
                ></platform-field>
            </div>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                ttsSrOpts,
                typeof tts.sample_rate === 'number' ? tts.sample_rate : NaN,
                'property_panel.speech_option_inherit_empty',
                h.intSelect('tts', 'sample_rate'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${vadProv}
                    .config=${{ values: vadProvValuesFlow }}
                    @change=${h.vadProvider('vad')}
                ></platform-field>
            </div>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                vadSrOpts,
                typeof vad.sample_rate === 'number' ? vad.sample_rate : NaN,
                'property_panel.speech_option_inherit_empty',
                h.intSelect('vad', 'sample_rate'),
            )}
            ${this._renderVadThresholdSelect(
                'property_panel.speech_option_inherit_empty',
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
        const sttProvValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...provOpts.map((id) => ({ value: id, label: id })),
        ];
        const ttsProvValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...provOpts.map((id) => ({ value: id, label: id })),
        ];
        const rfValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...rfOpts.map((id) => ({ value: id, label: id })),
        ];
        const vadProvValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...vadProvOpts.map((id) => ({ value: id, label: id })),
        ];
        const ttsRfStrBranch = typeof tts.response_format === 'string' ? tts.response_format : '';
        return html`
            <div style="font-weight: var(--font-semibold); margin-top: var(--space-3);">${this.t(
                'property_panel.speech_branch_title',
            )}</div>
            <div style="font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.4;">
                ${this.t('property_panel.speech_branch_hint')}
            </div>
            <div class="speech-subtitle">${this.t('property_panel.speech_section_stt')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${sttProv}
                    .config=${{ values: sttProvValuesBranch }}
                    @change=${h.provider('stt')}
                ></platform-field>
            </div>
            ${_needsSttTtsModel(sttProv)
                ? this._renderModelSelect(
                      'stt',
                      sttProv,
                      catalog,
                      sttModel,
                      h.modelSelect('stt'),
                      'property_panel.speech_option_inherit_flow',
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
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${ttsProv}
                    .config=${{ values: ttsProvValuesBranch }}
                    @change=${h.provider('tts')}
                ></platform-field>
            </div>
            ${_needsSttTtsModel(ttsProv)
                ? this._renderModelSelect(
                      'tts',
                      ttsProv,
                      catalog,
                      ttsModel,
                      h.modelSelect('tts'),
                      'property_panel.speech_option_inherit_flow',
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
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_response_format')}
                    .value=${ttsRfStrBranch}
                    .config=${{ values: rfValuesBranch }}
                    @change=${h.responseFormat('tts')}
                ></platform-field>
            </div>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                ttsSrOpts,
                typeof tts.sample_rate === 'number' ? tts.sample_rate : NaN,
                'property_panel.speech_option_inherit_flow',
                h.intSelect('tts', 'sample_rate'),
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .value=${vadProv}
                    .config=${{ values: vadProvValuesBranch }}
                    @change=${h.vadProvider('vad')}
                ></platform-field>
            </div>
            ${this._renderSpeechIntSelect(
                'property_panel.speech_field_sample_rate',
                vadSrOpts,
                typeof vad.sample_rate === 'number' ? vad.sample_rate : NaN,
                'property_panel.speech_option_inherit_flow',
                h.intSelect('vad', 'sample_rate'),
            )}
            ${this._renderVadThresholdSelect(
                'property_panel.speech_option_inherit_flow',
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
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-flow-property-panel: flow_timeout change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-flow-property-panel: flow_timeout detail.value');
        }
        const val = d.value;
        if (val === null) {
            this._editor.patchFlowConfig({ patch: { timeout: null } });
            return;
        }
        if (typeof val !== 'number' || !Number.isFinite(val)) {
            throw new Error('flows-flow-property-panel: flow_timeout detail.value number|null');
        }
        const n = Math.floor(val);
        if (n < 1) {
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
        const timeoutVal =
            fc && typeof fc === 'object' && typeof fc.timeout === 'number' && Number.isFinite(fc.timeout)
                ? fc.timeout
                : null;
        return html`
            <div class="card-inner">
                <div class="card-title">${this.t('flow_property_panel.card_title')}</div>
                <div class="flow-settings-heading">${this.t('property_panel.flow_settings_title')}</div>
                <platform-field
                    mode="edit"
                    type="integer"
                    .label=${this.t('property_panel.flow_timeout_seconds')}
                    .hint=${this.t('property_panel.flow_timeout_hint')}
                    .value=${timeoutVal}
                    @change=${this._onFlowTimeout}
                ></platform-field>
                ${this._renderSpeechSettings()}
            </div>
        `;
    }
}

customElements.define('flows-flow-property-panel', FlowsFlowPropertyPanel);
