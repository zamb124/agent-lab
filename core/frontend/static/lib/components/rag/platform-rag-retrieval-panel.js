/**
 * platform-rag-retrieval-panel — переиспользуемая панель advanced RAG retrieval overrides.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import { defaultRetrievalPanelValue } from '../../rag/pack_search_request_options.js';

const RETRIEVAL_MODE_VALUES = Object.freeze(['platform', 'hybrid', 'semantic', 'lexical']);

export class PlatformRagRetrievalPanel extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: Object },
        disabled: { type: Boolean },
        showPlatformDefaultsToggle: { type: Boolean, attribute: 'show-platform-defaults-toggle' },
        compact: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .panel {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .panel.compact {
                gap: var(--space-2);
            }
            .title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
            }
            .grid.compact {
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.value = defaultRetrievalPanelValue();
        this.disabled = false;
        this.showPlatformDefaultsToggle = true;
        this.compact = false;
    }

    _panelValue() {
        if (this.value && typeof this.value === 'object' && !Array.isArray(this.value)) {
            return { ...defaultRetrievalPanelValue(), ...this.value };
        }
        return defaultRetrievalPanelValue();
    }

    _emitValue(next) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: next },
            bubbles: true,
            composed: true,
        }));
    }

    _onFieldChange(e, field, normalize) {
        e.stopPropagation();
        this._patch(field, normalize(e));
    }

    _patch(field, rawValue) {
        const current = this._panelValue();
        const next = { ...current, [field]: rawValue };
        this._emitValue(next);
    }

    _retrievalModeEnumConfig() {
        return {
            values: RETRIEVAL_MODE_VALUES.map((mode) => ({
                value: mode,
                label: this.t(`rag_retrieval_panel.retrieval_mode_${mode}`),
            })),
        };
    }

    _rerankEnumConfig() {
        return {
            values: [
                { value: '', label: this.t('rag_retrieval_panel.rerank_inherit') },
                { value: 'true', label: this.t('rag_retrieval_panel.rerank_enabled') },
                { value: 'false', label: this.t('rag_retrieval_panel.rerank_disabled') },
            ],
        };
    }

    render() {
        const panel = this._panelValue();
        const disabledByDefaults = this.showPlatformDefaultsToggle && panel.usePlatformDefaults === true;
        const fieldsDisabled = this.disabled || disabledByDefaults;
        const panelClass = this.compact ? 'panel compact' : 'panel';
        const gridClass = this.compact ? 'grid compact' : 'grid';

        return html`
            <div class=${panelClass}>
                <div class="title">${this.t('rag_retrieval_panel.title')}</div>
                ${this.showPlatformDefaultsToggle ? html`
                    <platform-field
                        type="boolean"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.platform_defaults')}
                        .value=${panel.usePlatformDefaults === true}
                        ?disabled=${this.disabled}
                        @change=${(e) => this._onFieldChange(e, 'usePlatformDefaults', (ev) => ev.detail && ev.detail.value === true)}
                    ></platform-field>
                ` : ''}
                <div class=${gridClass}>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.retrieval_mode')}
                        .value=${typeof panel.retrievalMode === 'string' ? panel.retrievalMode : 'platform'}
                        .config=${this._retrievalModeEnumConfig()}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'retrievalMode', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : 'platform'
                        ))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.rrf_k')}
                        .value=${typeof panel.rrfK === 'string' ? panel.rrfK : ''}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'rrfK', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.per_channel_top_k')}
                        .value=${typeof panel.perChannelTopK === 'string' ? panel.perChannelTopK : ''}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'perChannelTopK', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.rerank')}
                        .value=${typeof panel.rerank === 'string' ? panel.rerank : ''}
                        .config=${this._rerankEnumConfig()}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'rerank', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.rerank_max_candidates')}
                        .value=${typeof panel.rerankMaxCandidates === 'string' ? panel.rerankMaxCandidates : ''}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'rerankMaxCandidates', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.freshness_weight')}
                        .value=${typeof panel.freshnessWeight === 'string' ? panel.freshnessWeight : ''}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'freshnessWeight', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('rag_retrieval_panel.freshness_half_life_days')}
                        .value=${typeof panel.freshnessHalfLifeDays === 'string' ? panel.freshnessHalfLifeDays : ''}
                        ?disabled=${fieldsDisabled}
                        @change=${(e) => this._onFieldChange(e, 'freshnessHalfLifeDays', (ev) => (
                            ev.detail && typeof ev.detail.value === 'string' ? ev.detail.value : ''
                        ))}
                    ></platform-field>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-rag-retrieval-panel', PlatformRagRetrievalPanel);
