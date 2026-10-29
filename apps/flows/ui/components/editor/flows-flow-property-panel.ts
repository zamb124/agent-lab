/**
 * flows-flow-property-panel — лимиты flow и профиль речи (уровень flow / ветки).
 *
 * Показывается в правом столбе по кнопке в сайдбаре (`flows-node-types-sidebar`).
 * Не привязана к выбранной ноде.
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

type SpeechBlockName = 'stt' | 'tts' | 'vad';
type SpeechScope = 'flow' | 'branch';
type SpeechChange = (event: CustomEvent) => void;

function _needsSttTtsModel(provider: unknown) {
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

function requireStringIds(value: unknown, label: string): string[] {
    if (!Array.isArray(value)) {
        throw new Error(`flows-flow-property-panel: ${label} must be a list`);
    }
    const ids: string[] = [];
    for (const item of value) {
        if (typeof item !== 'string') {
            throw new Error(`flows-flow-property-panel: ${label} id must be a string`);
        }
        ids.push(item);
    }
    return ids;
}

function optionalStringIds(value: unknown, label: string): string[] {
    if (!Array.isArray(value)) return [];
    return requireStringIds(value, label);
}

function requireNumberIds(value: unknown, label: string): number[] {
    if (!Array.isArray(value)) {
        throw new Error(`flows-flow-property-panel: ${label} must be a list`);
    }
    const ids: number[] = [];
    for (const item of value) {
        if (typeof item !== 'number' || !Number.isFinite(item)) {
            throw new Error(`flows-flow-property-panel: ${label} id must be a number`);
        }
        ids.push(item);
    }
    return ids;
}

function optionalNumberIds(value: unknown, label: string): number[] {
    if (!Array.isArray(value)) return [];
    return requireNumberIds(value, label);
}

function readFlowConfig(state: unknown): Record<string, unknown> | null {
    if (!isPlainObject(state) || !isPlainObject(state.flowConfig)) return null;
    return state.flowConfig;
}

function requireFlowConfig(state: unknown): Record<string, unknown> {
    const flowConfig = readFlowConfig(state);
    if (flowConfig === null) {
        throw new Error('flows-flow-property-panel: flowConfig required');
    }
    return flowConfig;
}

function copyBranchMap(flowConfig: Record<string, unknown>): Record<string, unknown> {
    if (!isPlainObject(flowConfig.branches)) return {};
    return { ...flowConfig.branches };
}

export class FlowsFlowPropertyPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String },
        branchId: { type: String },
    }
    declare flowId: string;
    declare branchId: string;
;

    static override styles: CSSResultGroup = [
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
    private _editor: ControllerFor<'flows/editor'>;
    private _voiceCatalog: OpController;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._editor = this.useOp('flows/editor');
        this._voiceCatalog = this.useOp('flows/voice_providers_catalog_load');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._voiceCatalog
            .run({})
            .catch((err: unknown) => {
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
    _mergeSpeechBlock(prevSpeech: unknown, block: SpeechBlockName, field: string, value: unknown) {
        const speech = isPlainObject(prevSpeech) ? { ...prevSpeech } : {};
        const previous = speech[block];
        const prevBlock = isPlainObject(previous) ? { ...previous } : {};
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

    /**
     * Эффективный TTS=flow.speech + branch.speech; голос на ветке перекрывает flow.
     * Устаревший `branches.*.speech.tts.voice` в состоянии редактора давит на flow
     * после смены голоса на уровне flow — снимаем только поле voice на всех ветках.
     * @param {unknown} flowConfig
     * @returns {Record<string, unknown>|null}
     */
    _stripTtsVoiceFromAllBranches(flowConfig: unknown): Record<string, unknown> | null {
        if (!isPlainObject(flowConfig)) return null;
        const branches = copyBranchMap(flowConfig);
        const keys = Object.keys(branches);
        if (keys.length === 0) return null;
        let changed = false;
        for (const branchKey of keys) {
            const rawBranch = branches[branchKey];
            if (!isPlainObject(rawBranch)) continue;
            const speech = isPlainObject(rawBranch.speech) ? rawBranch.speech : null;
            const tts = speech !== null && isPlainObject(speech.tts) ? speech.tts : null;
            if (tts === null || typeof tts.voice !== 'string' || tts.voice === '') continue;
            const nextSpeech = this._mergeSpeechBlock(speech, 'tts', 'voice', null);
            const nextBranch: Record<string, unknown> = { ...rawBranch };
            if (nextSpeech === null) {
                delete nextBranch.speech;
            } else {
                nextBranch.speech = nextSpeech;
            }
            branches[branchKey] = nextBranch;
            changed = true;
        }
        return changed ? branches : null;
    }

    _commitFlowSpeech(block: SpeechBlockName, field: string, value: unknown) {
        const flowConfig = requireFlowConfig(this._editor.state);
        const prev = isPlainObject(flowConfig.speech) ? flowConfig.speech : null;
        const next = this._mergeSpeechBlock(prev, block, field, value);
        const patch: Record<string, unknown> = { speech: next };
        if (block === 'tts' && field === 'voice') {
            const branchesNext = this._stripTtsVoiceFromAllBranches(flowConfig);
            if (branchesNext !== null) patch.branches = branchesNext;
        }
        this._editor.patchFlowConfig({ patch });
    }

    _commitBranchSpeech(branchKey: string, block: SpeechBlockName, field: string, value: unknown) {
        const flowConfig = requireFlowConfig(this._editor.state);
        const branches = copyBranchMap(flowConfig);
        const rawBranch = branches[branchKey];
        if (!isPlainObject(rawBranch)) {
            throw new Error('flows-flow-property-panel: branch config missing for speech patch');
        }
        const prevBranch: Record<string, unknown> = { ...rawBranch };
        const prevSpeech = isPlainObject(prevBranch.speech) ? prevBranch.speech : null;
        const nextSpeech = this._mergeSpeechBlock(prevSpeech, block, field, value);
        if (nextSpeech === null) {
            delete prevBranch.speech;
        } else {
            prevBranch.speech = nextSpeech;
        }
        branches[branchKey] = prevBranch;
        this._editor.patchFlowConfig({ patch: { branches } });
    }

    _clearFlowSpeech() {
        this._editor.patchFlowConfig({ patch: { speech: null } });
    }

    _clearBranchSpeech(branchKey: string) {
        const flowConfig = requireFlowConfig(this._editor.state);
        const branches = copyBranchMap(flowConfig);
        const rawBranch = branches[branchKey];
        if (!isPlainObject(rawBranch)) {
            throw new Error('flows-flow-property-panel: branch config missing for speech clear');
        }
        const prevBranch: Record<string, unknown> = { ...rawBranch };
        delete prevBranch.speech;
        branches[branchKey] = prevBranch;
        this._editor.patchFlowConfig({ patch: { branches } });
    }

    _modelOptions(kind: string, provider: unknown, catalog: unknown): string[] {
        if (!_needsSttTtsModel(provider) || !isPlainObject(catalog)) return [];
        if (provider === 'litserve') {
            if (kind === 'stt') return requireStringIds(catalog.stt_litserve_models, 'stt_litserve_models');
            return requireStringIds(catalog.tts_litserve_models, 'tts_litserve_models');
        }
        if (provider === 'cloud_ru') {
            if (kind === 'stt') return requireStringIds(catalog.cloud_ru_stt_models, 'cloud_ru_stt_models');
            return requireStringIds(catalog.cloud_ru_tts_models, 'cloud_ru_tts_models');
        }
        if (provider === 'yandex') return requireStringIds(catalog.yandex_speech_models, 'yandex_speech_models');
        if (provider === 'sber') return requireStringIds(catalog.sber_speech_models, 'sber_speech_models');
        return [];
    }

    _enumChangeString(e: CustomEvent, ctx: string) {
        const d = e.detail;
        if (!isPlainObject(d)) {
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

    _renderModelSelect(
        kind: string,
        provider: unknown,
        catalog: unknown,
        currentModel: unknown,
        onPick: SpeechChange,
        emptyLabelKey: string,
        hintKey = '',
    ) {
        const opts = this._modelOptions(kind, provider, catalog);
        if (opts.length === 0) {
            return '';
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
                    .hint=${hintKey ? this.t(hintKey) : ''}
                    .value=${cur}
                    .config=${{ values }}
                    @change=${onPick}
                ></platform-field>
            </div>
        `;
    }

    /** @param {unknown} catalog */
    _speechLanguageIds(catalog: unknown) {
        if (!isPlainObject(catalog)) return [];
        return optionalStringIds(catalog.speech_language_ids, 'speech_language_ids');
    }

    /** @param {unknown} catalog */
    _litserveTtsVoiceIdsUnion(catalog: unknown) {
        if (!isPlainObject(catalog) || !Array.isArray(catalog.tts_litserve_voice_hints)) return [];
        const seen = new Set<string>();
        for (const hint of catalog.tts_litserve_voice_hints) {
            if (!isPlainObject(hint) || !Array.isArray(hint.voice_ids)) continue;
            for (const id of hint.voice_ids) {
                if (typeof id === 'string' && id !== '') seen.add(id);
            }
        }
        return [...seen].sort();
    }

    /**
     * Litserve: при заданной model — голоса из hint; иначе union по hint'ам каталога.
     * Пустой prov при непустом union — те же id (наследование провайдера с компании).
     */
    /** @param {unknown} catalog */
    _ttsVoiceIds(ttsProv: unknown, ttsModel: unknown, catalog: unknown) {
        if (!isPlainObject(catalog)) return [];
        const litserveUnion = this._litserveTtsVoiceIdsUnion(catalog);
        if (ttsProv === 'litserve') {
            if (typeof ttsModel === 'string' && ttsModel !== '') {
                const hints = catalog.tts_litserve_voice_hints;
                if (!Array.isArray(hints)) return [];
                const hint = hints.find((item) => isPlainObject(item) && item.api_model_id === ttsModel);
                if (!isPlainObject(hint) || !Array.isArray(hint.voice_ids)) return [];
                return requireStringIds(hint.voice_ids, 'tts voice_ids');
            }
            return litserveUnion;
        }
        if (ttsProv === '' && litserveUnion.length > 0) return litserveUnion;
        if (ttsProv === 'cloud_ru') return optionalStringIds(catalog.cloud_ru_tts_voice_ids, 'cloud_ru_tts_voice_ids');
        if (ttsProv === 'yandex') return optionalStringIds(catalog.yandex_tts_voice_ids, 'yandex_tts_voice_ids');
        if (ttsProv === 'sber') return optionalStringIds(catalog.sber_tts_voice_ids, 'sber_tts_voice_ids');
        return [];
    }

    /** @param {unknown} catalog */
    _ttsSampleRateInts(ttsProv: unknown, catalog: unknown) {
        if (!isPlainObject(catalog)) return [];
        if (ttsProv === 'litserve' && Array.isArray(catalog.litserve_silero_tts_sample_rate_ids)) {
            return requireNumberIds(catalog.litserve_silero_tts_sample_rate_ids, 'litserve_silero_tts_sample_rate_ids');
        }
        return optionalNumberIds(catalog.tts_sample_rate_ids, 'tts_sample_rate_ids');
    }

    /** @param {unknown} catalog */
    _vadSampleRateInts(catalog: unknown) {
        if (!isPlainObject(catalog)) return [];
        return optionalNumberIds(catalog.vad_sample_rate_ids, 'vad_sample_rate_ids');
    }

    /** @param {unknown} catalog */
    _vadProviderIds(catalog: unknown) {
        if (!isPlainObject(catalog)) return [];
        return optionalStringIds(catalog.vad_provider_ids, 'vad_provider_ids');
    }

    _mergeStringOption(sortedBase: readonly string[], current: unknown) {
        if (typeof current !== 'string' || current === '') return [...sortedBase];
        const base = [...sortedBase];
        if (base.includes(current)) return base.sort();
        base.push(current);
        return base.sort();
    }

    _mergeIntOption(sortedBase: readonly number[], current: unknown) {
        const base = [...sortedBase];
        if (typeof current !== 'number' || !Number.isFinite(current)) return base.sort((a, b) => a - b);
        if (base.includes(current)) return base.sort((a, b) => a - b);
        base.push(current);
        return base.sort((a, b) => a - b);
    }

    _mergeThresholdOpts(currentNum: unknown) {
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

    _renderSpeechStringSelect(
        labelKey: string,
        sortedIds: readonly string[],
        currentStr: unknown,
        emptyLabelKey: string,
        onChange: SpeechChange,
        hintKey = '',
    ) {
        const cur = typeof currentStr === 'string' ? currentStr : '';
        const ids = this._mergeStringOption(sortedIds, cur);
        if (ids.length === 0) return '';
        const values = [{ value: '', label: this.t(emptyLabelKey) }, ...ids.map((id) => ({ value: id, label: id }))];
        return html`
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t(labelKey)}
                    .hint=${hintKey ? this.t(hintKey) : ''}
                    .value=${cur}
                    .config=${{ values }}
                    @change=${onChange}
                ></platform-field>
            </div>
        `;
    }

    _renderSpeechIntSelect(
        labelKey: string,
        sortedInts: readonly number[],
        currentNum: unknown,
        emptyLabelKey: string,
        onChange: SpeechChange,
        hintKey = '',
    ) {
        const ints = this._mergeIntOption(sortedInts, typeof currentNum === 'number' ? currentNum : NaN);
        if (ints.length === 0) return '';
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
                    .hint=${hintKey ? this.t(hintKey) : ''}
                    .value=${curStr}
                    .config=${{ values }}
                    @change=${onChange}
                ></platform-field>
            </div>
        `;
    }

    _renderVadThresholdSelect(emptyLabelKey: string, currentNum: unknown, onChange: SpeechChange, hintKey = '') {
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
                    .hint=${hintKey ? this.t(hintKey) : ''}
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
    _speechHandlers(scope: SpeechScope, branchKey?: string) {
        const commit =
            scope === 'flow'
                ? (block: SpeechBlockName, field: string, value: unknown) => this._commitFlowSpeech(block, field, value)
                : (block: SpeechBlockName, field: string, value: unknown) => {
                    if (typeof branchKey !== 'string' || branchKey.length === 0) {
                        throw new Error('flows-flow-property-panel: branch key required');
                    }
                    this._commitBranchSpeech(branchKey, block, field, value);
                };
        return {
            provider: (block: SpeechBlockName) => (e: CustomEvent) => {
                const raw = this._enumChangeString(e, `speech provider (${block})`);
                const trimmed = raw.trim();
                commit(block, 'provider', trimmed === '' ? null : trimmed);
                commit(block, 'model', null);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                    commit(block, 'sample_rate', null);
                }
            },
            modelSelect: (block: SpeechBlockName) => (e: CustomEvent) => {
                const raw = this._enumChangeString(e, `speech model (${block})`);
                const trimmed = raw.trim();
                commit(block, 'model', trimmed === '' ? null : trimmed);
                if (block === 'tts') {
                    commit(block, 'voice', null);
                }
            },
            enumSelect: (block: SpeechBlockName, field: string) => (e: CustomEvent) => {
                const raw = this._enumChangeString(e, `speech ${block}.${field}`);
                const trimmed = raw.trim();
                commit(block, field, trimmed === '' ? null : trimmed);
            },
            intSelect: (block: SpeechBlockName, field: string) => (e: CustomEvent) => {
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
            vadThresholdSelect: () => (e: CustomEvent) => {
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
            responseFormat: (block: SpeechBlockName) => (e: CustomEvent) => {
                const raw = this._enumChangeString(e, `speech ${block}.response_format`);
                const trimmed = raw.trim();
                commit(block, 'response_format', trimmed === '' ? null : trimmed);
            },
            vadProvider: (block: SpeechBlockName) => (e: CustomEvent) => {
                const raw = this._enumChangeString(e, `speech ${block}.provider`);
                const trimmed = raw.trim();
                commit(block, 'provider', trimmed === '' ? null : trimmed);
            },
        };
    }

    _renderFlowSpeechSettingsInner(catalog: unknown, speech: unknown) {
        const speechRecord = isPlainObject(speech) ? speech : {};
        const stt = isPlainObject(speechRecord.stt) ? speechRecord.stt : {};
        const tts = isPlainObject(speechRecord.tts) ? speechRecord.tts : {};
        const vad = isPlainObject(speechRecord.vad) ? speechRecord.vad : {};
        const catalogRecord = isPlainObject(catalog) ? catalog : null;
        const provOpts = catalogRecord === null
            ? []
            : optionalStringIds(catalogRecord.stt_tts_provider_ids, 'stt_tts_provider_ids');
        const rfOpts = catalogRecord === null
            ? []
            : optionalStringIds(catalogRecord.response_format_ids, 'response_format_ids');
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
            ...provOpts.map((id: string) => ({ value: id, label: id })),
        ];
        const ttsProvValuesFlow = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...provOpts.map((id: string) => ({ value: id, label: id })),
        ];
        const rfValuesFlow = [
            { value: '', label: this.t('property_panel.speech_option_inherit_empty') },
            ...rfOpts.map((id: string) => ({ value: id, label: id })),
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
                    .hint=${this.t('property_panel.speech_stt_provider_hint')}
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
                      'property_panel.speech_stt_model_hint',
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof stt.language === 'string' ? stt.language : '',
                'property_panel.speech_option_inherit_empty',
                h.enumSelect('stt', 'language'),
                'property_panel.speech_stt_language_hint',
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_tts')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .hint=${this.t('property_panel.speech_tts_provider_hint')}
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
                      'property_panel.speech_tts_model_hint',
                  )
                : nothing}
            ${voiceOpts.length > 0
                ? this._renderSpeechStringSelect(
                      'property_panel.speech_field_voice',
                      voiceOpts,
                      typeof tts.voice === 'string' ? tts.voice : '',
                      'property_panel.speech_option_inherit_empty',
                      h.enumSelect('tts', 'voice'),
                      'property_panel.speech_tts_voice_hint',
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof tts.language === 'string' ? tts.language : '',
                'property_panel.speech_option_inherit_empty',
                h.enumSelect('tts', 'language'),
                'property_panel.speech_tts_language_hint',
            )}
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_response_format')}
                    .hint=${this.t('property_panel.speech_response_format_hint')}
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
                'property_panel.speech_tts_sample_rate_hint',
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .hint=${this.t('property_panel.speech_vad_provider_hint')}
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
                'property_panel.speech_vad_sample_rate_hint',
            )}
            ${this._renderVadThresholdSelect(
                'property_panel.speech_option_inherit_empty',
                typeof vad.threshold === 'number' ? vad.threshold : NaN,
                h.vadThresholdSelect(),
                'property_panel.speech_vad_threshold_hint',
            )}
            <div class="speech-actions">
                <platform-button variant="ghost" density="compact" @click=${() => this._clearFlowSpeech()}>
                    ${this.t('property_panel.speech_clear_flow')}
                </platform-button>
            </div>
        `;
    }

    _renderBranchSpeechSettingsInner(catalog: unknown, speech: unknown, branchKey: string) {
        const speechRecord = isPlainObject(speech) ? speech : {};
        const stt = isPlainObject(speechRecord.stt) ? speechRecord.stt : {};
        const tts = isPlainObject(speechRecord.tts) ? speechRecord.tts : {};
        const vad = isPlainObject(speechRecord.vad) ? speechRecord.vad : {};
        const catalogRecord = isPlainObject(catalog) ? catalog : null;
        const provOpts = catalogRecord === null
            ? []
            : optionalStringIds(catalogRecord.stt_tts_provider_ids, 'stt_tts_provider_ids');
        const rfOpts = catalogRecord === null
            ? []
            : optionalStringIds(catalogRecord.response_format_ids, 'response_format_ids');
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
            ...provOpts.map((id: string) => ({ value: id, label: id })),
        ];
        const ttsProvValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...provOpts.map((id: string) => ({ value: id, label: id })),
        ];
        const rfValuesBranch = [
            { value: '', label: this.t('property_panel.speech_option_inherit_flow') },
            ...rfOpts.map((id: string) => ({ value: id, label: id })),
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
                    .hint=${this.t('property_panel.speech_stt_provider_hint')}
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
                      'property_panel.speech_stt_model_hint',
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof stt.language === 'string' ? stt.language : '',
                'property_panel.speech_option_inherit_flow',
                h.enumSelect('stt', 'language'),
                'property_panel.speech_stt_language_hint',
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_tts')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .hint=${this.t('property_panel.speech_tts_provider_hint')}
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
                      'property_panel.speech_tts_model_hint',
                  )
                : nothing}
            ${voiceOpts.length > 0
                ? this._renderSpeechStringSelect(
                      'property_panel.speech_field_voice',
                      voiceOpts,
                      typeof tts.voice === 'string' ? tts.voice : '',
                      'property_panel.speech_option_inherit_flow',
                      h.enumSelect('tts', 'voice'),
                      'property_panel.speech_tts_voice_hint',
                  )
                : nothing}
            ${this._renderSpeechStringSelect(
                'property_panel.speech_field_language',
                langOpts,
                typeof tts.language === 'string' ? tts.language : '',
                'property_panel.speech_option_inherit_flow',
                h.enumSelect('tts', 'language'),
                'property_panel.speech_tts_language_hint',
            )}
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_response_format')}
                    .hint=${this.t('property_panel.speech_response_format_hint')}
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
                'property_panel.speech_tts_sample_rate_hint',
            )}

            <div class="speech-subtitle">${this.t('property_panel.speech_section_vad')}</div>
            <div class="speech-field">
                <platform-field
                    mode="edit"
                    type="enum"
                    .label=${this.t('property_panel.speech_field_provider')}
                    .hint=${this.t('property_panel.speech_vad_provider_hint')}
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
                'property_panel.speech_vad_sample_rate_hint',
            )}
            ${this._renderVadThresholdSelect(
                'property_panel.speech_option_inherit_flow',
                typeof vad.threshold === 'number' ? vad.threshold : NaN,
                h.vadThresholdSelect(),
                'property_panel.speech_vad_threshold_hint',
            )}
            <div class="speech-actions">
                <platform-button variant="ghost" density="compact" @click=${() => this._clearBranchSpeech(branchKey)}>
                    ${this.t('property_panel.speech_clear_branch')}
                </platform-button>
            </div>
        `;
    }

    _renderSpeechSettings() {
        const catalog = this._voiceCatalog.lastResult;
        const fc = readFlowConfig(this._editor.state);
        const flowSpeech = fc !== null && isPlainObject(fc.speech) ? fc.speech : {};
        const branchKey = typeof this.branchId === 'string' && this.branchId !== '' ? this.branchId : 'base';
        let branchSpeech: Record<string, unknown> = {};
        if (branchKey !== 'base' && fc !== null && isPlainObject(fc.branches)) {
            const branch = fc.branches[branchKey];
            if (isPlainObject(branch) && isPlainObject(branch.speech)) branchSpeech = branch.speech;
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

    _onFlowTimeout(e: CustomEvent) {
        const detail = e.detail;
        if (!isPlainObject(detail) || !('value' in detail)) {
            throw new Error('flows-flow-property-panel: flow_timeout detail.value');
        }
        const val = detail.value;
        if (val === null) {
            this._editor.patchFlowConfig({ patch: { timeout: null } });
            return;
        }
        if (typeof val !== 'number' || !Number.isFinite(val)) {
            throw new Error('flows-flow-property-panel: flow_timeout detail.value number|null');
        }
        const n = Math.floor(val);
        if (n < 1) return;
        const clamped = Math.min(n, 3600);
        this._editor.patchFlowConfig({ patch: { timeout: clamped } });
    }

    override render(): TemplateResult {
        if (!this.flowId) {
            return html``;
        }
        const fc = readFlowConfig(this._editor.state);
        const timeoutVal =
            fc !== null && typeof fc.timeout === 'number' && Number.isFinite(fc.timeout)
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
