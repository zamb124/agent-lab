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

import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-empty-state.js';
import { getBlankCodeNodeConfig } from '../_helpers/code-node-defaults.js';
import {
    resolveFlowCoverGradient,
    resolveFlowPresetGradient,
} from '../_helpers/flow-cover-gradients.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

function eventPayload(event: unknown): Record<string, unknown> | null {
    if (!isPlainRecord(event) || !isPlainRecord(event.payload)) return null;
    return event.payload;
}

const FLOW_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

interface FlowIdentity {
    flow_id: string;
    name: string;
    description: string;
}

interface FlowBundle {
    bundle_id: string;
    name: unknown;
    description: unknown;
}

const FLOW_PRESETS = Object.freeze([
    {
        id: 'react',
        icon: 'sparkle',
        defaultIdPrefix: 'react_flow',
        buildConfig: ({ flow_id, name, description }: FlowIdentity) => ({
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
        defaultIdPrefix: 'graph_flow',
        buildConfig: ({ flow_id, name, description }: FlowIdentity) => ({
            flow_id, name, description,
            entry: 'start',
            nodes: {
                start: {
                    type: 'code',
                    name: 'Start',
                    config: { ...getBlankCodeNodeConfig(), code: 'async def run(args, state):\n    return state\n' },
                },
                end: {
                    type: 'code',
                    name: 'End',
                    config: { ...getBlankCodeNodeConfig(), code: 'async def run(args, state):\n    return state\n' },
                },
            },
            edges: [{ from_node: 'start', to_node: 'end' }],
            variables: {}, tags: ['preset:graph'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'multi',
        icon: 'agent',
        defaultIdPrefix: 'multi_flow',
        buildConfig: ({ flow_id, name, description }: FlowIdentity) => ({
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
        defaultIdPrefix: 'code_flow',
        buildConfig: ({ flow_id, name, description }: FlowIdentity) => ({
            flow_id, name, description,
            entry: 'compute',
            nodes: {
                compute: {
                    type: 'code',
                    name: 'Compute',
                    config: {
                        ...getBlankCodeNodeConfig(),
                        code: 'async def run(args, state):\n    # TODO: write your logic\n    return state\n',
                    },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:code'], branches: {}, triggers: {}, resources: {},
        }),
    },
    {
        id: 'external',
        icon: 'cloud',
        defaultIdPrefix: 'external_flow',
        buildConfig: ({ flow_id, name, description }: FlowIdentity) => ({
            flow_id, name, description,
            entry: 'start',
            nodes: {
                start: {
                    type: 'code',
                    name: 'Start',
                    config: {
                        ...getBlankCodeNodeConfig(),
                        code: 'async def run(args, state):\n    # TODO: replace with remote_flow node in editor\n    return state\n',
                    },
                },
            },
            edges: [],
            variables: {}, tags: ['preset:external'], branches: {}, triggers: {}, resources: {},
        }),
    },
]);

type FlowPreset = (typeof FLOW_PRESETS)[number];
type FlowCreateSelection =
    | { kind: 'preset'; preset: FlowPreset }
    | { kind: 'bundle'; bundle: FlowBundle };

function isFlowBundle(value: unknown): value is FlowBundle {
    return isPlainRecord(value) && typeof value.bundle_id === 'string' && value.bundle_id.length > 0;
}

export class FlowsFlowCreateModal extends PlatformFormModal {
    static modalKind = 'flows.flow_create';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        _step: { state: true },
        _selection: { state: true },
        _query: { state: true },
        _flowId: { state: true },
        _name: { state: true },
        _description: { state: true },
    }
    declare _step: number;
    declare _selection: FlowCreateSelection | null;
    declare _query: string;
    declare _flowId: string;
    declare _name: string;
    declare _description: string;
;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        glassStyles,
        ...formStyles,
        css`
            :host {
                --modal-width: min(1280px, calc(100vw - 24px));
                --modal-content-inset: 0;
            }
            .modal-title { padding: 0; }
            .head-row { display: flex; flex-direction: column; gap: 2px; }
            .subtitle { color: var(--text-secondary); font-size: var(--text-sm); font-weight: var(--font-normal); }
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
            platform-picker-card {
                min-width: 0;
            }
            .picker-card-icon {
                width: 56px;
                height: 56px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--flows-avatar-text);
            }
            .empty-row {
                grid-column: 1 / -1;
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .form {
                display: flex;
                flex-direction: column;
                gap: 0;
            }
            .form .picked {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-4);
            }
            .form .picked-text { display: flex; flex-direction: column; }
            .form .picked-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .form .picked-sub { font-size: var(--text-xs); color: var(--text-tertiary); }
            .identity-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 0 var(--space-3);
            }
            @media (min-width: 720px) {
                .identity-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            .form .change-link {
                margin-left: auto;
                background: none; border: none;
                color: var(--accent);
                font: inherit; cursor: pointer;
                padding: 0;
            }
        `,
    ];
    private _flows: ResourceController;
    private _bundlesOp: OpController;
    private _installOp: OpController;

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

    override connectedCallback(): void {
        super.connectedCallback();
        void this._bundlesOp.run({});
    }

    _matchQuery(text: unknown) {
        if (this._query.length === 0) return true;
        return String(text).toLowerCase().includes(this._query.toLowerCase());
    }

    _filteredPresets() {
        if (this._query.length === 0) return FLOW_PRESETS;
        return FLOW_PRESETS.filter((preset) => {
            const title = this.t(`flow_create_modal.preset_${preset.id}_title`);
            const desc = this.t(`flow_create_modal.preset_${preset.id}_desc`);
            return this._matchQuery(title) || this._matchQuery(desc) || this._matchQuery(preset.id);
        });
    }

    _bundles(): FlowBundle[] {
        const result = this._bundlesOp.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isFlowBundle);
    }

    _filteredBundles() {
        const items = this._bundles();
        if (this._query.length === 0) return items;
        return items.filter((bundle) => this._matchQuery(bundle.name) || this._matchQuery(bundle.bundle_id) || this._matchQuery(bundle.description));
    }

    _selectPreset(preset: FlowPreset) {
        this._selection = { kind: 'preset', preset };
        this._flowId = `${preset.defaultIdPrefix}_${Date.now().toString(36)}`;
        this._name = this.t(`flow_create_modal.preset_${preset.id}_title`);
        this._description = this.t(`flow_create_modal.preset_${preset.id}_desc`);
        this._step = 2;
        this.isDirty = true;
    }

    _selectBundle(bundle: FlowBundle) {
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

    override renderHeader() {
        return html`
            <div class="head-row">
                <span>${this.t('flow_create_modal.title')}</span>
                ${this._step === 1
                    ? html`<span class="subtitle">${this.t('flow_create_modal.subtitle')}</span>`
                    : ''}
            </div>
        `;
    }

    override renderHeaderActions() {
        if (this._step !== 1) return '';
        return html`
            <platform-modal-search-field
                layout="header"
                .value=${this._query}
                placeholder=${this.t('flow_create_modal.search_placeholder')}
                @change=${(e: CustomEvent) => {
                    const v = e.detail.value;
                    if (typeof v !== 'string') {
                        throw new TypeError('flows-flow-create-modal: search expects string detail.value');
                    }
                    this._query = v;
                }}
            ></platform-modal-search-field>
        `;
    }

    override renderBody() {
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
                    ? html`<platform-empty-state icon="search" title=${this.t('flow_create_modal.empty_search')}></platform-empty-state>`
                    : presets.map((p) => html`
                        <platform-picker-card
                            value=${p.id}
                            title=${this.t(`flow_create_modal.preset_${p.id}_title`)}
                            subtitle=${this.t(`flow_create_modal.preset_${p.id}_desc`)}
                            @select=${() => this._selectPreset(p)}
                        >
                            <div slot="icon" class="picker-card-icon" style=${`background:${resolveFlowPresetGradient(p.id)};`}>
                                <platform-icon name=${p.icon} size="28"></platform-icon>
                            </div>
                        </platform-picker-card>
                    `)}
            </div>

            <div class="section-title">${this.t('flow_create_modal.section_store')}</div>
            ${this._renderStore(bundles)}
        `;
    }

    _renderStore(bundles: readonly FlowBundle[]) {
        if (this._bundlesOp.busy && bundles.length === 0) {
            return html`<div style="padding: var(--space-4); text-align: center"><platform-spinner></platform-spinner></div>`;
        }
        if (bundles.length === 0) {
            return html`<div class="grid"><platform-empty-state icon="apps" title=${this.t('flow_create_modal.store_empty')}></platform-empty-state></div>`;
        }
        return html`
            <div class="grid">
                ${bundles.map((bundle) => html`
                    <platform-picker-card
                        value=${bundle.bundle_id}
                        title=${typeof bundle.name === 'string' && bundle.name !== '' ? bundle.name : bundle.bundle_id}
                        subtitle=${typeof bundle.description === 'string' ? bundle.description : bundle.bundle_id}
                        @select=${() => this._selectBundle(bundle)}
                    >
                        <div slot="icon" class="picker-card-icon" style=${`background:${resolveFlowCoverGradient(bundle.bundle_id)};`}>
                            <platform-icon name="box" size="28"></platform-icon>
                        </div>
                    </platform-picker-card>
                `)}
            </div>
        `;
    }

    _renderForm() {
        const validId = FLOW_ID_PATTERN.test(this._flowId);
        const sel = this._selection;
        const titleKey = sel !== null && sel.kind === 'preset'
            ? `flow_create_modal.preset_${sel.preset.id}_title`
            : null;
        const pickedTitle = titleKey !== null
            ? this.t(titleKey)
            : (sel !== null && sel.kind === 'bundle'
                ? (typeof sel.bundle.name === 'string' && sel.bundle.name !== '' ? sel.bundle.name : sel.bundle.bundle_id)
                : '');
        const pickedSub = sel !== null && sel.kind === 'bundle'
            ? this.t('flow_create_modal.picked_bundle')
            : this.t('flow_create_modal.picked_preset');
        return html`
            <div class="form">
                <div class="picked glass-subtle">
                    <div class="picked-text">
                        <div class="picked-title">${pickedTitle}</div>
                        <div class="picked-sub">${pickedSub}</div>
                    </div>
                    <platform-button variant="ghost" density="compact" @click=${this._backToStep1}>
                        <platform-icon name="arrow-left" size="16"></platform-icon>
                        ${this.t('flow_create_modal.action_return')}
                    </platform-button>
                </div>
                <div class="identity-grid">
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="compact"
                        .label=${this.t('flow_create_modal.field_flow_id')}
                        .value=${this._flowId}
                        placeholder="my_flow"
                        .error=${this._flowId && !validId ? this.t('flow_create_modal.err_flow_id_pattern') : ''}
                        @change=${(e: CustomEvent) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-flow-create-modal: flow_id expects string detail.value');
                            }
                            this._flowId = v;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="compact"
                        .label=${this.t('flow_create_modal.field_name')}
                        .value=${this._name}
                        @change=${(e: CustomEvent) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-flow-create-modal: name expects string detail.value');
                            }
                            this._name = v;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
                <platform-field
                    type="text"
                    mode="edit"
                    pill-density="compact"
                    .label=${this.t('flow_create_modal.field_description')}
                    .value=${this._description}
                    @change=${(e: CustomEvent) => {
                        const v = e.detail.value;
                        if (typeof v !== 'string') {
                            throw new TypeError('flows-flow-create-modal: description expects string detail.value');
                        }
                        this._description = v;
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    override renderFooter() {
        if (this._step === 1) {
            return html`
                <platform-button @click=${() => this.close()}>${this.t('common.action_cancel')}</platform-button>
            `;
        }
        const validId = FLOW_ID_PATTERN.test(this._flowId);
        const valid = validId && this._name.trim().length > 0;
        const isBundle = this._selection !== null && this._selection.kind === 'bundle';
        return html`
            <platform-button @click=${this._backToStep1}>${this.t('flow_create_modal.action_back')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid || this.loading} @click=${this._onSubmit}>
                ${isBundle
                    ? this.t('flow_create_modal.action_install')
                    : this.t('common.action_create')}
            </platform-button>
        `;
    }

    _waitForFlowCreated(flowId: string, triggerCreate: () => unknown) {
        const events = this._flows.resource.events;
        return new Promise((resolve, reject) => {
            let finished = false;
            let offCreated: (() => void) | null = null;
            let offFailed: (() => void) | null = null;
            let timer: number | null = null;
            const cleanup = () => {
                if (offCreated) offCreated();
                if (offFailed) offFailed();
                if (timer) window.clearTimeout(timer);
            };
            const settle = (finish: (value: unknown) => void, value: unknown) => {
                if (finished) return;
                finished = true;
                cleanup();
                finish(value);
            };
            offCreated = this.bus.subscribeType(events.CREATED, (event) => {
                const payload = eventPayload(event);
                const item = payload !== null && isPlainRecord(payload.item) ? payload.item : null;
                if (item !== null && item.flow_id === flowId) {
                    settle(resolve, item);
                }
            });
            offFailed = this.bus.subscribeType(events.CREATE_FAILED, (event) => {
                const payload = eventPayload(event);
                const raw = payload !== null ? payload.message : undefined;
                const message = typeof raw === 'string' && raw !== '' ? raw : this.t('toast.flow_create_error');
                settle(reject, new Error(message));
            });
            timer = window.setTimeout(() => {
                settle(reject, new Error('Timed out waiting for flow creation'));
            }, 30_000);
            try {
                const dispatched = triggerCreate();
                if (dispatched === undefined) {
                    settle(reject, new Error('Flow creation is already in progress'));
                }
            } catch (error) {
                settle(reject, error);
            }
        });
    }

    override async _onSubmit() {
        if (this.loading) return;
        const sel = this._selection;
        if (!sel) return;
        const flow_id = this._flowId.trim();
        const name = this._name.trim();
        this.loading = true;
        try {
            if (sel.kind === 'preset') {
                const config = sel.preset.buildConfig({
                    flow_id,
                    name,
                    description: this._description,
                });
                await this._waitForFlowCreated(config.flow_id, () => this._flows.create(config));
                this.closeAfterSave();
                this.navigate('flow_editor', { flowId: config.flow_id });
                return;
            }
            const result = await this._installOp.run({ flow_id: sel.bundle.bundle_id });
            const installedId = isPlainRecord(result) && typeof result.flow_id === 'string' && result.flow_id !== ''
                ? result.flow_id
                : sel.bundle.bundle_id;
            this.closeAfterSave();
            this._flows.load();
            this.navigate('flow_editor', { flowId: installedId });
        } finally {
            if (this.open) {
                this.loading = false;
            }
        }
    }
}

customElements.define('flows-flow-create-modal', FlowsFlowCreateModal);
registerModalKind(FlowsFlowCreateModal.modalKind, 'flows-flow-create-modal');
