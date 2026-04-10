import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore, isRelationshipSuggestion } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import './entity-modal.js';

export class AIAnalysisModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _suggestions: { state: true },
        _notes: { state: true },
        _currentNoteId: { state: true },
        _entityTypes: { state: true },
        _relationshipTypes: { state: true },
        _taskStates: { state: true },
        _taskDraft: { state: true },
        _saving: { state: true },
        _analyzing: { state: true },
        loading: { type: Boolean },
        _loadingProgress: { state: true },
        _loadingMessageIndex: { state: true },
        _expandedSuggestions: { state: true },
        _attributeDrafts: { state: true },
        _importReviewActive: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host {
                --modal-max-width: 1120px;
                --ai-analysis-save-bg: #7c3aed;
                --ai-analysis-save-hover: #6d28d9;
                --ai-analysis-save-shadow: 0 2px 14px rgba(124, 58, 237, 0.55);
                --ai-analysis-save-shadow-hover: 0 4px 20px rgba(124, 58, 237, 0.65);
            }

            .header-btn.header-save-btn--primary {
                background: var(--ai-analysis-save-bg);
                color: #ffffff;
                box-shadow: var(--ai-analysis-save-shadow);
            }

            .header-btn.header-save-btn--primary:hover:not(:disabled) {
                background: var(--ai-analysis-save-hover);
                color: #ffffff;
                box-shadow: var(--ai-analysis-save-shadow-hover);
            }

            .header-btn.header-save-btn--primary:disabled {
                box-shadow: none;
            }

            .root {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: var(--space-3);
                min-height: 520px;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            .loading-shell {
                width: 100%;
                min-height: 620px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 24px;
            }

            .loading-wrap {
                width: 547px;
                max-width: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 48px;
            }

            .loading-title {
                margin: 0;
                width: 100%;
                text-align: center;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
                color: #99a6f9;
            }

            .loading-percent {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                font-weight: 600;
                color: #99a6f9;
                opacity: 0.95;
            }

            .loading-track {
                width: 100%;
                height: 24px;
                border-radius: 999px;
                background: rgba(34, 34, 34, 0.05);
                position: relative;
                overflow: hidden;
            }

            .loading-fill {
                height: 100%;
                border-radius: inherit;
                background: #99a6f9;
                transition: width 500ms linear;
            }

            .column {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
                min-width: 0;
            }

            .block {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                background: var(--crm-surface-muted);
                padding: var(--space-3);
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }

            .ai-summary {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }

            .block-title {
                margin: 0 0 var(--space-2) 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-2xl);
                font-weight: 700;
                color: var(--text-primary);
            }

            .gradient-title {
                background: var(--accent-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .analysis-header-title {
                display: inline-flex;
                align-items: center;
                gap: 12px;
                font-size: 34px;
                line-height: 1;
                font-weight: 700;
                background: linear-gradient(80.46deg, #FAD17A 9.08%, #FF9A76 44.12%, #99A6F9 85.61%, #99A6F9 85.61%);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .analysis-header-sub {
                font-size: var(--text-lg);
                font-weight: 600;
                color: var(--text-secondary);
                -webkit-text-fill-color: var(--text-secondary);
                background: none;
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                line-height: 1.45;
                font-size: var(--text-base);
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .chips {
                margin-top: var(--space-3);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: var(--text-xs);
                padding: 4px 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-elevated);
            }

            .tasks-wrap {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
            }

            .tasks-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 220px;
                overflow: auto;
                margin-bottom: var(--space-3);
            }

            .task-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-secondary);
            }

            .task-row.done {
                color: var(--text-tertiary);
                text-decoration: line-through;
            }

            .task-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                width: 20px;
                height: 20px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }

            .task-input-wrap {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
                background: var(--crm-surface-elevated);
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                min-height: 40px;
            }

            .task-input {
                border: none;
                background: transparent;
                outline: none;
                color: var(--text-primary);
                width: 100%;
                font-size: var(--text-sm);
            }

            .connections-title {
                margin: 0 0 var(--space-3) 0;
                font-size: 40px;
                line-height: 1.1;
                font-weight: 700;
                color: var(--text-primary);
            }

            .connections-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                overflow: auto;
                min-width: 0;
            }

            .connection-card {
                border-radius: var(--radius-xl);
                padding: 12px;
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                border: none;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }

            .connection-card.blue {
                background: rgba(153, 166, 249, 0.3);
            }

            .connection-card.yellow {
                background: rgba(250, 209, 122, 0.34);
            }

            .connection-card.orange {
                background: rgba(255, 154, 118, 0.28);
            }

            .connection-avatar {
                width: 64px;
                height: 64px;
                border-radius: var(--radius-md);
                background: var(--crm-surface-elevated);
                border: none;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .connection-main {
                flex: 1;
                min-width: 0;
            }

            .connection-name {
                font-weight: 600;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                font-size: var(--text-base);
            }

            .connection-subtitle {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 2px;
            }

            .score-track {
                height: 16px;
                border-radius: var(--radius-full);
                background: var(--glass-tint-strong);
                margin-top: var(--space-2);
                position: relative;
                overflow: hidden;
            }

            .score-fill {
                height: 100%;
                border-radius: inherit;
            }

            .score-fill.blue {
                background: #8e9bf7;
            }

            .score-fill.yellow {
                background: #f0c35f;
            }

            .score-fill.orange {
                background: #f78d61;
            }

            .score-label {
                position: absolute;
                inset: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xs);
                color: var(--text-inverse);
            }

            .connection-actions {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                gap: var(--space-2);
            }

            .new-badge {
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                padding: 3px 10px;
                color: var(--text-primary);
            }

            .new-badge.blue {
                background: #8e9bf7;
                color: #fff;
            }

            .new-badge.yellow {
                background: #f0c35f;
            }

            .new-badge.orange {
                background: #f78d61;
                color: #fff;
            }

            .new-badge.existing {
                background: rgba(250, 209, 122, 0.5);
                color: #5c4700;
            }

            .existing-hint {
                margin-top: 4px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .existing-link {
                border: none;
                background: transparent;
                color: var(--crm-selected-text);
                font-size: var(--text-sm);
                font-weight: var(--font-bold);
                line-height: 1.25;
                padding: 0;
                cursor: pointer;
                text-decoration: none;
                font-family: inherit;
            }

            .existing-link:hover {
                color: var(--platform-btn-primary-hover);
            }

            .remove-connection {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .connection-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
                min-width: 0;
                flex-wrap: wrap;
            }

            .connection-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
                margin-left: auto;
            }

            .relationship-type {
                font-size: var(--text-xs);
                line-height: 16px;
                color: var(--text-tertiary);
                margin-top: 4px;
            }

            .relationship-line {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-top: 4px;
                min-width: 0;
                flex-wrap: wrap;
            }

            .relationship-entity {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: 500;
                max-width: 100%;
            }

            .relationship-arrow {
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
            }

            .relationship-object-link {
                border: none;
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                border-radius: 12px;
                padding: 2px 10px;
                font-size: var(--text-xs);
                line-height: 18px;
                cursor: pointer;
                max-width: 100%;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .relationship-object-link:disabled {
                cursor: not-allowed;
                color: var(--text-disabled);
                background: var(--glass-tint-medium);
            }

            .attr-toggle {
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
                padding: 0;
                margin-top: 6px;
            }

            .attrs-panel {
                margin-top: var(--space-2);
                border-top: 1px solid var(--crm-stroke);
                padding-top: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .attr-row {
                display: grid;
                grid-template-columns: 1fr 1fr auto;
                gap: 8px;
                align-items: center;
            }

            .attr-input {
                border: 1px solid var(--crm-stroke);
                border-radius: 10px;
                height: 30px;
                padding: 0 10px;
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
                font-size: var(--text-xs);
                min-width: 0;
            }

            .attr-input:focus {
                outline: 1px solid var(--accent);
                border-color: transparent;
            }

            .attr-remove {
                width: 24px;
                height: 24px;
                border: none;
                border-radius: 12px;
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .attr-add-row {
                display: grid;
                grid-template-columns: 1fr 1fr auto;
                gap: 8px;
                align-items: center;
            }

            .attr-add-btn {
                border: none;
                border-radius: 16px;
                height: 28px;
                padding: 0 12px;
                background: rgba(153, 166, 249, 0.2);
                color: var(--text-primary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .footer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
                width: 100%;
            }

            .btn-disabled {
                background: var(--glass-tint-subtle);
                color: var(--text-disabled);
            }

            @media (max-width: 1024px) {
                .root {
                    grid-template-columns: minmax(0, 1fr);
                }
                .connections-title {
                    font-size: 30px;
                }
                .block-title {
                    font-size: var(--text-xl);
                }
            }

            @media (max-width: 480px) {
                .connection-avatar {
                    width: 48px;
                    height: 48px;
                }

                .attr-row,
                .attr-add-row {
                    grid-template-columns: 1fr;
                }

                .task-row {
                    grid-template-columns: auto minmax(0, 1fr) auto;
                }

                .task-row span {
                    min-width: 0;
                    overflow-wrap: anywhere;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this._suggestions = [];
        this._notes = [];
        this._currentNoteId = null;
        this._entityTypes = [];
        this._relationshipTypes = [];
        this._taskStates = [];
        this._taskDraft = '';
        this._saving = false;
        this._analyzing = false;
        this.loading = false;
        this._loadingProgress = 0;
        this._loadingMessageIndex = 0;
        this._expandedSuggestions = [];
        this._attributeDrafts = {};
        this._importReviewActive = false;
        this._loadingIntervalId = null;
        this._loadingStartedAt = 0;
        this._unsubscribe = null;
        this.hideHeaderClose = true;
        this.headerSavePrimary = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadTypeMetadata();
        this._initFromStore();
        this._unsubscribe = CRMStore.subscribe(() => {
            this._initFromStore();
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        this._stopLoadingTicker();
    }

    updated() {
        super.updated?.();
        this._syncLoadingTicker();
    }

    _initFromStore() {
        const state = CRMStore.state;
        this._suggestions = Array.isArray(state.ai.suggestions) ? state.ai.suggestions : [];
        this._notes = Array.isArray(state.entities.notes) ? state.entities.notes : [];
        this._currentNoteId = state.entities.currentNoteId;
        this._entityTypes = Array.isArray(state.entities.entityTypes) ? state.entities.entityTypes : [];
        this._relationshipTypes = Array.isArray(state.entities.relationshipTypes) ? state.entities.relationshipTypes : [];
        this._importReviewActive = Boolean(state.ai.importReview);
        const aid = state.ai.analyzingNoteId;
        this._analyzing = typeof aid === 'string' && aid.trim().length > 0;
        const taskSuggestions = this._getTaskSuggestions();
        const currentDoneMap = new Map(this._taskStates.map((task) => [task.id, task.done]));
        this._taskStates = taskSuggestions.map((task) => ({
            id: this._getTaskId(task),
            name: this._getTaskName(task),
            done: this._getTaskDoneState(currentDoneMap, task),
        }));
    }

    _isLoadingActive() {
        return this.loading || this._analyzing;
    }

    _syncLoadingTicker() {
        if (this._isLoadingActive()) {
            this._startLoadingTicker();
            return;
        }
        this._stopLoadingTicker();
    }

    _startLoadingTicker() {
        if (this._loadingIntervalId !== null) {
            return;
        }
        this._loadingStartedAt = Date.now();
        this._loadingProgress = 0;
        this._loadingMessageIndex = 0;
        this._loadingIntervalId = window.setInterval(() => {
            const elapsedMs = Date.now() - this._loadingStartedAt;
            const progress = Math.min(99, Math.floor((elapsedMs / 60000) * 100));
            const messageIndex = Math.floor(elapsedMs / 4500);
            this._loadingProgress = progress;
            this._loadingMessageIndex = messageIndex;
        }, 500);
    }

    _stopLoadingTicker() {
        if (this._loadingIntervalId === null) {
            return;
        }
        window.clearInterval(this._loadingIntervalId);
        this._loadingIntervalId = null;
        this._loadingProgress = 0;
        this._loadingMessageIndex = 0;
    }

    _getLoadingMessage() {
        const messages = [
            this.i18n.t('ai_analysis_modal.loading_1'),
            this.i18n.t('ai_analysis_modal.loading_2'),
            this.i18n.t('ai_analysis_modal.loading_3'),
            this.i18n.t('ai_analysis_modal.loading_4'),
            this.i18n.t('ai_analysis_modal.loading_5'),
        ];
        if (this._loadingProgress >= 99) {
            return messages[messages.length - 1];
        }
        const index = this._loadingMessageIndex % messages.length;
        return messages[index];
    }

    async _loadTypeMetadata() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntityTypes(crmApi);
        await CRMStore.loadRelationshipTypes(crmApi);
    }

    _getTaskId(task) {
        if (typeof task.entity_id === 'string' && task.entity_id.length > 0) {
            return task.entity_id;
        }
        if (typeof task.name === 'string' && task.name.length > 0) {
            return task.name;
        }
        throw new Error('Task suggestion requires entity_id or name');
    }

    _getTaskName(task) {
        if (typeof task.name === 'string' && task.name.length > 0) {
            return task.name;
        }
        return this.i18n.t('ai_analysis_modal.task_fallback');
    }

    _getTaskDoneState(currentDoneMap, task) {
        const taskId = this._getTaskId(task);
        const doneState = currentDoneMap.get(taskId);
        return doneState === true;
    }

    _getCurrentNote() {
        const ir = CRMStore.state.ai.importReview;
        if (ir && ir.anchorNote && typeof ir.anchorNote === 'object') {
            return ir.anchorNote;
        }
        const note = this._notes.find((entry) => entry.entity_id === this._currentNoteId);
        return note === undefined ? null : note;
    }

    _getTaskSuggestions() {
        return this._suggestions.filter((item) => item.entity_type === 'task');
    }

    _getConnectionSuggestions() {
        return this._suggestions.filter((item) => {
            if (isRelationshipSuggestion(item)) {
                return true;
            }
            if (!item.entity_type) {
                return false;
            }
            return item.entity_type !== 'task';
        });
    }

    _onToggleTask(taskId) {
        this._taskStates = this._taskStates.map((task) => (
            task.id === taskId ? { ...task, done: !task.done } : task
        ));
    }

    _onRemoveTask(taskId) {
        this._taskStates = this._taskStates.filter((task) => task.id !== taskId);
    }

    _onTaskDraftInput(event) {
        this._taskDraft = event.target.value;
    }

    _onTaskDraftKeydown(event) {
        if (event.key !== 'Enter') {
            return;
        }
        const value = this._taskDraft.trim();
        if (!value) {
            return;
        }
        const id = `${Date.now()}-${value}`;
        this._taskStates = [...this._taskStates, { id, name: value, done: false }];
        this._taskDraft = '';
    }

    async _onRemoveConnection(index) {
        if (this._importReviewActive) {
            this.error(this.i18n.t('ai_analysis_modal.remove_disabled_import'));
            return;
        }
        const crmApi = this.services.get('crmApi');
        await CRMStore.removeSuggestionWithServerDraftSync(crmApi, index);
    }

    _getSuggestionUiKey(item, index) {
        if (typeof item.entity_id === 'string' && item.entity_id.length > 0) {
            return item.entity_id;
        }
        if (typeof item.name === 'string' && item.name.length > 0) {
            return `${item.name}-${index}`;
        }
        return `${item.entity_type || 'entity'}-${index}`;
    }

    _toggleSuggestionExpanded(key) {
        if (this._expandedSuggestions.includes(key)) {
            this._expandedSuggestions = this._expandedSuggestions.filter((entry) => entry !== key);
            return;
        }
        this._expandedSuggestions = [...this._expandedSuggestions, key];
    }

    _isSuggestionExpanded(key) {
        return this._expandedSuggestions.includes(key);
    }

    _getSuggestionAttributes(item) {
        const attributes = item.attributes;
        if (!attributes || typeof attributes !== 'object' || Array.isArray(attributes)) {
            return [];
        }
        return Object.entries(attributes).filter(([, value]) => (
            typeof value === 'string'
            || typeof value === 'number'
            || typeof value === 'boolean'
        ));
    }

    _onSuggestionNameInput(index, event) {
        CRMStore.updateSuggestion(index, { name: event.target.value });
    }

    _onSuggestionSubtitleInput(index, event) {
        CRMStore.updateSuggestion(index, { description: event.target.value });
    }

    _onAttributeKeyInput(index, oldKey, event) {
        const suggestion = this._suggestions[index];
        if (!suggestion) {
            throw new Error('Suggestion is required');
        }
        const attributes = { ...(suggestion.attributes || {}) };
        const value = attributes[oldKey];
        delete attributes[oldKey];
        const nextKey = event.target.value.trim();
        if (nextKey.length > 0) {
            attributes[nextKey] = value;
        }
        CRMStore.updateSuggestion(index, { attributes });
    }

    _onAttributeValueInput(index, key, event) {
        const suggestion = this._suggestions[index];
        if (!suggestion) {
            throw new Error('Suggestion is required');
        }
        const attributes = { ...(suggestion.attributes || {}) };
        attributes[key] = event.target.value;
        CRMStore.updateSuggestion(index, { attributes });
    }

    _onRemoveAttribute(index, key) {
        const suggestion = this._suggestions[index];
        if (!suggestion) {
            throw new Error('Suggestion is required');
        }
        const attributes = { ...(suggestion.attributes || {}) };
        delete attributes[key];
        CRMStore.updateSuggestion(index, { attributes });
    }

    _onAttributeDraftInput(index, field, event) {
        const previous = this._attributeDrafts[index] || { key: '', value: '' };
        this._attributeDrafts = {
            ...this._attributeDrafts,
            [index]: { ...previous, [field]: event.target.value },
        };
    }

    _onAddAttribute(index) {
        const draft = this._attributeDrafts[index];
        if (!draft) {
            return;
        }
        const key = draft.key.trim();
        if (key.length === 0) {
            return;
        }
        const suggestion = this._suggestions[index];
        if (!suggestion) {
            throw new Error('Suggestion is required');
        }
        const attributes = { ...(suggestion.attributes || {}) };
        attributes[key] = draft.value;
        CRMStore.updateSuggestion(index, { attributes });
        this._attributeDrafts = {
            ...this._attributeDrafts,
            [index]: { key: '', value: '' },
        };
    }

    _buildSummaryTags() {
        const selected = this._suggestions.slice(0, 2);
        return selected.map((item) => {
            if (typeof item.name === 'string' && item.name.length > 0) {
                return item.name;
            }
            if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
                return item.entity_type;
            }
            return 'Entity';
        });
    }

    _getAISummaryText(note) {
        if (note && typeof note === 'object') {
            const attrs = note.attributes;
            if (attrs && typeof attrs === 'object') {
                if (typeof attrs.ai_summary === 'string' && attrs.ai_summary.trim().length > 0) {
                    return attrs.ai_summary.trim();
                }
                const draft = attrs.ai_analysis_draft;
                if (
                    draft
                    && typeof draft === 'object'
                    && draft.note
                    && typeof draft.note === 'object'
                    && typeof draft.note.description === 'string'
                    && draft.note.description.trim().length > 0
                ) {
                    return draft.note.description.trim();
                }
            }
        }
        const noteId = typeof this._currentNoteId === 'string' ? this._currentNoteId : '';
        if (noteId.length > 0) {
            const noteSummary = CRMStore.state.ai.noteSummaries[noteId];
            if (
                noteSummary
                && typeof noteSummary === 'object'
                && typeof noteSummary.summary === 'string'
                && noteSummary.summary.trim().length > 0
            ) {
                return noteSummary.summary.trim();
            }
            const draft = CRMStore.state.ai.draftByNoteId[noteId];
            if (
                draft
                && typeof draft === 'object'
                && draft.note
                && typeof draft.note === 'object'
                && typeof draft.note.description === 'string'
                && draft.note.description.trim().length > 0
            ) {
                return draft.note.description.trim();
            }
        }
        return this.i18n.t('ai_analysis_modal.summary_empty');
    }

    _getScoreValue(item) {
        const raw = item.dedup_confidence;
        if (typeof raw === 'number' && Number.isFinite(raw)) {
            return Math.max(0, Math.min(100, Math.round(raw * 100)));
        }
        return 80;
    }

    _getConnectionTheme(index) {
        if (index % 3 === 0) {
            return 'blue';
        }
        if (index % 3 === 1) {
            return 'yellow';
        }
        return 'orange';
    }

    _getDedupBadge(item) {
        const isExisting = item?.dedup_action === 'merge'
            || (typeof item?.dedup_existing_id === 'string' && item.dedup_existing_id.trim().length > 0)
            || (typeof item?.existing_entity_id === 'string' && item.existing_entity_id.trim().length > 0);
        const confidence = typeof item?.dedup_confidence === 'number' && Number.isFinite(item.dedup_confidence)
            ? Math.max(0, Math.min(100, Math.round(item.dedup_confidence * 100)))
            : null;
        if (isExisting) {
            return {
                label: this.i18n.t('ai_analysis_modal.dedup_existing'),
                className: 'existing',
                confidence,
            };
        }
        return {
            label: this.i18n.t('ai_analysis_modal.dedup_new'),
            className: '',
            confidence: null,
        };
    }

    _getExistingEntityRef(item) {
        const existingId = typeof item?.dedup_existing_id === 'string' && item.dedup_existing_id.trim().length > 0
            ? item.dedup_existing_id
            : (typeof item?.existing_entity_id === 'string' && item.existing_entity_id.trim().length > 0
                ? item.existing_entity_id
                : '');
        const existingName = typeof item?.dedup_existing_name === 'string' && item.dedup_existing_name.trim().length > 0
            ? item.dedup_existing_name
            : (typeof item?.existing_entity_name === 'string' && item.existing_entity_name.trim().length > 0
                ? item.existing_entity_name
                : '');
        return { existingId, existingName };
    }

    _resolveIconName(rawIconName) {
        if (typeof rawIconName !== 'string' || rawIconName.trim().length === 0) {
            return 'folder';
        }
        const iconName = rawIconName.trim();
        if (iconName === 'file') {
            return 'folder';
        }
        if (/^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        const emojiIconAliases = {
            '🤝': 'share',
            '👤': 'user',
            '🏢': 'database',
        };
        const aliasName = emojiIconAliases[iconName];
        return typeof aliasName === 'string' ? aliasName : 'folder';
    }

    _getEntityTypeIcon(typeId) {
        if (typeof typeId !== 'string' || typeId.trim().length === 0) {
            return null;
        }
        const typeConfig = this._entityTypes.find((item) => item?.type_id === typeId);
        if (!typeConfig) {
            return null;
        }
        return this._resolveIconName(typeConfig.icon);
    }

    _getRelationshipTypeIcon(typeId) {
        if (typeof typeId !== 'string' || typeId.trim().length === 0) {
            return null;
        }
        const typeConfig = this._relationshipTypes.find((item) => item?.type_id === typeId);
        if (!typeConfig) {
            return null;
        }
        return this._resolveIconName(typeConfig.icon);
    }

    _getRelationshipTypeLabel(typeId) {
        if (typeof typeId !== 'string' || typeId.trim().length === 0) {
            return this.i18n.t('ai_analysis_modal.relationship_fallback');
        }
        const typeConfig = this._relationshipTypes.find((item) => item?.type_id === typeId);
        if (typeConfig && typeof typeConfig.name === 'string' && typeConfig.name.trim().length > 0) {
            return typeConfig.name;
        }
        return this._humanizeRelationshipTypeId(typeId);
    }

    _humanizeRelationshipTypeId(typeId) {
        const typeAliases = {
            attended: 'ai_analysis_modal.rel_type_attended',
            works_at: 'ai_analysis_modal.rel_type_works_at',
            involved_organization: 'ai_analysis_modal.rel_type_involved_organization',
            documents: 'ai_analysis_modal.rel_type_documents',
            mentions: 'ai_analysis_modal.rel_type_mentions',
        };
        if (Object.prototype.hasOwnProperty.call(typeAliases, typeId)) {
            return this.i18n.t(typeAliases[typeId]);
        }
        const normalized = typeId
            .split('_')
            .map((part) => part.trim())
            .filter((part) => part.length > 0)
            .join(' ');
        if (normalized.length === 0) {
            return this.i18n.t('ai_analysis_modal.relationship_fallback');
        }
        return normalized.charAt(0).toUpperCase() + normalized.slice(1);
    }

    _draftEndpointLabel(draftEntityId) {
        if (typeof draftEntityId !== 'string' || draftEntityId.trim().length === 0) {
            throw new Error('draft_entity_id is required for relationship endpoint');
        }
        const ctx = CRMStore.state.ai.analyzeContextNote;
        if (ctx?.draft_entity_id === draftEntityId) {
            if (typeof ctx.name === 'string' && ctx.name.trim().length > 0) {
                return ctx.name.trim();
            }
            return this.i18n.t('note_content.note_title_fallback');
        }
        const row = this._suggestions.find((s) => s?.draft_entity_id === draftEntityId && s.entity_type);
        if (!row || typeof row.name !== 'string' || row.name.trim().length === 0) {
            throw new Error(`No label for draft_entity_id=${draftEntityId}`);
        }
        return row.name.trim();
    }

    _draftEndpointRealEntityId(draftEntityId) {
        if (typeof draftEntityId !== 'string' || draftEntityId.trim().length === 0) {
            return '';
        }
        if (draftEntityId.startsWith('ki:')) {
            return draftEntityId.slice(3).trim();
        }
        const noteId = typeof this._currentNoteId === 'string' ? this._currentNoteId : '';
        const ctx = CRMStore.state.ai.analyzeContextNote;
        if (ctx?.draft_entity_id === draftEntityId && noteId.length > 0) {
            return noteId;
        }
        const row = this._suggestions.find((s) => s?.draft_entity_id === draftEntityId && s.entity_type);
        if (row?.dedup_action === 'merge' && typeof row.dedup_existing_id === 'string' && row.dedup_existing_id.trim().length > 0) {
            return row.dedup_existing_id.trim();
        }
        const resolved = CRMStore.state.ai.resolvedDraftEntityIds;
        if (resolved && typeof resolved[draftEntityId] === 'string' && resolved[draftEntityId].trim().length > 0) {
            return resolved[draftEntityId].trim();
        }
        return '';
    }

    _getRelationshipDisplay(item) {
        if (!isRelationshipSuggestion(item)) {
            throw new Error('Expected draft relationship (draft_relationship_id)');
        }
        const sourceLabel = this._draftEndpointLabel(item.source_draft_entity_id);
        const targetLabel = this._draftEndpointLabel(item.target_draft_entity_id);
        const targetReal = this._draftEndpointRealEntityId(item.target_draft_entity_id);
        const sourceReal = this._draftEndpointRealEntityId(item.source_draft_entity_id);
        let objectId = '';
        let objectLabel = targetLabel;
        if (targetReal.length > 0) {
            objectId = targetReal;
            objectLabel = targetLabel;
        } else if (sourceReal.length > 0) {
            objectId = sourceReal;
            objectLabel = sourceLabel;
        }
        return {
            sourceLabel,
            targetLabel,
            objectId,
            objectLabel,
        };
    }

    _openEntityModalById(entityId) {
        if (typeof entityId !== 'string' || entityId.trim().length === 0) {
            throw new Error('Entity ID is required');
        }
        CRMStore.setCurrentEntity(entityId);
        const modal = document.createElement('entity-modal');
        modal.entityId = entityId;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _getConnectionIcon(item) {
        if (!item || typeof item !== 'object') {
            throw new Error('Connection item is required');
        }
        if (typeof item.relationship_type === 'string' && item.relationship_type.trim().length > 0) {
            const relationshipIcon = this._getRelationshipTypeIcon(item.relationship_type);
            if (relationshipIcon) {
                return relationshipIcon;
            }
            return 'share';
        }
        const entityTypeId = typeof item.entity_subtype === 'string' && item.entity_subtype.trim().length > 0
            ? item.entity_subtype
            : item.entity_type;
        const entityIcon = this._getEntityTypeIcon(entityTypeId);
        if (entityIcon) {
            return entityIcon;
        }
        if (item.entity_type === 'organization') {
            return 'database';
        }
        if (item.entity_type === 'task') {
            return 'check';
        }
        return 'user';
    }

    renderHeader() {
        const ir = CRMStore.state.ai.importReview;
        return html`
            <span class="analysis-header-title">
                <platform-icon name="ai" size="32" colored></platform-icon>
                ${this.i18n.t('ai_analysis_modal.header_title')}
                ${ir
                    ? html`<span class="analysis-header-sub"> · ${this.i18n.t('ai_analysis_modal.import_review_header_suffix')}</span>`
                    : ''}
            </span>
        `;
    }

    renderBody() {
        if (this.loading || this._analyzing) {
            const progressWidth = Math.max(2, this._loadingProgress);
            return html`
                <div class="loading-shell">
                    <div class="loading-wrap">
                        <h2 class="loading-title">${this._getLoadingMessage()}</h2>
                        <p class="loading-percent">${this._loadingProgress}%</p>
                        <div class="loading-track">
                            <div class="loading-fill" style=${`width:${progressWidth}%;`}></div>
                        </div>
                    </div>
                </div>
            `;
        }

        const note = this._getCurrentNote();
        const noteText = this._getAISummaryText(note);
        const tags = this._buildSummaryTags();
        const connections = this._getConnectionSuggestions();

        return html`
            <div class="root">
                <section class="column">
                    <article class="block ai-summary">
                        <h3 class="block-title gradient-title">
                            <platform-icon name="ai" size="15" colored></platform-icon>
                            ${this.i18n.t('ai_analysis_modal.block_summary_title')}
                        </h3>
                        <p class="summary-text">${noteText}</p>
                        <div class="chips">
                            ${tags.map((tag) => html`
                                <span class="chip">
                                    <platform-icon name="doc-detail" size="11"></platform-icon>
                                    ${tag}
                                </span>
                            `)}
                        </div>
                    </article>

                    <article class="block tasks-wrap">
                        <h3 class="block-title">${this.i18n.t('ai_analysis_modal.suggested_tasks_title')}</h3>
                        <div class="tasks-list">
                            ${this._taskStates.map((task) => html`
                                <label class="task-row ${task.done ? 'done' : ''}">
                                    <input type="checkbox" .checked=${task.done} @change=${() => this._onToggleTask(task.id)} />
                                    <span>${task.name}</span>
                                    <button class="task-remove" type="button" @click=${() => this._onRemoveTask(task.id)}>
                                        <platform-icon name="close" size="12"></platform-icon>
                                    </button>
                                </label>
                            `)}
                        </div>
                        <label class="task-input-wrap">
                            <platform-icon name="ai" size="12" colored></platform-icon>
                            <input
                                class="task-input"
                                type="text"
                                placeholder=${this.i18n.t('ai_analysis_modal.task_input_placeholder')}
                                .value=${this._taskDraft}
                                @input=${this._onTaskDraftInput}
                                @keydown=${this._onTaskDraftKeydown}
                            />
                        </label>
                    </article>
                </section>

                <section class="column">
                    
                    <div class="connections-list">
                        ${connections.map((item, index) => {
                            const suggestionIndex = this._suggestions.indexOf(item);
                            if (suggestionIndex < 0) {
                                throw new Error('Suggestion index is required');
                            }
                            const theme = this._getConnectionTheme(index);
                            const score = this._getScoreValue(item);
                            const uiKey = this._getSuggestionUiKey(item, suggestionIndex);
                            const attributes = this._getSuggestionAttributes(item);
                            const expanded = this._isSuggestionExpanded(uiKey);
                            const draft = this._attributeDrafts[suggestionIndex] || { key: '', value: '' };
                            const subtitle = item.description || this._getConnectionSubtitle(item);
                            const isRelationship = isRelationshipSuggestion(item);
                            const dedupBadge = this._getDedupBadge(item);
                            const existingEntityRef = this._getExistingEntityRef(item);
                            const relationshipTypeLabel = isRelationship
                                ? this._getRelationshipTypeLabel(item.relationship_type)
                                : '';
                            const relationshipDisplay = isRelationship ? this._getRelationshipDisplay(item) : null;
                            return html`
                                <article class="connection-card ${theme}">
                                    <div class="connection-avatar">
                                        <platform-icon name=${this._getConnectionIcon(item)} size="24"></platform-icon>
                                    </div>
                                    <div class="connection-main">
                                        <div class="connection-header">
                                            <div style="min-width:0;flex:1;">
                                                ${isRelationship ? html`
                                                    <div class="connection-name">${relationshipTypeLabel}</div>
                                                    <div class="relationship-type">${this.i18n.t('ai_analysis_modal.relationship_line', { source: relationshipDisplay.sourceLabel, target: relationshipDisplay.targetLabel })}</div>
                                                    <div class="relationship-line">
                                                        <span class="relationship-entity">${relationshipDisplay.sourceLabel}</span>
                                                        <span class="relationship-arrow">
                                                            <platform-icon name="arrow-right" size="12"></platform-icon>
                                                        </span>
                                                        <button
                                                            class="relationship-object-link"
                                                            type="button"
                                                            ?disabled=${relationshipDisplay.objectId.length === 0}
                                                            @click=${() => this._openEntityModalById(relationshipDisplay.objectId)}
                                                            title=${this.i18n.t('ai_analysis_modal.open_entity_title')}
                                                        >
                                                            ${relationshipDisplay.objectLabel}
                                                        </button>
                                                    </div>
                                                ` : html`
                                                    <input
                                                        class="attr-input"
                                                        style="height:28px;font-weight:600;"
                                                        .value=${this._getConnectionName(item)}
                                                        @input=${(event) => this._onSuggestionNameInput(suggestionIndex, event)}
                                                    />
                                                    <input
                                                        class="attr-input"
                                                        style="height:26px;margin-top:4px;"
                                                        .value=${subtitle}
                                                        @input=${(event) => this._onSuggestionSubtitleInput(suggestionIndex, event)}
                                                    />
                                                `}
                                            </div>
                                            <div class="connection-meta">
                                                <span class="new-badge ${theme} ${dedupBadge.className}">
                                                    ${dedupBadge.label}
                                                    ${dedupBadge.confidence !== null ? ` ${dedupBadge.confidence}%` : ''}
                                                </span>
                                                ${this._importReviewActive
                                                    ? null
                                                    : html`
                                                          <button
                                                              class="remove-connection"
                                                              type="button"
                                                              @click=${() => {
                                                                  this._onRemoveConnection(suggestionIndex).catch((err) => {
                                                                      this.error(err?.message || String(err));
                                                                  });
                                                              }}
                                                          >
                                                              <platform-icon name="close" size="14"></platform-icon>
                                                          </button>
                                                      `}
                                            </div>
                                        </div>
                                        ${dedupBadge.className === 'existing' ? html`
                                            <div class="existing-hint">
                                                ${this.i18n.t('ai_entity_card.will_update_prefix')}
                                                ${existingEntityRef.existingId.length > 0 ? html`
                                                    <button
                                                        class="existing-link"
                                                        type="button"
                                                        @click=${() => this._openEntityModalById(existingEntityRef.existingId)}
                                                    >
                                                        ${existingEntityRef.existingName || existingEntityRef.existingId}
                                                    </button>
                                                ` : html`
                                                    ${existingEntityRef.existingName || this.i18n.t('ai_analysis_modal.existing_entity_fallback')}
                                                `}
                                            </div>
                                        ` : ''}
                                        <div class="score-track">
                                            <div class="score-fill ${theme}" style=${`width:${score}%;`}></div>
                                            <div class="score-label">${this.i18n.t('ai_analysis_modal.score_label', { value: String(score) })}</div>
                                        </div>
                                        <button class="attr-toggle" type="button" @click=${() => this._toggleSuggestionExpanded(uiKey)}>
                                            ${expanded ? this.i18n.t('ai_analysis_modal.toggle_attrs_hide') : this.i18n.t('ai_analysis_modal.toggle_attrs_show')}
                                        </button>
                                        ${expanded ? html`
                                            <div class="attrs-panel">
                                                ${attributes.map(([key, value]) => html`
                                                    <div class="attr-row">
                                                        <input
                                                            class="attr-input"
                                                            .value=${String(key)}
                                                            @input=${(event) => this._onAttributeKeyInput(suggestionIndex, key, event)}
                                                        />
                                                        <input
                                                            class="attr-input"
                                                            .value=${String(value)}
                                                            @input=${(event) => this._onAttributeValueInput(suggestionIndex, key, event)}
                                                        />
                                                        <button class="attr-remove" type="button" @click=${() => this._onRemoveAttribute(suggestionIndex, key)}>
                                                            <platform-icon name="close" size="12"></platform-icon>
                                                        </button>
                                                    </div>
                                                `)}
                                                <div class="attr-add-row">
                                                    <input
                                                        class="attr-input"
                                                        placeholder=${this.i18n.t('ai_entity_card.attr_key_placeholder')}
                                                        .value=${draft.key}
                                                        @input=${(event) => this._onAttributeDraftInput(suggestionIndex, 'key', event)}
                                                    />
                                                    <input
                                                        class="attr-input"
                                                        placeholder=${this.i18n.t('ai_entity_card.attr_value_placeholder')}
                                                        .value=${draft.value}
                                                        @input=${(event) => this._onAttributeDraftInput(suggestionIndex, 'value', event)}
                                                    />
                                                    <button class="attr-add-btn" type="button" @click=${() => this._onAddAttribute(suggestionIndex)}>
                                                        ${this.i18n.t('ai_analysis_modal.add_attribute_row')}
                                                    </button>
                                                </div>
                                            </div>
                                        ` : ''}
                                    </div>
                                </article>
                            `;
                        })}
                    </div>
                </section>
            </div>
        `;
    }

    async _onSave() {
        this._saving = true;
        try {
            const crmApi = this.services.get('crmApi');
            if (CRMStore.state.ai.importReview) {
                await CRMStore.persistKnowledgeImportReview(crmApi);
            } else {
                await CRMStore.confirmAllSuggestions(crmApi);
            }
            this.dispatchEvent(new CustomEvent('saved'));
            this.close();
        } catch (error) {
            const message = error instanceof Error
                ? error.message
                : this.i18n.t('ai_analysis_modal.err_save');
            this.error(message);
            throw error;
        } finally {
            this._saving = false;
        }
    }

    _getConnectionName(item) {
        if (typeof item.name === 'string' && item.name.length > 0) {
            return item.name;
        }
        if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
            return item.entity_type;
        }
        return this.i18n.t('ai_analysis_modal.relationship_fallback');
    }

    _getConnectionSubtitle(item) {
        if (typeof item.entity_subtype === 'string' && item.entity_subtype.length > 0) {
            return item.entity_subtype;
        }
        if (typeof item.entity_type === 'string' && item.entity_type.length > 0) {
            return item.entity_type;
        }
        return this.i18n.t('ai_analysis_modal.object_fallback');
    }

    renderSaveHeaderButton() {
        const title = this._saving
            ? this.i18n.t('entity_modal.saving')
            : (CRMStore.state.ai.importReview
                ? this.i18n.t('knowledge_import.detail_approve')
                : this.i18n.t('save', {}, 'common'));
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: this._saving || this._analyzing || this.loading,
            title,
        });
    }

    renderFooter() {
        return html``;
    }
}

customElements.define('ai-analysis-modal', AIAnalysisModal);
