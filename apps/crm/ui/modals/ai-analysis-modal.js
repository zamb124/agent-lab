/**
 * CRMAiAnalysisModal — модалка AI-анализа заметки.
 *
 * Props:
 *   - noteId: string — обязательный, id заметки.
 *
 * Поток:
 *   1. На open подгружаем заметку через `entitiesResource.get(noteId)`.
 *      Из `entity.attributes.ai_analysis_draft` достаём текущий черновик
 *      (note + entities + relationships + draft_version).
 *   2. Подписка на WS `crm/note/updated` для noteId — перезагрузка entity
 *      (когда воркер докинул свежий draft или применил его).
 *   3. Действия:
 *      - «Запустить анализ» — `noteAnalyzeStartOp.run({ note_id, mode: 'analyze' })`.
 *      - «Применить» — `noteAnalyzeStartOp.run({ note_id, mode: 'apply' })`.
 *      - per-row «удалить» — кладём draft_entity_id / draft_relationship_id
 *        в локальные _pendingRemoveEntityIds / _pendingRemoveRelIds.
 *      - «Сохранить изменения» — `noteAnalysisDraftSaveOp.run({ note_id, draft })`,
 *        где draft.expected_version берётся из текущего draft.
 *      - «Запустить заново» — повторный analyze поверх той же заметки.
 *   4. Render — двухколоночный layout: левая колонка summary + suggested
 *      tasks; правая — suggested entities/relationships.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const ENTITIES_NAME = 'crm/entities';
const ANALYZE_OP = 'crm/note_analyze_start';
const DRAFT_SAVE_OP = 'crm/note_analysis_draft_save';

const TASK_TYPE = 'task';

function _isObject(value) {
    return typeof value === 'object' && value !== null;
}

function _readDraft(entity) {
    if (entity === null) return null;
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return null;
    const draft = attrs.ai_analysis_draft;
    if (!_isObject(draft)) return null;
    if (typeof draft.draft_version !== 'number') return null;
    return draft;
}

function _isApplied(entity) {
    if (entity === null) return false;
    const attrs = entity.attributes;
    if (!_isObject(attrs)) return false;
    return typeof attrs.ai_analysis_applied_at === 'string'
        && attrs.ai_analysis_applied_at.length > 0
        && _readDraft(entity) === null;
}

export class CRMAiAnalysisModal extends PlatformModal {
    static modalKind = 'crm.ai_analysis';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        noteId: { type: String },
        _pendingRemoveEntityIds: { state: true },
        _pendingRemoveRelIds: { state: true },
        _attrsExpandedIds: { state: true },
        _saveError: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host { --modal-max-width: 1240px; }

            .modal-title-gradient {
                background: var(--crm-main-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                font-weight: 700;
            }

            .body {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
                min-height: 480px;
            }

            .column {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
            }

            .block {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                background: var(--crm-surface-muted);
                padding: var(--space-4);
            }

            .block.summary {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }

            .block-title {
                margin: 0 0 var(--space-3) 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
            }

            .block-title platform-icon {
                color: var(--accent);
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                line-height: 1.45;
                font-size: var(--text-sm);
                white-space: pre-wrap;
            }

            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .empty-state .hint { font-size: var(--text-sm); }

            .loading-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
            }

            .applied-banner {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .items-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 360px;
                overflow-y: auto;
            }

            .item-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .item-row.removed {
                opacity: 0.45;
                text-decoration: line-through;
            }
            .item-row .icon {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-sm);
            }
            .item-row .meta {
                display: grid;
                gap: 2px;
                min-width: 0;
            }
            .item-row .name {
                font-weight: 500;
                color: var(--text-primary);
                font-size: var(--text-sm);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .item-row .sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .item-row .actions {
                display: inline-flex;
                gap: 4px;
                align-items: center;
            }
            .icon-btn {
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-sm);
            }
            .icon-btn:hover { background: var(--crm-surface-muted); color: var(--text-primary); }

            .badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                background: var(--crm-selected-bg);
                color: var(--text-secondary);
                white-space: nowrap;
            }
            .badge.dedup-existing { background: rgba(250, 209, 122, 0.34); color: var(--text-primary); }
            .badge.dedup-new { background: rgba(142, 155, 247, 0.34); color: var(--text-primary); }

            .attrs-preview {
                margin-top: var(--space-2);
                padding: var(--space-2);
                background: var(--crm-surface-muted);
                border-radius: var(--radius-sm);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: pre-wrap;
                max-height: 160px;
                overflow-y: auto;
            }

            .footer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: space-between;
                align-items: center;
                width: 100%;
            }
            .footer-actions .left,
            .footer-actions .right {
                display: flex;
                gap: var(--space-2);
                align-items: center;
            }
            .submit-error {
                color: var(--error);
                font-size: var(--text-sm);
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid transparent;
                background: var(--crm-surface);
                border-color: var(--crm-stroke);
                color: var(--text-secondary);
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--crm-main-gradient);
                border-color: transparent;
                color: white;
                font-weight: 600;
            }
            .btn-primary:hover:not(:disabled) { filter: brightness(1.08); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            @media (max-width: 1024px) {
                .body { grid-template-columns: 1fr; }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.noteId = '';
        this._pendingRemoveEntityIds = [];
        this._pendingRemoveRelIds = [];
        this._attrsExpandedIds = [];
        this._saveError = '';

        this._entities = this.useResource(ENTITIES_NAME);
        this._analyzeOp = this.useOp(ANALYZE_OP);
        this._draftSaveOp = this.useOp(DRAFT_SAVE_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            throw new Error('CRMAiAnalysisModal: prop "noteId" required');
        }

        this._entities.get(this.noteId);

        this.useEvent('crm/note/updated', (event) => {
            const payload = event && event.payload;
            if (!_isObject(payload)) return;
            if (payload.note_id !== this.noteId && payload.entity_id !== this.noteId) return;
            this._entities.get(this.noteId);
        });

        this.useEvent(this._draftSaveOp.op.events.SUCCEEDED, () => {
            this._pendingRemoveEntityIds = [];
            this._pendingRemoveRelIds = [];
            this._saveError = '';
            this._entities.get(this.noteId);
        });
        this.useEvent(this._draftSaveOp.op.events.FAILED, (event) => {
            const payload = event && event.payload;
            const message = _isObject(payload) && typeof payload.message === 'string'
                ? payload.message
                : this.t('ai_analysis_modal.err_save');
            this._saveError = message;
        });
    }

    _entity() {
        const item = this._entities.byId[this.noteId];
        return item === undefined ? null : item;
    }

    _draft() {
        return _readDraft(this._entity());
    }

    _isPendingRemoveEntity(draftEntityId) {
        return this._pendingRemoveEntityIds.indexOf(draftEntityId) !== -1;
    }

    _isPendingRemoveRel(draftRelId) {
        return this._pendingRemoveRelIds.indexOf(draftRelId) !== -1;
    }

    _toggleRemoveEntity(draftEntityId) {
        if (this._isPendingRemoveEntity(draftEntityId)) {
            this._pendingRemoveEntityIds = this._pendingRemoveEntityIds.filter((id) => id !== draftEntityId);
        } else {
            this._pendingRemoveEntityIds = [...this._pendingRemoveEntityIds, draftEntityId];
        }
    }

    _toggleRemoveRel(draftRelId) {
        if (this._isPendingRemoveRel(draftRelId)) {
            this._pendingRemoveRelIds = this._pendingRemoveRelIds.filter((id) => id !== draftRelId);
        } else {
            this._pendingRemoveRelIds = [...this._pendingRemoveRelIds, draftRelId];
        }
    }

    _toggleAttrs(draftEntityId) {
        if (this._attrsExpandedIds.indexOf(draftEntityId) !== -1) {
            this._attrsExpandedIds = this._attrsExpandedIds.filter((id) => id !== draftEntityId);
        } else {
            this._attrsExpandedIds = [...this._attrsExpandedIds, draftEntityId];
        }
    }

    _hasPendingChanges() {
        return this._pendingRemoveEntityIds.length > 0 || this._pendingRemoveRelIds.length > 0;
    }

    _onAnalyze() {
        const entity = this._entity();
        if (entity === null) return;
        this._analyzeOp.run({
            note_id: this.noteId,
            mode: 'analyze',
        });
    }

    _onApply() {
        const draft = this._draft();
        if (draft === null) return;
        if (this._hasPendingChanges()) {
            this._draftSaveOp.run({
                note_id: this.noteId,
                draft: {
                    expected_version: draft.draft_version,
                    remove_entity_draft_ids: this._pendingRemoveEntityIds,
                    remove_relationship_draft_ids: this._pendingRemoveRelIds,
                },
            });
            return;
        }
        this._analyzeOp.run({
            note_id: this.noteId,
            mode: 'apply',
        });
    }

    _onSavePending() {
        const draft = this._draft();
        if (draft === null) return;
        if (!this._hasPendingChanges()) return;
        this._draftSaveOp.run({
            note_id: this.noteId,
            draft: {
                expected_version: draft.draft_version,
                remove_entity_draft_ids: this._pendingRemoveEntityIds,
                remove_relationship_draft_ids: this._pendingRemoveRelIds,
            },
        });
    }

    renderHeader() {
        return html`
            <span style="display:inline-flex;align-items:center;gap:8px;">
                <platform-icon name="sparkle" size="18" style="color: var(--accent);"></platform-icon>
                <span class="modal-title-gradient">${this.t('ai_analysis_modal.header_title')}</span>
            </span>
        `;
    }

    renderBody() {
        const entity = this._entity();
        if (entity === null) {
            return html`
                <div class="loading-state">
                    <glass-spinner></glass-spinner>
                    <span>${this.t('ai_analysis_modal.loading_1')}</span>
                </div>
            `;
        }

        const draft = _readDraft(entity);
        if (draft === null) {
            return this._renderEmptyState(entity);
        }

        return html`
            <div class="body">
                ${this._renderLeftColumn(entity, draft)}
                ${this._renderRightColumn(draft)}
            </div>
        `;
    }

    _renderEmptyState(entity) {
        const applied = _isApplied(entity);
        const analyzing = this._analyzeOp.busy;
        if (analyzing) {
            return html`
                <div class="loading-state">
                    <glass-spinner></glass-spinner>
                    <span>${this.t('ai_analysis_modal.loading_2')}</span>
                </div>
            `;
        }
        if (applied) {
            return html`
                <div class="empty-state">
                    <platform-icon name="check" size="32"></platform-icon>
                    <div class="hint">${this.t('ai_analysis_modal.empty_applied')}</div>
                    <button class="btn" type="button" @click=${() => this._onAnalyze()}>
                        ${this.t('ai_analysis_modal.action_re_analyze')}
                    </button>
                </div>
            `;
        }
        return html`
            <div class="empty-state">
                <platform-icon name="sparkle" size="32"></platform-icon>
                <div class="hint">${this.t('ai_analysis_modal.empty_no_draft')}</div>
                <button class="btn btn-primary" type="button" @click=${() => this._onAnalyze()}>
                    ${this.t('ai_analysis_modal.action_analyze')}
                </button>
            </div>
        `;
    }

    _renderLeftColumn(entity, draft) {
        const summary = this._summaryText(entity, draft);
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const tasks = draftEntities.filter((e) => e.entity_type === TASK_TYPE);
        return html`
            <section class="column">
                <article class="block summary">
                    <h3 class="block-title">
                        <platform-icon name="sparkle" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.block_summary_title')}
                    </h3>
                    <p class="summary-text">${summary}</p>
                </article>
                <article class="block">
                    <h3 class="block-title">
                        <platform-icon name="check-square" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.suggested_tasks_title')}
                    </h3>
                    ${tasks.length === 0
                        ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_tasks')}</div>`
                        : html`<div class="items-list">${tasks.map((t) => this._renderEntityRow(t))}</div>`}
                </article>
            </section>
        `;
    }

    _renderRightColumn(draft) {
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const entities = draftEntities.filter((e) => e.entity_type !== TASK_TYPE);
        const relationships = Array.isArray(draft.relationships) ? draft.relationships : [];
        return html`
            <section class="column">
                <article class="block">
                    <h3 class="block-title">
                        <platform-icon name="link" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.suggested_entities_title')}
                    </h3>
                    ${entities.length === 0
                        ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_entities')}</div>`
                        : html`<div class="items-list">${entities.map((e) => this._renderEntityRow(e))}</div>`}
                </article>
                <article class="block">
                    <h3 class="block-title">
                        <platform-icon name="git-branch" size="14"></platform-icon>
                        ${this.t('ai_analysis_modal.suggested_relationships_title')}
                    </h3>
                    ${relationships.length === 0
                        ? html`<div class="hint" style="color: var(--text-tertiary); font-size: var(--text-sm);">${this.t('ai_analysis_modal.no_relationships')}</div>`
                        : html`<div class="items-list">${relationships.map((r) => this._renderRelRow(r, draft))}</div>`}
                </article>
            </section>
        `;
    }

    _summaryText(entity, draft) {
        if (draft && draft.note && typeof draft.note.description === 'string' && draft.note.description.length > 0) {
            return draft.note.description;
        }
        if (typeof entity.description === 'string' && entity.description.length > 0) {
            return entity.description;
        }
        return this.t('ai_analysis_modal.summary_empty');
    }

    _renderEntityRow(item) {
        const draftId = typeof item.draft_entity_id === 'string' && item.draft_entity_id.length > 0
            ? item.draft_entity_id
            : item.name;
        const removed = this._isPendingRemoveEntity(draftId);
        const expanded = this._attrsExpandedIds.indexOf(draftId) !== -1;
        const name = typeof item.name === 'string' && item.name.length > 0
            ? item.name
            : this.t('ai_analysis_modal.existing_entity_fallback');
        const subtitle = this._entitySubtitle(item);
        const dedup = this._dedupBadge(item);
        const hasAttrs = _isObject(item.attributes) && Object.keys(item.attributes).length > 0;

        return html`
            <div class="item-row ${removed ? 'removed' : ''}">
                <div class="icon">
                    <platform-icon name=${this._iconForType(item.entity_type)} size="14"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${name}</div>
                    <div class="sub">${subtitle}</div>
                    ${expanded && hasAttrs
                        ? html`<pre class="attrs-preview">${JSON.stringify(item.attributes, null, 2)}</pre>`
                        : nothing}
                </div>
                <div class="actions">
                    ${dedup}
                    ${hasAttrs
                        ? html`
                            <button
                                type="button"
                                class="icon-btn"
                                title=${expanded ? this.t('ai_analysis_modal.toggle_attrs_hide') : this.t('ai_analysis_modal.toggle_attrs_show')}
                                @click=${() => this._toggleAttrs(draftId)}
                            >
                                <platform-icon name=${expanded ? 'chevron-up' : 'chevron-down'} size="12"></platform-icon>
                            </button>
                        `
                        : nothing}
                    <button
                        type="button"
                        class="icon-btn"
                        title=${removed ? this.t('ai_analysis_modal.action_undo') : this.t('ai_analysis_modal.action_remove')}
                        @click=${() => this._toggleRemoveEntity(draftId)}
                    >
                        <platform-icon name=${removed ? 'rotate-ccw' : 'close'} size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _renderRelRow(rel, draft) {
        const draftId = rel.draft_relationship_id;
        const removed = this._isPendingRemoveRel(draftId);
        const sourceName = this._draftEntityName(draft, rel.source_draft_entity_id);
        const targetName = this._draftEntityName(draft, rel.target_draft_entity_id);
        const relType = typeof rel.relationship_type === 'string' && rel.relationship_type.length > 0
            ? rel.relationship_type
            : this.t('ai_analysis_modal.relationship_fallback');

        return html`
            <div class="item-row ${removed ? 'removed' : ''}">
                <div class="icon">
                    <platform-icon name="git-branch" size="14"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${this.t('ai_analysis_modal.relationship_line', { source: sourceName, target: targetName })}</div>
                    <div class="sub">${relType}</div>
                </div>
                <div class="actions">
                    <button
                        type="button"
                        class="icon-btn"
                        title=${removed ? this.t('ai_analysis_modal.action_undo') : this.t('ai_analysis_modal.action_remove')}
                        @click=${() => this._toggleRemoveRel(draftId)}
                    >
                        <platform-icon name=${removed ? 'rotate-ccw' : 'close'} size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _entitySubtitle(item) {
        const parts = [];
        if (typeof item.entity_type === 'string' && item.entity_type.length > 0) parts.push(item.entity_type);
        if (typeof item.entity_subtype === 'string' && item.entity_subtype.length > 0) parts.push(item.entity_subtype);
        if (parts.length === 0) return this.t('ai_analysis_modal.object_fallback');
        return parts.join(' · ');
    }

    _dedupBadge(item) {
        if (item.dedup_action === 'merge') {
            const score = typeof item.dedup_confidence === 'number' && Number.isFinite(item.dedup_confidence)
                ? Math.round(item.dedup_confidence * 100)
                : null;
            const label = score !== null
                ? `${this.t('ai_analysis_modal.dedup_existing')} ${score}%`
                : this.t('ai_analysis_modal.dedup_existing');
            return html`<span class="badge dedup-existing">${label}</span>`;
        }
        if (item.dedup_action === 'create') {
            return html`<span class="badge dedup-new">${this.t('ai_analysis_modal.dedup_new')}</span>`;
        }
        return nothing;
    }

    _iconForType(entityType) {
        if (entityType === 'task') return 'check-square';
        if (entityType === 'member') return 'user';
        if (entityType === 'company') return 'building';
        if (entityType === 'meeting') return 'calendar';
        if (entityType === 'note') return 'doc-detail';
        return 'circle';
    }

    _draftEntityName(draft, draftEntityId) {
        if (!_isObject(draft) || typeof draftEntityId !== 'string') {
            return this.t('ai_analysis_modal.existing_entity_fallback');
        }
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const found = draftEntities.find((e) => e.draft_entity_id === draftEntityId);
        if (!_isObject(found)) {
            return this.t('ai_analysis_modal.existing_entity_fallback');
        }
        if (typeof found.name === 'string' && found.name.length > 0) return found.name;
        return this.t('ai_analysis_modal.existing_entity_fallback');
    }

    renderFooter() {
        const draft = this._draft();
        const hasDraft = draft !== null;
        const pending = this._hasPendingChanges();
        const savingPending = this._draftSaveOp.busy;
        const analyzing = this._analyzeOp.busy;

        return html`
            <div class="footer-actions">
                <div class="left">
                    ${this._saveError.length > 0
                        ? html`<span class="submit-error">${this._saveError}</span>`
                        : nothing}
                </div>
                <div class="right">
                    <button type="button" class="btn" @click=${() => this.close()}>
                        ${this.t('ai_analysis_modal.action_close')}
                    </button>
                    ${hasDraft
                        ? html`
                            <button
                                type="button"
                                class="btn"
                                ?disabled=${analyzing}
                                @click=${() => this._onAnalyze()}
                            >
                                ${analyzing
                                    ? this.t('ai_analysis_modal.action_re_analyzing')
                                    : this.t('ai_analysis_modal.action_re_analyze')}
                            </button>
                            ${pending
                                ? html`
                                    <button
                                        type="button"
                                        class="btn"
                                        ?disabled=${savingPending}
                                        @click=${() => this._onSavePending()}
                                    >
                                        ${savingPending
                                            ? this.t('ai_analysis_modal.action_saving')
                                            : this.t('ai_analysis_modal.action_save_changes')}
                                    </button>
                                `
                                : nothing}
                            <button
                                type="button"
                                class="btn btn-primary"
                                ?disabled=${analyzing || savingPending}
                                @click=${() => this._onApply()}
                            >
                                ${this.t('ai_analysis_modal.action_apply')}
                            </button>
                        `
                        : nothing}
                </div>
            </div>
        `;
    }
}

customElements.define('crm-ai-analysis-modal', CRMAiAnalysisModal);
registerModalKind(CRMAiAnalysisModal.modalKind, 'crm-ai-analysis-modal');
