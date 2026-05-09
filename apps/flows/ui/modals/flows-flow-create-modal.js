/**
 * flows-flow-create-modal — мастер создания flow.
 *
 * Шаг 1: выбор шаблона (preset с нуля или bundle из Магазина).
 *   - Пресеты «Создать с нуля»: react / graph / multi / code / external.
 *     Каждый пресет генерирует минимальную конфигурацию flow с
 *     соответствующей entry-нодой.
 *   - Магазин: список из `useOp('flows/flow_store_bundles')`.
 *   - Поиск фильтрует обе секции одновременно.
 *
 * Шаг 2: ввод flow_id / name / description (для пресетов) или подтверждение
 *   установки (для bundle). Submit:
 *     - preset → useResource('flows/flows').create(config)
 *     - bundle → useOp('flows/flow_reload_from_bundle').run({ flow_id })
 *   Затем `this.navigate('flow_editor', { flowId })`.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';

const FLOW_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

const FLOW_PRESETS = Object.freeze([
    {
        id: 'react',
        icon: 'sparkle',
        gradient: 'linear-gradient(135deg, #FFB7B2 0%, #B388EB 100%)',
        defaultIdPrefix: 'react_flow',
        buildConfig: ({ flow_id, name, description }) => ({
            flow_id, name, description,
            entry: 'agent',
            nodes: {
                agent: {
                    type: 'llm_node',
                    name: 'Agent',
                    config: { prompt: 'You are a helpful AI agent.', tools: [], llm: {} },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:react'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'graph',
        icon: 'workflow',
        gradient: 'linear-gradient(135deg, #C39BD3 0%, #BB8FCE 100%)',
        defaultIdPrefix: 'graph_flow',
        buildConfig: ({ flow_id, name, description }) => ({
            flow_id, name, description,
            entry: 'start',
            nodes: {
                start: { type: 'code', name: 'Start', config: { code: 'def run(state):\n    return state\n' } },
                end:   { type: 'code', name: 'End',   config: { code: 'def run(state):\n    return state\n' } },
            },
            edges: [{ from: 'start', to: 'end' }],
            variables: {}, tags: ['preset:graph'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'multi',
        icon: 'agent',
        gradient: 'linear-gradient(135deg, #5DADE2 0%, #48C9B0 100%)',
        defaultIdPrefix: 'multi_flow',
        buildConfig: ({ flow_id, name, description }) => ({
            flow_id, name, description,
            entry: 'orchestrator',
            nodes: {
                orchestrator: {
                    type: 'llm_node',
                    name: 'Orchestrator',
                    config: { prompt: 'You orchestrate sub-flows. Add sub-flow nodes in the editor.', tools: [], llm: {} },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:multi'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'code',
        icon: 'code',
        gradient: 'linear-gradient(135deg, #82E0AA 0%, #76D7C4 100%)',
        defaultIdPrefix: 'code_flow',
        buildConfig: ({ flow_id, name, description }) => ({
            flow_id, name, description,
            entry: 'compute',
            nodes: {
                compute: {
                    type: 'code',
                    name: 'Compute',
                    config: { code: 'def run(state):\n    # TODO: write your logic\n    return state\n' },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:code'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'external',
        icon: 'cloud',
        gradient: 'linear-gradient(135deg, #BB8FCE 0%, #8E44AD 100%)',
        defaultIdPrefix: 'external_flow',
        buildConfig: ({ flow_id, name, description }) => ({
            flow_id, name, description,
            entry: 'start',
            nodes: {
                start: {
                    type: 'code',
                    name: 'Start',
                    config: { code: 'def run(state):\n    # TODO: replace with remote_flow node in editor\n    return state\n' },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:external'], branches: {}, triggers: {}, resources: {},
        }),
    },
]);

export class FlowsFlowCreateModal extends PlatformFormModal {
    static modalKind = 'flows.flow_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        _step: { state: true },
        _selection: { state: true },
        _query: { state: true },
        _flowId: { state: true },
        _name: { state: true },
        _description: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            :host {
                --modal-width: min(1280px, calc(100vw - 24px));
                --modal-content-inset: 0;
            }
            .modal-title { padding: 0; }
            .head-row { display: flex; flex-direction: column; gap: 2px; }
            .subtitle { color: var(--text-secondary); font-size: var(--text-sm); font-weight: var(--font-normal); }
            .header-search {
                width: clamp(220px, 28vw, 360px);
            }
            .header-search platform-field {
                width: 100%;
            }
            .header-search platform-icon[slot='prefix'] {
                color: var(--text-tertiary);
            }
            .section-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: var(--space-2) 0 var(--space-3) 0;
            }
            .section-title:first-child { margin-top: 0; }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            @media (min-width: 720px) {
                .grid { grid-template-columns: repeat(3, 1fr); }
            }
            @media (min-width: 1100px) {
                .grid { grid-template-columns: repeat(4, 1fr); }
            }
            .card {
                position: relative;
                box-sizing: border-box;
                height: 168px;
                padding: var(--space-3) var(--space-4) var(--space-4);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                cursor: pointer;
                transition: all var(--duration-fast);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: hidden;
            }
            .card:hover { background: var(--glass-solid-medium); transform: translateY(-1px); }
            .card[active] {
                border-color: var(--accent);
                box-shadow: 0 0 0 1px var(--accent);
            }
            .card-icon {
                flex-shrink: 0;
                width: 56px;
                height: 56px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
            }
            .card-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                flex-shrink: 0;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                overflow: hidden;
            }
            .card-desc {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
                flex: 1;
                min-height: 0;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 3;
                overflow: hidden;
            }
            .empty-row {
                grid-column: 1 / -1;
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .form { display: flex; flex-direction: column; gap: var(--space-3); }
            .form .picked {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .form .picked-text { display: flex; flex-direction: column; }
            .form .picked-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .form .picked-sub { font-size: var(--text-xs); color: var(--text-tertiary); }
            .form .change-link {
                margin-left: auto;
                background: none; border: none;
                color: var(--accent);
                font: inherit; cursor: pointer;
                padding: 0;
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field input, .field textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .field textarea { min-height: 80px; resize: vertical; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .form-error { color: var(--error); font-size: var(--text-xs); margin-top: 4px; }
        `,
    ];

    constructor() {
        super();
        this._step = 1;
        this._selection = null;
        this._query = '';
        this._flowId = '';
        this._name = '';
        this._description = '';
        this._flows = this.useResource('flows/flows');
        this._bundlesOp = this.useOp('flows/flow_store_bundles');
        this._installOp = this.useOp('flows/flow_reload_from_bundle');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._bundlesOp.run({});
    }

    _matchQuery(text) {
        if (this._query.length === 0) return true;
        return String(text).toLowerCase().includes(this._query.toLowerCase());
    }

    _filteredPresets() {
        if (this._query.length === 0) return FLOW_PRESETS;
        return FLOW_PRESETS.filter((p) => {
            const title = this.t(`flow_create_modal.preset_${p.id}_title`);
            const desc = this.t(`flow_create_modal.preset_${p.id}_desc`);
            return this._matchQuery(title) || this._matchQuery(desc) || this._matchQuery(p.id);
        });
    }

    _bundles() {
        const result = this._bundlesOp.lastResult;
        return Array.isArray(result && result.items) ? result.items : [];
    }

    _filteredBundles() {
        const items = this._bundles();
        if (this._query.length === 0) return items;
        return items.filter((b) => this._matchQuery(b.name) || this._matchQuery(b.bundle_id) || this._matchQuery(b.description));
    }

    _selectPreset(preset) {
        this._selection = { kind: 'preset', preset };
        this._flowId = `${preset.defaultIdPrefix}_${Date.now().toString(36)}`;
        this._name = this.t(`flow_create_modal.preset_${preset.id}_title`);
        this._description = this.t(`flow_create_modal.preset_${preset.id}_desc`);
        this._step = 2;
        this.isDirty = true;
    }

    _selectBundle(bundle) {
        this._selection = { kind: 'bundle', bundle };
        this._flowId = bundle.bundle_id;
        this._name = typeof bundle.name === 'string' && bundle.name !== '' ? bundle.name : bundle.bundle_id;
        this._description = typeof bundle.description === 'string' ? bundle.description : '';
        this._step = 2;
        this.isDirty = true;
    }

    _backToStep1() {
        this._step = 1;
        this._selection = null;
    }

    renderHeader() {
        return html`
            <div class="head-row">
                <span>${this.t('flow_create_modal.title')}</span>
                ${this._step === 1
                    ? html`<span class="subtitle">${this.t('flow_create_modal.subtitle')}</span>`
                    : ''}
            </div>
        `;
    }

    renderHeaderActions() {
        if (this._step !== 1) return '';
        return html`
            <div class="header-search">
                <platform-field
                    type="string"
                    mode="edit"
                    pill-density="compact"
                    input-type="search"
                    .value=${this._query}
                    placeholder=${this.t('flow_create_modal.search_placeholder')}
                    @change=${(e) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-flow-create-modal: search expects string detail.value');
                        }
                        this._query = v;
                    }}
                >
                    <platform-icon slot="prefix" name="search" size="14"></platform-icon>
                </platform-field>
            </div>
        `;
    }

    renderBody() {
        if (this._step === 2) return this._renderForm();
        return this._renderCatalog();
    }

    _renderCatalog() {
        const presets = this._filteredPresets();
        const bundles = this._filteredBundles();
        return html`
            <div class="section-title">${this.t('flow_create_modal.section_scratch')}</div>
            <div class="grid">
                ${presets.length === 0
                    ? html`<div class="empty-row">${this.t('flow_create_modal.empty_search')}</div>`
                    : presets.map((p) => html`
                        <div class="card" @click=${() => this._selectPreset(p)}>
                            <div class="card-icon" style=${`background:${p.gradient};`}>
                                <platform-icon name=${p.icon} size="28"></platform-icon>
                            </div>
                            <div class="card-title">${this.t(`flow_create_modal.preset_${p.id}_title`)}</div>
                            <div class="card-desc">${this.t(`flow_create_modal.preset_${p.id}_desc`)}</div>
                        </div>
                    `)}
            </div>

            <div class="section-title">${this.t('flow_create_modal.section_store')}</div>
            ${this._renderStore(bundles)}
        `;
    }

    _renderStore(bundles) {
        if (this._bundlesOp.busy && bundles.length === 0) {
            return html`<div style="padding: var(--space-4); text-align: center"><glass-spinner></glass-spinner></div>`;
        }
        if (bundles.length === 0) {
            return html`<div class="grid"><div class="empty-row">${this.t('flow_create_modal.store_empty')}</div></div>`;
        }
        return html`
            <div class="grid">
                ${bundles.map((b) => html`
                    <div class="card" @click=${() => this._selectBundle(b)}>
                        <div class="card-icon" style="background: linear-gradient(135deg, #94B49F 0%, #5D9CEC 100%);">
                            <platform-icon name="box" size="28"></platform-icon>
                        </div>
                        <div class="card-title">${typeof b.name === 'string' && b.name !== '' ? b.name : b.bundle_id}</div>
                        <div class="card-desc">${typeof b.description === 'string' ? b.description : b.bundle_id}</div>
                    </div>
                `)}
            </div>
        `;
    }

    _renderForm() {
        const validId = FLOW_ID_PATTERN.test(this._flowId);
        const sel = this._selection;
        const titleKey = sel && sel.kind === 'preset'
            ? `flow_create_modal.preset_${sel.preset.id}_title`
            : null;
        const pickedTitle = sel && sel.kind === 'preset'
            ? this.t(titleKey)
            : (sel && sel.kind === 'bundle' ? (sel.bundle.name || sel.bundle.bundle_id) : '');
        const pickedSub = sel && sel.kind === 'bundle'
            ? this.t('flow_create_modal.picked_bundle')
            : this.t('flow_create_modal.picked_preset');
        return html`
            <div class="form">
                <div class="picked">
                    <div class="picked-text">
                        <div class="picked-title">${pickedTitle}</div>
                        <div class="picked-sub">${pickedSub}</div>
                    </div>
                    <button class="change-link" type="button" @click=${this._backToStep1}>
                        ${this.t('flow_create_modal.action_change')}
                    </button>
                </div>
                <div class="field">
                    <label>${this.t('flow_create_modal.field_flow_id')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${this._flowId}
                        placeholder="my_flow"
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-flow-create-modal: flow_id expects string detail.value');
                            }
                            this._flowId = v;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    ${this._flowId && !validId
                        ? html`<div class="form-error">${this.t('flow_create_modal.err_flow_id_pattern')}</div>`
                        : ''}
                </div>
                <div class="field">
                    <label>${this.t('flow_create_modal.field_name')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${this._name}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-flow-create-modal: name expects string detail.value');
                            }
                            this._name = v;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
                <div class="field">
                    <label>${this.t('flow_create_modal.field_description')}</label>
                    <platform-field
                        type="text"
                        mode="edit"
                        .value=${this._description}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-flow-create-modal: description expects string detail.value');
                            }
                            this._description = v;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    renderFooter() {
        if (this._step === 1) {
            return html`
                <platform-button @click=${() => this.close()}>${this.t('flow_create_modal.action_cancel')}</platform-button>
            `;
        }
        const validId = FLOW_ID_PATTERN.test(this._flowId);
        const valid = validId && this._name.trim().length > 0;
        const isBundle = this._selection && this._selection.kind === 'bundle';
        return html`
            <platform-button @click=${this._backToStep1}>${this.t('flow_create_modal.action_back')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._onSubmit}>
                ${isBundle
                    ? this.t('flow_create_modal.action_install')
                    : this.t('flow_create_modal.action_create')}
            </platform-button>
        `;
    }

    async _onSubmit() {
        const sel = this._selection;
        if (!sel) return;
        const flow_id = this._flowId.trim();
        const name = this._name.trim();
        if (sel.kind === 'preset') {
            const config = sel.preset.buildConfig({
                flow_id,
                name,
                description: this._description,
            });
            this._flows.create(config);
            this.closeAfterSave();
            this.navigate('flow_editor', { flowId: config.flow_id });
            return;
        }
        const result = await this._installOp.run({ flow_id: sel.bundle.bundle_id });
        const installedId = (result && result.flow_id) || sel.bundle.bundle_id;
        this.closeAfterSave();
        this._flows.load();
        this.navigate('flow_editor', { flowId: installedId });
    }
}

customElements.define('flows-flow-create-modal', FlowsFlowCreateModal);
registerModalKind(FlowsFlowCreateModal.modalKind, 'flows-flow-create-modal');
