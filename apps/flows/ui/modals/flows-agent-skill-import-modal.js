/**
 * Import Agent Skill from agentskills.io SKILL.md (preview then persist).
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { asArray, asString } from '../_helpers/flows-resolvers.js';
import { mapAgentSkillItem } from '../_helpers/agent-skill-map.js';

export class FlowsAgentSkillImportModal extends PlatformFormModal {
    static modalKind = 'flows.agent_skill_import';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        onImported: { attribute: false },
        _markdown: { state: true },
        _preview: { state: true },
        _step: { state: true },
        _fileName: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        glassStyles,
        css`
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.4;
            }
            .preview {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
            }
            .preview-row {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .preview-label {
                font-size: 11px;
                font-weight: 600;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .preview-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            .file-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .file-row input[type='file'] {
                display: none;
            }
            .file-name {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-family: var(--font-mono);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.onImported = null;
        this._markdown = '';
        this._preview = null;
        this._step = 'paste';
        this._fileName = '';
        this._importOp = this.useOp('flows/agent_skill_import');
        this._skills = this.useResource('flows/agent_skills');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('open') && this.open) {
            this._markdown = '';
            this._preview = null;
            this._step = 'paste';
            this._fileName = '';
            this.isDirty = false;
        }
    }

    renderHeader() {
        return html`<h3>${this.t('agent_skill_import_modal.title')}</h3>`;
    }

    async _onFile(e) {
        const file = e?.target?.files?.[0];
        if (!file) return;
        const text = await file.text();
        this._markdown = text;
        this._fileName = typeof file.name === 'string' ? file.name : '';
        this.isDirty = true;
        e.target.value = '';
    }

    async _previewParse() {
        if (this._markdown.trim().length === 0) return;
        const result = await this._importOp.run({
            markdown: this._markdown,
            persist: false,
        });
        if (!result) {
            this.toast('toast.agent_skill_import_error', { type: 'error' });
            return;
        }
        this._preview = mapAgentSkillItem(result);
        this._step = 'preview';
    }

    async _persist() {
        if (!this._preview) return;
        const result = await this._importOp.run({
            markdown: this._markdown,
            persist: true,
        });
        if (!result) {
            this.toast('toast.agent_skill_import_error', { type: 'error' });
            return;
        }
        const item = mapAgentSkillItem(result);
        this.toast('toast.agent_skill_imported', { type: 'success' });
        void this._skills.load({ limit: 200, offset: 0 });
        if (typeof this.onImported === 'function') {
            this.onImported(item);
        }
        this.closeAfterSave();
    }

    renderBody() {
        if (this._step === 'preview' && this._preview) {
            const p = this._preview;
            const toolIds = asArray(p.tool_refs).map((ref) => asString(ref.tool_id)).filter((id) => id.length > 0);
            return html`
                <div class="stack">
                    <p class="hint">${this.t('agent_skill_import_modal.preview_hint')}</p>
                    <div class="preview">
                        <div class="preview-row">
                            <span class="preview-label">${this.t('agent_skills.field_id')}</span>
                            <span class="preview-value">${p.agent_skill_id}</span>
                        </div>
                        <div class="preview-row">
                            <span class="preview-label">${this.t('agent_skills.field_name')}</span>
                            <span class="preview-value">${p.name}</span>
                        </div>
                        <div class="preview-row">
                            <span class="preview-label">${this.t('agent_skills.field_description')}</span>
                            <span class="preview-value">${p.description}</span>
                        </div>
                        <div class="preview-row">
                            <span class="preview-label">${this.t('agent_skills.field_tool_refs')}</span>
                            <span class="preview-value">${toolIds.length > 0 ? toolIds.join(', ') : this.t('agent_skill_import_modal.none')}</span>
                        </div>
                        <div class="preview-row">
                            <span class="preview-label">${this.t('agent_skills.field_body')}</span>
                            <span class="preview-value">${p.body_markdown.slice(0, 400)}${p.body_markdown.length > 400 ? '…' : ''}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        return html`
            <div class="stack">
                <p class="hint">${this.t('agent_skill_import_modal.intro')}</p>
                <div class="file-row">
                    <platform-button
                        variant="secondary"
                        density="compact"
                        @click=${(e) => e.currentTarget.parentElement?.querySelector('input')?.click()}
                    >
                        <platform-icon name="upload" size="14"></platform-icon>
                        ${this.t('agent_skill_import_modal.choose_file')}
                    </platform-button>
                    <input
                        type="file"
                        accept=".md,text/markdown,text/plain"
                        data-canon="composer"
                        @change=${this._onFile}
                    />
                    ${this._fileName
                        ? html`<span class="file-name">${this._fileName}</span>`
                        : nothing}
                </div>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('agent_skill_import_modal.field_markdown')}
                    .placeholder=${this.t('agent_skill_import_modal.field_markdown_placeholder')}
                    .value=${this._markdown}
                    @change=${(e) => {
                        this._markdown = typeof e.detail?.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    renderFooter() {
        if (this._step === 'preview') {
            return html`
                <platform-button variant="ghost" @click=${() => { this._step = 'paste'; this._preview = null; }}>
                    ${this.t('agent_skill_import_modal.back')}
                </platform-button>
                <platform-button
                    variant="primary"
                    ?disabled=${this._importOp.busy}
                    @click=${() => this._persist()}
                >
                    ${this.t('agent_skill_import_modal.persist')}
                </platform-button>
            `;
        }
        return html`
            <platform-button variant="ghost" @click=${() => this.close()}>
                ${this.t('common.action_cancel')}
            </platform-button>
            <platform-button
                variant="primary"
                ?disabled=${this._markdown.trim().length === 0 || this._importOp.busy}
                @click=${() => this._previewParse()}
            >
                ${this.t('agent_skill_import_modal.preview')}
            </platform-button>
        `;
    }
}

customElements.define('flows-agent-skill-import-modal', FlowsAgentSkillImportModal);
registerModalKind(FlowsAgentSkillImportModal.modalKind, 'flows-agent-skill-import-modal');
