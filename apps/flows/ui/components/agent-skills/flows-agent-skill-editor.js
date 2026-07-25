/**
 * Skill detail editor: index fields, body, tool_refs, depends_on, files.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '../editors/flows-code-editor.js';
import '../common/flows-code-language-icon.js';
import './flows-agent-skills-how-it-works.js';
import { asArray, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { buildPlatformAuxiliaryFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { AGENT_SKILL_ICON, mapAgentSkillItem, buildAgentSkillDuplicatePayload, suggestAgentSkillCopyId, isValidAgentSkillId, replaceAttachedAgentSkillId } from '../../_helpers/agent-skill-map.js';
import {
    getToolLabel,
    getToolRefVisualMeta,
    inferToolRefLanguage,
    normalizeToolRef,
} from '../../_helpers/flows-tool-visual.js';

const EMPTY_SCHEMA = Object.freeze({
    type: 'object',
    properties: {},
    additionalProperties: false,
});

function _cloneSkill(skill) {
    return {
        agent_skill_id: skill.agent_skill_id,
        name: skill.name,
        description: skill.description,
        body_markdown: skill.body_markdown,
        tool_refs: Array.isArray(skill.tool_refs)
            ? skill.tool_refs.map((ref) => ({ ...ref }))
            : [],
        depends_on: Array.isArray(skill.depends_on) ? [...skill.depends_on] : [],
        references: Array.isArray(skill.references)
            ? skill.references.map((ref) => ({ ...ref }))
            : [],
        assets: Array.isArray(skill.assets) ? skill.assets.map((ref) => ({ ...ref })) : [],
    };
}

function _draftEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
}

function _toolRefFromSave(updated, previous) {
    const toolId = asString(updated?.tool_id);
    if (toolId.length === 0) {
        throw new Error('flows-agent-skill-editor: onSave tool_id required');
    }
    const description =
        typeof updated.description === 'string' && updated.description.length > 0
            ? updated.description
            : (typeof previous?.description === 'string' ? previous.description : toolId);
    const parameters_schema =
        isPlainObject(updated.parameters_schema)
            ? updated.parameters_schema
            : (isPlainObject(previous?.parameters_schema) ? previous.parameters_schema : { ...EMPTY_SCHEMA });
    return {
        tool_id: toolId,
        description,
        parameters_schema,
    };
}

export class FlowsAgentSkillEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        skill: { type: Object },
        catalogItems: { type: Array, attribute: false },
        _draft: { state: true },
        _dirty: { state: true },
        _duplicateOpen: { state: true },
        _duplicateId: { state: true },
        _duplicateName: { state: true },
        _duplicateBusy: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 0;
                height: 100%;
                overflow: auto;
            }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .toolbar-id {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-family: var(--font-mono);
            }
            .toolbar-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .strip {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
            }
            .stats {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .field-label-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            .field-label {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-secondary);
            }
            .body-editor {
                min-height: 220px;
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--border-subtle);
            }
            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 8px 4px 10px;
                border-radius: var(--radius-full, 999px);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-xs);
                color: var(--text-primary);
                cursor: pointer;
            }
            .chip platform-icon,
            .chip flows-code-language-icon {
                flex-shrink: 0;
            }
            .chip-skill platform-icon {
                color: var(--accent);
            }
            .chip:hover {
                border-color: var(--accent);
            }
            .chip-label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .chip-actions {
                display: flex;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            .files {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .file-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
                cursor: pointer;
            }
            .file-row:hover {
                border-color: var(--accent);
            }
            .file-name {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm);
            }
            .attach-label {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                cursor: pointer;
            }
            .attach-label input {
                display: none;
            }
            .duplicate-panel {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
            }
            .duplicate-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                justify-content: flex-end;
            }
        `,
    ];

    constructor() {
        super();
        this.skill = null;
        this.catalogItems = [];
        this._draft = null;
        this._dirty = false;
        this._duplicateOpen = false;
        this._duplicateId = '';
        this._duplicateName = '';
        this._duplicateBusy = false;
        this._updateOp = this.useOp('flows/agent_skill_update');
        this._skills = this.useResource('flows/agent_skills');
        this._fileUpload = this.useOp('platform/file_create');
    }

    updated(changed) {
        if (changed.has('skill') && this.skill && typeof this.skill === 'object') {
            const next = _cloneSkill(this.skill);
            if (!this._draft || this._draft.agent_skill_id !== next.agent_skill_id || !this._dirty) {
                this._draft = next;
                this._dirty = false;
                this._duplicateOpen = false;
            }
        }
    }

    _patchDraft(patch) {
        if (!this._draft) return;
        this._draft = { ...this._draft, ...patch };
        this._dirty = this.skill ? !_draftEqual(this._draft, _cloneSkill(this.skill)) : true;
    }

    _toolIds() {
        return asArray(this._draft?.tool_refs).map((ref) => asString(ref.tool_id)).filter((id) => id.length > 0);
    }

    _skillLabel(agentSkillId) {
        const id = asString(agentSkillId);
        const found = asArray(this.catalogItems).find((item) => asString(item.agent_skill_id) === id);
        if (found && typeof found.name === 'string' && found.name.length > 0) {
            return found.name;
        }
        return id;
    }

    _toolChipIcon(ref) {
        const normalized = normalizeToolRef(ref);
        if (normalized === null) {
            return html`<platform-icon name="tool" size="14"></platform-icon>`;
        }
        const rawLanguage = inferToolRefLanguage(normalized);
        if (rawLanguage.length > 0) {
            return html`<flows-code-language-icon language=${rawLanguage} size="16"></flows-code-language-icon>`;
        }
        const vm = getToolRefVisualMeta(normalized);
        return html`<platform-icon name=${vm.icon} size="14"></platform-icon>`;
    }

    _onPickTools() {
        this.openModal('flows.tool_picker', {
            pickMode: 'all',
            onPickBatch: (detail) => {
                const batch = Array.isArray(detail)
                    ? detail
                    : (detail && Array.isArray(detail.items) ? detail.items : []);
                const existing = new Set(this._toolIds());
                const nextRefs = [...asArray(this._draft?.tool_refs)];
                for (const item of batch) {
                    const toolId = asString(item?.tool_id || item?.id);
                    if (toolId.length === 0 || existing.has(toolId)) continue;
                    existing.add(toolId);
                    nextRefs.push({
                        tool_id: toolId,
                        description: typeof item.description === 'string' ? item.description : toolId,
                        parameters_schema:
                            item.parameters_schema && typeof item.parameters_schema === 'object'
                                ? item.parameters_schema
                                : { ...EMPTY_SCHEMA },
                    });
                }
                this._patchDraft({ tool_refs: nextRefs });
            },
        });
    }

    _onEditTool(ref) {
        const toolId = asString(ref?.tool_id);
        if (toolId.length === 0) return;
        this.openModal('flows.embedded_tool_config', {
            toolRef: {
                tool_id: toolId,
                description: typeof ref.description === 'string' ? ref.description : toolId,
                parameters_schema:
                    isPlainObject(ref.parameters_schema) ? ref.parameters_schema : { ...EMPTY_SCHEMA },
            },
            nodeId: '',
            onSaved: null,
            focusMode: false,
            flowId: '',
            branchId: 'base',
            onSave: (updated) => {
                if (!isPlainObject(updated)) return;
                const saved = _toolRefFromSave(updated, ref);
                const nextRefs = asArray(this._draft?.tool_refs).map((item) =>
                    item.tool_id === saved.tool_id ? saved : item,
                );
                this._patchDraft({ tool_refs: nextRefs });
            },
        });
    }

    _removeTool(toolId) {
        this._patchDraft({
            tool_refs: asArray(this._draft?.tool_refs).filter((ref) => ref.tool_id !== toolId),
        });
    }

    _onPickDepends() {
        const selfId = asString(this._draft?.agent_skill_id);
        const current = asArray(this._draft?.depends_on).map((id) => asString(id)).filter((id) => id.length > 0);
        this.openModal('flows.agent_skill_picker', {
            excludeIds: [selfId, ...current].filter((id) => id.length > 0),
            onPickBatch: (items) => {
                const batch = asArray(items);
                const existing = new Set(current);
                const next = [...current];
                for (const item of batch) {
                    const id = asString(item?.agent_skill_id);
                    if (id.length === 0 || id === selfId || existing.has(id)) continue;
                    existing.add(id);
                    next.push(id);
                }
                this._patchDraft({ depends_on: next });
            },
        });
    }

    _removeDepends(agentSkillId) {
        const id = asString(agentSkillId);
        this._patchDraft({
            depends_on: asArray(this._draft?.depends_on).filter((x) => asString(x) !== id),
        });
    }

    _onOpenDepends(agentSkillId) {
        const id = asString(agentSkillId);
        if (id.length === 0) {
            throw new Error('flows-agent-skill-editor: depends agent_skill_id required');
        }
        this.openModal('flows.agent_skill_edit', {
            agentSkillId: id,
            onDuplicated: ({ fromId, toId }) => {
                if (typeof fromId !== 'string' || typeof toId !== 'string') {
                    return;
                }
                if (fromId.length === 0 || toId.length === 0 || fromId === toId) {
                    return;
                }
                const current = asArray(this._draft?.depends_on)
                    .map((sid) => asString(sid))
                    .filter((sid) => sid.length > 0);
                this._patchDraft({
                    depends_on: replaceAttachedAgentSkillId(current, fromId, toId),
                });
            },
        });
    }

    async _uploadFile(kind, event) {
        const input = event?.target;
        const file = input?.files?.[0];
        if (!file) return;
        const result = await this._fileUpload.run({
            file,
            spec: buildPlatformAuxiliaryFileCreateSpecJson({
                metadata: {
                    purpose: 'agent_skill_reference',
                    agent_skill_id: asString(this._draft?.agent_skill_id),
                },
            }),
        });
        if (input) input.value = '';
        if (!result || typeof result.file_id !== 'string') {
            this.toast('toast.agent_skill_file_upload_error', { type: 'error' });
            return;
        }
        const ref = {
            file_id: result.file_id,
            original_name: result.original_name,
            url: result.url,
            content_type: result.content_type,
            file_size: result.file_size,
        };
        const key = kind === 'assets' ? 'assets' : 'references';
        this._patchDraft({ [key]: [...asArray(this._draft?.[key]), ref] });
    }

    _removeFile(kind, index) {
        const key = kind === 'assets' ? 'assets' : 'references';
        this._patchDraft({
            [key]: asArray(this._draft?.[key]).filter((_, i) => i !== index),
        });
    }

    _openSkillFile(file) {
        if (!isPlainObject(file) || typeof file.file_id !== 'string' || file.file_id.length === 0) {
            throw new Error('flows-agent-skill-editor: file_id required to open file');
        }
        this.openFile(
            {
                file_id: file.file_id,
                original_name: typeof file.original_name === 'string' ? file.original_name : file.file_id,
                content_type: typeof file.content_type === 'string' ? file.content_type : '',
                file_size: typeof file.file_size === 'number' ? file.file_size : 0,
                url: typeof file.url === 'string' ? file.url : '',
            },
            { source: 'flows_agent_skill' },
        );
    }

    async _save() {
        if (!this._draft || !this._dirty) return;
        const body = {
            name: this._draft.name,
            description: this._draft.description,
            body_markdown: this._draft.body_markdown,
            tool_refs: this._draft.tool_refs,
            depends_on: this._draft.depends_on,
            references: this._draft.references,
            assets: this._draft.assets,
        };
        const result = await this._updateOp.run({
            agent_skill_id: this._draft.agent_skill_id,
            body,
        });
        if (!result) return;
        const item = mapAgentSkillItem(result);
        this._dirty = false;
        this.emit('skills-saved', { agent_skill_id: this._draft.agent_skill_id, item });
        void this._skills.load({ limit: 200, offset: 0 });
    }

    async _delete() {
        if (!this._draft) return;
        const ok = await platformConfirm(
            this.t('agent_skills.delete_confirm', { name: this._draft.name }),
            {
                title: this.t('agent_skills.delete_title'),
                confirmText: this.t('common.action_delete'),
                cancelText: this.t('common.action_cancel'),
                variant: 'danger',
                confirmVariant: 'danger',
            },
        );
        if (!ok) return;
        const requested = this._skills.remove(this._draft.agent_skill_id);
        if (!requested) return;
        this.emit('skills-deleted', { agent_skill_id: this._draft.agent_skill_id });
    }

    _existingSkillIds() {
        const ids = new Set();
        for (const item of asArray(this.catalogItems)) {
            const id = asString(item?.agent_skill_id);
            if (id.length > 0) ids.add(id);
        }
        for (const item of asArray(this._skills.items)) {
            const id = asString(item?.agent_skill_id);
            if (id.length > 0) ids.add(id);
        }
        if (this._draft?.agent_skill_id) {
            ids.add(this._draft.agent_skill_id);
        }
        return ids;
    }

    _openDuplicate() {
        if (!this._draft) return;
        const sourceId = this._draft.agent_skill_id;
        this._duplicateId = suggestAgentSkillCopyId(sourceId, this._existingSkillIds());
        this._duplicateName = `${this._draft.name} (copy)`;
        this._duplicateOpen = true;
    }

    _closeDuplicate() {
        this._duplicateOpen = false;
        this._duplicateBusy = false;
    }

    _canConfirmDuplicate() {
        return (
            isValidAgentSkillId(this._duplicateId)
            && this._duplicateId !== this._draft?.agent_skill_id
            && typeof this._duplicateName === 'string'
            && this._duplicateName.trim().length > 0
            && !this._duplicateBusy
            && !this._skills.createInFlight
        );
    }

    _waitCreated(requestedId) {
        const bus = this._skills.bus;
        const successType = this._skills.resource.events.CREATED;
        const failedType = this._skills.resource.events.CREATE_FAILED;
        return new Promise((resolve, reject) => {
            let offSuccess = null;
            let offFailed = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') offSuccess();
                if (typeof offFailed === 'function') offFailed();
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const item = event.payload && typeof event.payload.item === 'object'
                    ? event.payload.item
                    : null;
                resolve(item);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const message = event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'create failed';
                reject(new Error(message));
            });
        });
    }

    async _confirmDuplicate() {
        if (!this._draft || !this._canConfirmDuplicate()) return;
        const fromId = this._draft.agent_skill_id;
        const payload = buildAgentSkillDuplicatePayload(this._draft, {
            agent_skill_id: this._duplicateId.trim(),
            name: this._duplicateName.trim(),
        });
        this._duplicateBusy = true;
        const requested = this._skills.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            this._duplicateBusy = false;
            return;
        }
        const rawItem = await this._waitCreated(requested.id).finally(() => {
            this._duplicateBusy = false;
        });
        const item = mapAgentSkillItem(rawItem);
        this._duplicateOpen = false;
        this.emit('skills-duplicated', {
            fromId,
            toId: item.agent_skill_id,
            skill: item,
        });
        void this._skills.load({ limit: 200, offset: 0 });
    }

    _renderDuplicatePanel() {
        if (!this._duplicateOpen) {
            return nothing;
        }
        return html`
            <div class="duplicate-panel" data-testid="agent-skill-duplicate-panel">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('agent_skills.duplicate_field_id')}
                    .hint=${this.t('agent_skills.duplicate_field_id_hint')}
                    .value=${this._duplicateId}
                    @change=${(e) => {
                        this._duplicateId = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
                    }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('agent_skills.duplicate_field_name')}
                    .value=${this._duplicateName}
                    @change=${(e) => {
                        this._duplicateName = typeof e.detail?.value === 'string' ? e.detail.value : '';
                    }}
                ></platform-field>
                <div class="duplicate-actions">
                    <platform-button variant="ghost" density="compact" @click=${this._closeDuplicate}>
                        ${this.t('common.action_cancel')}
                    </platform-button>
                    <platform-button
                        variant="primary"
                        density="compact"
                        ?disabled=${!this._canConfirmDuplicate()}
                        @click=${this._confirmDuplicate}
                    >
                        ${this.t('agent_skills.duplicate_confirm')}
                    </platform-button>
                </div>
            </div>
        `;
    }

    _renderFiles(kind) {
        const files = asArray(this._draft?.[kind]);
        return html`
            <div class="field">
                <div class="field-label-row">
                    <span class="field-label">${this.t(kind === 'assets' ? 'agent_skills.field_assets' : 'agent_skills.field_references')}</span>
                    <platform-help-hint .text=${this.t(kind === 'assets' ? 'agent_skills.field_assets_hint' : 'agent_skills.field_references_hint')}></platform-help-hint>
                </div>
                <div class="files">
                    ${files.map((file, index) => html`
                        <div
                            class="file-row"
                            role="button"
                            tabindex="0"
                            @click=${() => this._openSkillFile(file)}
                            @keydown=${(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    this._openSkillFile(file);
                                }
                            }}
                        >
                            <platform-icon name="file" size="16"></platform-icon>
                            <span class="file-name">${file.original_name}</span>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                aria-label=${this.t('agent_skills.file_open')}
                                @click=${(e) => {
                                    e.stopPropagation();
                                    this._openSkillFile(file);
                                }}
                            >
                                <platform-icon name="external-link" size="14"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                aria-label=${this.t('agent_skills.file_remove')}
                                @click=${(e) => {
                                    e.stopPropagation();
                                    this._removeFile(kind, index);
                                }}
                            >
                                <platform-icon name="x" size="14"></platform-icon>
                            </platform-button>
                        </div>
                    `)}
                    <label class="attach-label">
                        <platform-button variant="secondary" density="compact" ?disabled=${this._fileUpload.busy} @click=${(e) => e.currentTarget.parentElement?.querySelector('input')?.click()}>
                            <platform-icon name="paperclip" size="14"></platform-icon>
                            ${this.t('agent_skills.file_attach')}
                        </platform-button>
                        <input type="file" data-canon="composer" @change=${(e) => this._uploadFile(kind, e)} />
                    </label>
                </div>
            </div>
        `;
    }

    render() {
        if (!this._draft) {
            return nothing;
        }
        const draft = this._draft;
        const bodyLen = typeof draft.body_markdown === 'string' ? draft.body_markdown.length : 0;
        const toolsCount = asArray(draft.tool_refs).length;
        const refsCount = asArray(draft.references).length;
        return html`
            <div class="toolbar">
                <span class="toolbar-id">${draft.agent_skill_id}</span>
                <div class="toolbar-actions">
                    <platform-button
                        variant="secondary"
                        density="compact"
                        ?disabled=${this._duplicateBusy || this._skills.createInFlight}
                        @click=${this._openDuplicate}
                    >
                        ${this.t('agent_skills.action_duplicate')}
                    </platform-button>
                    <platform-button
                        variant="primary"
                        density="compact"
                        ?disabled=${!this._dirty || this._updateOp.busy}
                        @click=${this._save}
                    >
                        ${this.t('common.action_save')}
                    </platform-button>
                    <platform-button
                        variant="danger"
                        density="compact"
                        ?disabled=${this._skills.isBusy(draft.agent_skill_id)}
                        @click=${this._delete}
                    >
                        ${this.t('common.action_delete')}
                    </platform-button>
                </div>
            </div>

            ${this._renderDuplicatePanel()}

            <div class="strip">
                <flows-agent-skills-how-it-works compact></flows-agent-skills-how-it-works>
                <div class="stats">
                    <span>${this.t('agent_skills.stat_body', { n: bodyLen })}</span>
                    <span>${this.t('agent_skills.stat_tools', { n: toolsCount })}</span>
                    <span>${this.t('agent_skills.stat_refs', { n: refsCount })}</span>
                </div>
            </div>

            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('agent_skills.field_name')}
                .value=${draft.name}
                @change=${(e) => this._patchDraft({ name: e.detail.value })}
            ></platform-field>

            <platform-field
                type="text"
                mode="edit"
                .label=${this.t('agent_skills.field_description')}
                .hint=${this.t('agent_skills.field_description_hint')}
                .value=${draft.description}
                @change=${(e) => this._patchDraft({ description: e.detail.value })}
            ></platform-field>

            <div class="field">
                <div class="field-label-row">
                    <span class="field-label">${this.t('agent_skills.field_body')}</span>
                    <platform-help-hint .text=${this.t('agent_skills.field_body_hint')}></platform-help-hint>
                </div>
                <div class="body-editor">
                    <flows-code-editor
                        language="text"
                        .value=${draft.body_markdown}
                        @change=${(e) => {
                            const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                            this._patchDraft({ body_markdown: value });
                        }}
                    ></flows-code-editor>
                </div>
            </div>

            <div class="field">
                <div class="field-label-row">
                    <span class="field-label">${this.t('agent_skills.field_tool_refs')}</span>
                    <platform-help-hint .text=${this.t('agent_skills.field_tool_refs_hint')}></platform-help-hint>
                </div>
                <div class="chips">
                    ${asArray(draft.tool_refs).map((ref) => html`
                        <span
                            class="chip"
                            role="button"
                            tabindex="0"
                            @click=${() => this._onEditTool(ref)}
                            @keydown=${(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    this._onEditTool(ref);
                                }
                            }}
                        >
                            ${this._toolChipIcon(ref)}
                            <span class="chip-label">${getToolLabel(ref) || ref.tool_id}</span>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                aria-label=${this.t('agent_skills.tools_remove')}
                                @click=${(e) => {
                                    e.stopPropagation();
                                    this._removeTool(ref.tool_id);
                                }}
                            >
                                <platform-icon name="x" size="12"></platform-icon>
                            </platform-button>
                        </span>
                    `)}
                </div>
                <div class="chip-actions">
                    <platform-button variant="secondary" density="compact" @click=${this._onPickTools}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('agent_skills.tools_add')}
                    </platform-button>
                </div>
            </div>

            <div class="field">
                <div class="field-label-row">
                    <span class="field-label">${this.t('agent_skills.field_depends_on')}</span>
                    <platform-help-hint .text=${this.t('agent_skills.field_depends_on_hint')}></platform-help-hint>
                </div>
                <div class="chips">
                    ${asArray(draft.depends_on).map((depId) => html`
                        <span
                            class="chip chip-skill"
                            role="button"
                            tabindex="0"
                            @click=${() => this._onOpenDepends(depId)}
                            @keydown=${(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    this._onOpenDepends(depId);
                                }
                            }}
                        >
                            <platform-icon name=${AGENT_SKILL_ICON} size="14"></platform-icon>
                            <span class="chip-label">${this._skillLabel(depId)}</span>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="compact"
                                aria-label=${this.t('agent_skills.depends_remove')}
                                @click=${(e) => {
                                    e.stopPropagation();
                                    this._removeDepends(depId);
                                }}
                            >
                                <platform-icon name="x" size="12"></platform-icon>
                            </platform-button>
                        </span>
                    `)}
                </div>
                <div class="chip-actions">
                    <platform-button variant="secondary" density="compact" @click=${this._onPickDepends}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('agent_skills.depends_add')}
                    </platform-button>
                </div>
            </div>

            ${this._renderFiles('references')}
            ${this._renderFiles('assets')}
        `;
    }
}

customElements.define('flows-agent-skill-editor', FlowsAgentSkillEditor);
