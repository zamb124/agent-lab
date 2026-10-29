/**
 * flows-agent-focus-studio — полноэкранный редактор single llm_node.
 *
 * Заменяет канву/палитру/floating panel когда editorLayout === 'agent'.
 * Хостит flows-property-panel с focusMode; секции через segmented control.
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    EDITOR_LAYOUT_CANVAS,
    getSoleNodeId,
    writeEditorLayoutPreference,
} from '../../_helpers/flow-editor-layout.js';
import './flows-property-panel.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

const FOCUS_SECTIONS = Object.freeze(['prompt', 'model', 'skills_tools', 'advanced']);

export class FlowsAgentFocusStudio extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String },
        branchId: { type: String },
        _focusSection: { state: true, type: String },
    }
    declare flowId: string;
    declare branchId: string;
    declare _focusSection: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
                position: relative;
                overflow: hidden;
                animation: studio-enter 220ms ease-out;
            }

            @keyframes studio-enter {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .studio-atmosphere {
                pointer-events: none;
                position: absolute;
                inset: 0;
                background:
                    radial-gradient(
                        120% 80% at 12% -10%,
                        color-mix(in srgb, var(--accent) 14%, transparent) 0%,
                        transparent 55%
                    ),
                    radial-gradient(
                        90% 70% at 88% 110%,
                        color-mix(in srgb, var(--accent-secondary, var(--info)) 10%, transparent) 0%,
                        transparent 50%
                    ),
                    var(--bg-elevated);
                z-index: 0;
            }

            .studio-chrome {
                position: relative;
                z-index: 1;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-5);
                border-bottom: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-solid-medium) 88%, transparent);
                backdrop-filter: blur(12px);
                min-height: var(--flows-chrome-row-min-height, 52px);
            }

            .studio-identity {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-width: 0;
            }

            .studio-badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--accent) 12%, var(--bg-elevated));
                color: var(--accent);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: 0.02em;
                text-transform: uppercase;
                flex-shrink: 0;
            }

            .studio-title {
                min-width: 0;
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .studio-chrome-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .studio-run-host {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--platform-button-icon-size, 36px);
            }

            .studio-run-host:empty {
                display: none;
            }

            .layout-toggle {
                transition: transform 120ms ease;
            }

            .layout-toggle:active {
                transform: scale(0.94);
            }

            .studio-nav {
                position: relative;
                z-index: 1;
                flex-shrink: 0;
                display: flex;
                justify-content: center;
                padding: var(--space-3) var(--space-5) var(--space-2);
            }

            .studio-stage {
                position: relative;
                z-index: 1;
                flex: 1;
                min-height: 0;
                min-width: 0;
                display: flex;
                flex-direction: column;
                padding: var(--space-2) var(--space-5) var(--space-5);
            }

            .studio-stage-inner {
                flex: 1;
                min-height: 0;
                min-width: 0;
                display: flex;
                flex-direction: column;
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--glass-solid-medium) 70%, transparent);
                border: 1px solid var(--border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                overflow: auto;
                padding: var(--space-4);
                padding-bottom: var(--space-8);
            }

            .studio-stage-inner[data-section='prompt'] {
                padding: var(--space-3);
            }

            flows-property-panel {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _flows: ResourceController;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._focusSection = 'prompt';
        this._editor = this.useOp('flows/editor');
        this._flows = this.useResource('flows/flows');
    }

    _flowName() {
        const state = asObject(this._editor.state);
        const flowConfig = isPlainObject((state as any).flowConfig) ? (state as any).flowConfig : null;
        if (flowConfig !== null) {
            const name = asString(flowConfig.name);
            if (name.length > 0) {
                return name;
            }
            const flowId = asString(flowConfig.flow_id);
            if (flowId.length > 0) {
                return flowId;
            }
        }
        const flowId = asString(this.flowId);
        if (flowId.length > 0) {
            const cached = this._flows.byId && this._flows.byId[flowId]
                ? this._flows.byId[flowId]
                : null;
            if (isPlainObject(cached) && asString(cached.name).length > 0) {
                return asString(cached.name);
            }
            return flowId;
        }
        return this.t('agent_focus.untitled');
    }

    _soleNodeId() {
        const state = asObject(this._editor.state);
        const branchData = isPlainObject((state as any).branchData) ? (state as any).branchData : null;
        if (branchData === null) {
            throw new Error('flows-agent-focus-studio: branchData is required');
        }
        return getSoleNodeId(branchData);
    }

    _onSectionChange(e: CustomEvent) {
        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        if (!FOCUS_SECTIONS.includes(value)) {
            throw new Error(`flows-agent-focus-studio: invalid section "${value}"`);
        }
        this._focusSection = value;
    }

    _switchToCanvas() {
        const flowId = asString(this.flowId);
        if (flowId.length === 0) {
            throw new Error('flows-agent-focus-studio: flowId is required to switch layout');
        }
        writeEditorLayoutPreference(flowId, EDITOR_LAYOUT_CANVAS);
        (this._editor.setEditorLayout({ layout: EDITOR_LAYOUT_CANVAS }) as any);
    }

    _toggleExecutionPanel() {
        const state = asObject(this._editor.state);
        (this._editor.setExecutionPanelOpen as any)({ open: !Boolean((state as any).executionPanelOpen) });
    }

    override render(): TemplateResult {
        const nodeId = this._soleNodeId();
        const section = FOCUS_SECTIONS.includes(this._focusSection)
            ? this._focusSection
            : 'prompt';
        const executionOpen = Boolean((asObject(this._editor.state) as any).executionPanelOpen);
        return html`
            <div class="studio-atmosphere" aria-hidden="true"></div>
            <div class="studio-chrome">
                <div class="studio-identity">
                    <span class="studio-badge">
                        <platform-icon name="llm_node" size="14"></platform-icon>
                        ${this.t('agent_focus.badge')}
                    </span>
                    <div class="studio-title">${this._flowName()}</div>
                </div>
                <div class="studio-chrome-actions">
                    <div class="studio-run-host"></div>
                    <platform-button
                        class="layout-toggle"
                        variant=${executionOpen ? 'secondary' : 'ghost'}
                        density="compact"
                        icon-only
                        title=${executionOpen
                            ? this.t('canvas.toolbar.close_execution_panel')
                            : this.t('canvas.toolbar.open_execution_panel')}
                        aria-label=${executionOpen
                            ? this.t('canvas.toolbar.close_execution_panel')
                            : this.t('canvas.toolbar.open_execution_panel')}
                        @click=${() => this._toggleExecutionPanel()}
                    >
                        <platform-icon name="chat" size="18"></platform-icon>
                    </platform-button>
                    <platform-button
                        class="layout-toggle"
                        variant="secondary"
                        density="compact"
                        icon-only
                        title=${this.t('agent_focus.flow_settings')}
                        aria-label=${this.t('agent_focus.flow_settings_aria')}
                        @click=${() => this.emit('toggle-flow-settings')}
                    >
                        <platform-icon name="settings" size="18"></platform-icon>
                    </platform-button>
                    <platform-button
                        class="layout-toggle"
                        variant="secondary"
                        density="compact"
                        icon-only
                        title=${this.t('agent_focus.to_canvas')}
                        aria-label=${this.t('agent_focus.to_canvas_aria')}
                        @click=${() => this._switchToCanvas()}
                    >
                        <platform-icon name="workflow" size="18"></platform-icon>
                    </platform-button>
                </div>
            </div>
            <div class="studio-nav">
                <platform-segmented-control
                    density="compact"
                    .value=${section}
                    .items=${[
                        { value: 'prompt', label: this.t('agent_focus.section_prompt') },
                        { value: 'model', label: this.t('agent_focus.section_model') },
                        { value: 'skills_tools', label: this.t('agent_focus.section_skills_tools') },
                        { value: 'advanced', label: this.t('agent_focus.section_advanced') },
                    ]}
                    aria-label=${this.t('agent_focus.sections_aria')}
                    @change=${(e: CustomEvent) => this._onSectionChange(e)}
                ></platform-segmented-control>
            </div>
            <div class="studio-stage">
                <div class="studio-stage-inner" data-section=${section}>
                    <flows-property-panel
                        .flowId=${this.flowId}
                        .branchId=${this.branchId}
                        .nodeId=${nodeId}
                        ?focusMode=${true}
                        .focusSection=${section}
                    ></flows-property-panel>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-agent-focus-studio', FlowsAgentFocusStudio);
