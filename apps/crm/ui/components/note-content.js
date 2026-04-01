import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

function getLocalIsoDate() {
    const now = new Date();
    const year = String(now.getFullYear());
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

export class NoteContent extends PlatformElement {
    static properties = {
        note: { type: Object },
        relatedEntities: { type: Array },
        relationships: { type: Array },
        attachments: { type: Array },
        entityTypes: { type: Array },
        relationshipTypes: { type: Array },
        noteSubtypes: { type: Array },
        summaryText: { type: String },
        summaryGeneratedAt: { type: String },
        summaryEntities: { type: Array },
        hasAnalysisDraft: { type: Boolean },
        analysisDraftGeneratedAt: { type: String },
        processingEntities: { type: Boolean },
        deletingNote: { type: Boolean },
        editable: { type: Boolean },
        savingNote: { type: Boolean },
        draftMode: { type: Boolean },
        processingAttachment: { type: Boolean },
        processingRelationship: { type: Boolean },
        _draftTitle: { state: true },
        _draftText: { state: true },
        _draftSubtype: { state: true },
        _draftNoteDate: { state: true },
        _draftVoiceMode: { state: true },
        _draftManualVoiceId: { state: true },
        _draftContextEntityId: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                min-height: 0;
            }

            .layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 440px;
                gap: 24px;
                align-items: stretch;
                height: 100%;
                min-height: 0;
                overflow-x: hidden;
            }

            .note-main {
                display: flex;
                flex-direction: column;
                gap: 24px;
                min-height: 0;
                min-width: 0;
            }

            .note-main.is-editing {
                display: grid;
                grid-template-rows: auto minmax(0, 1fr);
                gap: 16px;
                min-height: 0;
                height: 100%;
            }

            .note-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 24px;
            }

            .note-title-wrap {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
                flex: 1;
            }

            .note-title {
                margin: 0;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
                color: var(--text-primary);
            }

            .note-date {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                color: rgba(34, 34, 34, 0.3);
            }

            .note-subtype {
                margin: 0;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: 13px;
                line-height: 16px;
                color: rgba(34, 34, 34, 0.55);
            }

            .note-edit-meta {
                margin-top: 8px;
                display: grid;
                grid-template-columns: minmax(0, 240px) minmax(0, 220px);
                gap: 12px;
                align-items: center;
                max-width: 520px;
            }

            .note-subtype-select {
                min-width: 0;
            }

            .note-date-picker {
                min-width: 0;
                --platform-date-picker-labeled-bg: rgba(34, 34, 34, 0.04);
                --platform-date-picker-labeled-border: rgba(34, 34, 34, 0.06);
                --platform-date-picker-labeled-height: 44px;
                --platform-date-picker-labeled-padding: 0 12px;
                --platform-date-picker-label-size: var(--text-xs);
                --platform-date-picker-value-size: var(--text-lg);
            }

            .note-actions {
                display: inline-flex;
                align-items: center;
                gap: 16px;
                flex-wrap: wrap;
                justify-content: flex-end;
            }

            .round-btn {
                width: 44px;
                height: 44px;
                border: 1px solid var(--crm-stroke);
                border-radius: 22px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }

            .round-btn:hover {
                background: var(--crm-surface);
                border-color: var(--crm-stroke-strong);
                color: var(--text-primary);
            }

            .round-btn:disabled {
                opacity: 0.55;
                cursor: not-allowed;
            }

            .refresh-icon.spinning {
                animation: note-refresh-spin 0.9s linear infinite;
                transform-origin: center;
            }

            @keyframes note-refresh-spin {
                from {
                    transform: rotate(0deg);
                }
                to {
                    transform: rotate(360deg);
                }
            }

            .round-btn.danger {
                background: rgba(255, 136, 92, 0.15);
                color: #ff885c;
            }

            .attach-dropdown {
                position: relative;
            }

            .attach-header-btn {
                position: relative;
            }

            .attach-count-badge {
                position: absolute;
                top: -2px;
                right: -2px;
                min-width: 18px;
                height: 18px;
                padding: 0 5px;
                border-radius: 9px;
                background: #99a6f9;
                color: #222222;
                font-size: 11px;
                font-weight: 600;
                line-height: 18px;
                text-align: center;
                pointer-events: none;
                box-sizing: border-box;
            }

            .attach-dropdown-panel {
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: 0;
                min-width: 260px;
                max-width: min(320px, 92vw);
                max-height: 240px;
                overflow-y: auto;
                padding: 8px;
                border-radius: 12px;
                background: var(--crm-surface-elevated);
                border: 1px solid var(--crm-stroke);
                box-shadow: 0 8px 24px rgba(34, 34, 34, 0.12);
                z-index: 40;
                opacity: 0;
                visibility: hidden;
                transform: translateY(-4px);
                transition: opacity var(--duration-fast), visibility var(--duration-fast), transform var(--duration-fast);
                pointer-events: none;
            }

            .attach-dropdown:hover .attach-dropdown-panel {
                opacity: 1;
                visibility: visible;
                transform: translateY(0);
                pointer-events: auto;
            }

            .attach-dropdown-empty {
                padding: 8px 10px;
                font-size: 13px;
                line-height: 18px;
                color: rgba(34, 34, 34, 0.45);
            }

            .attach-dropdown-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                padding: 6px 8px;
                border-radius: 8px;
                min-height: 32px;
            }

            .attach-dropdown-row:hover {
                background: rgba(34, 34, 34, 0.05);
            }

            .attach-dropdown-name {
                min-width: 0;
                flex: 1;
                font-size: 13px;
                line-height: 18px;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .attach-dropdown-remove {
                flex-shrink: 0;
                width: 28px;
                height: 28px;
                border: none;
                border-radius: 8px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                background: transparent;
                color: rgba(34, 34, 34, 0.35);
            }

            .attach-dropdown-remove:hover {
                background: rgba(255, 136, 92, 0.15);
                color: #ff885c;
            }

            .attach-dropdown-remove:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }

            .round-btn.analysis-draft {
                background: rgba(255, 136, 92, 0.18);
                color: var(--crm-button-secondary-bg);
                border: 1px solid rgba(255, 136, 92, 0.45);
            }

            .edit-btn {
                height: 44px;
                border: none;
                border-radius: 22px;
                padding: 0 24px;
                background: #99a6f9;
                color: #ffffff;
                font-size: 16px;
                line-height: 20px;
                cursor: pointer;
            }

            .edit-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .cancel-btn {
                height: 44px;
                border: 1px solid var(--crm-button-secondary-bg);
                border-radius: 22px;
                padding: 0 18px;
                background: var(--crm-button-secondary-bg);
                color: var(--crm-button-secondary-text);
                font-size: 14px;
                line-height: 18px;
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast);
            }

            .cancel-btn:hover {
                background: var(--crm-button-secondary-hover);
                border-color: var(--crm-button-secondary-hover);
            }

            .cancel-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .note-text {
                margin: 0;
                white-space: pre-wrap;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
                overflow-wrap: anywhere;
                word-break: break-word;
                max-width: 100%;
            }

            .note-markdown {
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                overflow-wrap: anywhere;
                word-break: break-word;
                max-width: 100%;
            }

            .note-markdown > :first-child {
                margin-top: 0;
            }

            .note-markdown > :last-child {
                margin-bottom: 0;
            }

            .note-markdown p,
            .note-markdown ul,
            .note-markdown ol,
            .note-markdown blockquote,
            .note-markdown pre,
            .note-markdown h1,
            .note-markdown h2,
            .note-markdown h3,
            .note-markdown h4 {
                margin: 0 0 12px 0;
            }

            .note-markdown ul,
            .note-markdown ol {
                padding-left: 20px;
            }

            .note-markdown code {
                background: rgba(34, 34, 34, 0.06);
                border-radius: 6px;
                padding: 1px 6px;
                font-size: 0.92em;
            }

            .note-markdown pre {
                background: rgba(34, 34, 34, 0.06);
                border-radius: 10px;
                padding: 12px;
                overflow: auto;
            }

            .note-markdown pre code {
                background: transparent;
                border-radius: 0;
                padding: 0;
            }

            .note-title-input {
                width: min(560px, 100%);
                padding: 8px 12px;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
            }

            .note-text-input {
                width: 100%;
                min-height: 180px;
                resize: vertical;
                font-size: 16px;
                line-height: 20px;
                white-space: pre-wrap;
                overflow-x: hidden;
                overflow-y: auto;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .note-main.is-editing .note-text-input {
                height: 100%;
                min-height: 260px;
                max-height: 100%;
            }

            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 24px;
                min-height: 0;
                min-width: 0;
            }

            .card {
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                min-width: 0;
            }

            .summary-card {
                background: var(--crm-surface-elevated);
                border: 1px solid rgba(153, 166, 249, 0.4);
            }

            .tasks-card {
                background: rgba(34, 34, 34, 0.05);
            }

            .entities-section {
                display: flex;
                flex-direction: column;
                gap: 20px;
                padding-bottom: 24px;
            }

            .relationships-section {
                display: flex;
                flex-direction: column;
                gap: 12px;
                padding-bottom: 8px;
            }

            .section-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
            }

            .card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }

            .summary-actions {
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }

            .summary-title {
                margin: 0;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                background: linear-gradient(80.46deg, #fad17a 9.08%, #ff9a76 44.12%, #99a6f9 85.61%);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .summary-meta {
                margin: 0;
                color: rgba(34, 34, 34, 0.3);
                font-size: 12px;
                line-height: 15px;
            }

            .summary-text {
                margin: 0;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
            }

            .summary-tag {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 12px;
                min-height: 24px;
                border-radius: 14px;
                font-size: 12px;
                line-height: 15px;
                background: #99a6f9;
                color: rgba(34, 34, 34, 0.95);
            }

            .tasks-title,
            .entities-title,
            .relationships-title {
                margin: 0;
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
            }

            .tasks-list {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .task-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                min-height: 32px;
            }

            .task-main {
                display: inline-flex;
                align-items: center;
                gap: 12px;
                min-width: 0;
                flex: 1;
            }

            .checkbox {
                width: 24px;
                height: 24px;
                border-radius: 4px;
                flex-shrink: 0;
                border: 2px solid rgba(34, 34, 34, 0.05);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .checkbox.checked {
                background: #99a6f9;
                border-color: #99a6f9;
                color: #ffffff;
            }

            .task-text {
                min-width: 0;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .task-text.completed {
                color: rgba(34, 34, 34, 0.2);
                text-decoration: line-through;
            }

            .task-remove {
                width: 24px;
                height: 24px;
                border: none;
                border-radius: 12px;
                background: transparent;
                color: rgba(34, 34, 34, 0.2);
                flex-shrink: 0;
            }

            .entity-link {
                border: none;
                width: 100%;
                text-align: left;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                padding: 12px;
                border-radius: 16px;
                cursor: pointer;
                background: rgba(153, 166, 249, 0.2);
                transition: transform var(--duration-fast), filter var(--duration-fast);
            }

            .entity-link:hover {
                transform: translateY(-1px);
                filter: brightness(0.99);
            }

            .entity-link.tone-yellow {
                background: rgba(250, 209, 122, 0.3);
            }

            .entity-link.tone-orange {
                background: rgba(255, 136, 92, 0.2);
            }

            .entity-avatar {
                width: 64px;
                height: 64px;
                border-radius: 12px;
                overflow: hidden;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(312.35deg, #fad17a 18.71%, #ff9a76 82.25%, #99a6f9 157.48%);
                color: #222222;
            }

            .entity-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .entity-data {
                display: flex;
                flex-direction: column;
                gap: 12px;
                min-width: 0;
                flex: 1;
            }

            .entity-name {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                font-weight: 600;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .entity-subtitle {
                margin: 0;
                font-size: 12px;
                line-height: 12px;
                color: rgba(34, 34, 34, 0.2);
            }

            .entity-score {
                height: 16px;
                border-radius: 8px;
                background: rgba(34, 34, 34, 0.05);
                overflow: hidden;
                position: relative;
            }

            .entity-score-fill {
                height: 100%;
                background: #99a6f9;
            }

            .entity-score-fill.tone-yellow {
                background: #fad17a;
            }

            .entity-score-fill.tone-orange {
                background: #ff885c;
            }

            .relationship-link {
                border: none;
                width: 100%;
                text-align: left;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                padding: 12px;
                border-radius: 16px;
                cursor: pointer;
                background: rgba(153, 166, 249, 0.2);
                transition: transform var(--duration-fast), filter var(--duration-fast);
            }

            .relationship-link:hover {
                transform: translateY(-1px);
                filter: brightness(0.99);
            }

            .relationship-avatar {
                width: 56px;
                height: 56px;
                border-radius: 12px;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: rgba(255, 255, 255, 0.65);
                color: #222222;
            }

            .relationship-data {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
                flex: 1;
            }

            .relationship-name {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                font-weight: 600;
                color: var(--text-primary);
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .relationship-subtitle {
                margin: 0;
                font-size: 12px;
                line-height: 16px;
                color: rgba(34, 34, 34, 0.55);
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .relationship-entities {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                flex-wrap: wrap;
            }

            .relationship-entity-btn {
                border: none;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.75);
                color: var(--text-primary);
                padding: 4px 8px;
                font-size: 12px;
                line-height: 16px;
                cursor: pointer;
            }

            .relationship-entity-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .relationship-weight {
                margin-left: auto;
                font-size: 12px;
                line-height: 16px;
                color: rgba(34, 34, 34, 0.55);
            }

            .relationship-actions {
                display: flex;
                justify-content: flex-end;
            }

            .relationship-delete-btn {
                height: 28px;
                border: none;
                border-radius: 12px;
                padding: 0 10px;
                background: rgba(255, 136, 92, 0.18);
                color: #ff885c;
                font-size: 12px;
                line-height: 14px;
                cursor: pointer;
            }

            .relationship-delete-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            @media (max-width: 1279px) {
                :host {
                    height: auto;
                    min-height: 100%;
                }

                .layout {
                    grid-template-columns: minmax(0, 1fr);
                    height: auto;
                    min-height: 0;
                    align-content: start;
                    grid-template-rows: auto auto;
                }

                .note-main,
                .sidebar {
                    width: 100%;
                    max-width: 100%;
                }

                .note-main.is-editing {
                    height: auto;
                    min-height: min(72dvh, 640px);
                    grid-template-rows: auto minmax(260px, min(58dvh, 520px));
                }
            }

            @media (max-width: 767px) {
                .layout {
                    gap: 16px;
                }

                .note-main {
                    gap: 16px;
                }

                .note-header {
                    flex-direction: column;
                    align-items: stretch;
                    gap: 12px;
                }

                .note-title {
                    font-size: 24px;
                    line-height: 30px;
                }

                .note-title-input {
                    font-size: 22px;
                    line-height: 28px;
                }

                .note-date {
                    font-size: 14px;
                    line-height: 18px;
                }

                .note-actions {
                    width: 100%;
                    display: grid;
                    grid-template-columns: 44px 44px 44px minmax(0, 1fr) minmax(0, 1fr);
                    gap: 10px;
                    justify-content: stretch;
                    align-items: center;
                }

                .round-btn {
                    width: 44px;
                    height: 44px;
                }

                .cancel-btn,
                .edit-btn {
                    width: 100%;
                    min-width: 0;
                    padding: 0 12px;
                    font-size: 14px;
                    line-height: 18px;
                }

                .card {
                    padding: 16px;
                }

                .summary-title,
                .tasks-title,
                .entities-title,
                .relationships-title {
                    font-size: 18px;
                    line-height: 24px;
                }

                .note-edit-meta {
                    grid-template-columns: 1fr;
                    max-width: 100%;
                }

                .summary-text,
                .task-text {
                    font-size: 14px;
                    line-height: 18px;
                }

                .note-text-input {
                    min-height: 220px;
                }

                .note-main.is-editing .note-text-input {
                    height: 100%;
                    min-height: 220px;
                }

                .entity-link {
                    padding: 10px;
                    gap: 10px;
                }

                .entity-avatar {
                    width: 56px;
                    height: 56px;
                }

                .entity-name {
                    font-size: 15px;
                }

                .relationship-link {
                    padding: 10px;
                    gap: 10px;
                }

                .relationship-avatar {
                    width: 48px;
                    height: 48px;
                }

                .relationship-name {
                    font-size: 14px;
                    line-height: 18px;
                }
            }

            @media (max-width: 420px) {
                .note-actions {
                    grid-template-columns: repeat(3, 1fr);
                }

                .round-btn {
                    width: 100%;
                    border-radius: 14px;
                }

                .cancel-btn,
                .edit-btn {
                    grid-column: 1 / -1;
                    width: 100%;
                }

                .summary-actions {
                    gap: 6px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.note = null;
        this.relatedEntities = [];
        this.entityTypes = [];
        this.relationships = [];
        this.attachments = [];
        this.relationshipTypes = [];
        this.noteSubtypes = [];
        this.summaryText = '';
        this.summaryGeneratedAt = '';
        this.summaryEntities = [];
        this.hasAnalysisDraft = false;
        this.analysisDraftGeneratedAt = '';
        this.processingEntities = false;
        this.deletingNote = false;
        this.editable = false;
        this.savingNote = false;
        this.draftMode = false;
        this.processingAttachment = false;
        this.processingRelationship = false;
        this._draftTitle = '';
        this._draftText = '';
        this._draftSubtype = '';
        this._draftNoteDate = '';
        this._draftVoiceMode = 'default';
        this._draftManualVoiceId = '';
        this._draftContextEntityId = '';
    }

    _syncVoiceContextDraftsFromGraph() {
        if (!this.note || typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            this._draftVoiceMode = 'default';
            this._draftManualVoiceId = '';
            this._draftContextEntityId = '';
            return;
        }
        const rels = Array.isArray(this.relationships) ? this.relationships : [];
        const nid = this.note.entity_id;
        const voice = rels.find((r) => r.relationship_type === 'note_voice' && r.source_entity_id === nid);
        const ctx = rels.find((r) => r.relationship_type === 'in_context' && r.source_entity_id === nid);
        if (voice && typeof voice.target_entity_id === 'string') {
            this._draftVoiceMode = 'manual';
            this._draftManualVoiceId = voice.target_entity_id;
        } else {
            this._draftVoiceMode = 'default';
            this._draftManualVoiceId = '';
        }
        this._draftContextEntityId = ctx && typeof ctx.target_entity_id === 'string' ? ctx.target_entity_id : '';
    }

    willUpdate(changedProperties) {
        if (changedProperties.has('note') || changedProperties.has('editable')) {
            const noteName = this.note && typeof this.note.name === 'string' ? this.note.name : '';
            const noteDescription = this.note && typeof this.note.description === 'string' ? this.note.description : '';
            const noteSubtype = this.note && typeof this.note.entity_subtype === 'string' ? this.note.entity_subtype : '';
            const noteDate = this.note && typeof this.note.note_date === 'string' ? this.note.note_date : '';
            if (this.editable) {
                this._draftTitle = noteName;
                this._draftText = noteDescription;
                this._draftSubtype = noteSubtype;
                this._draftNoteDate = noteDate || getLocalIsoDate();
            }
        }
        if (
            this.editable
            && (changedProperties.has('note') || changedProperties.has('editable') || changedProperties.has('relationships'))
        ) {
            this._syncVoiceContextDraftsFromGraph();
        }
    }

    _formatNoteDate(dateValue) {
        if (typeof dateValue !== 'string' || dateValue.trim().length === 0) {
            return '';
        }
        const date = new Date(dateValue);
        if (Number.isNaN(date.getTime())) {
            throw new Error('Invalid note date');
        }
        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        });
    }

    _getTaskEntities() {
        if (!Array.isArray(this.relatedEntities)) {
            throw new Error('relatedEntities must be an array');
        }
        return this.relatedEntities.filter((entity) => entity?.entity_type === 'task');
    }

    _getNonTaskEntities() {
        if (!Array.isArray(this.relatedEntities)) {
            throw new Error('relatedEntities must be an array');
        }
        return this.relatedEntities.filter((entity) => entity?.entity_type !== 'task');
    }

    _getRelationships() {
        if (!Array.isArray(this.relationships)) {
            throw new Error('relationships must be an array');
        }
        const noteId = this.note?.entity_id;
        if (!noteId) {
            return [];
        }
        return this.relationships.filter((rel) => rel?.source_entity_id === noteId || rel?.target_entity_id === noteId);
    }

    _getText(value, fallback) {
        if (typeof value === 'string' && value.trim().length > 0) {
            return value;
        }
        return fallback;
    }

    _getSummaryMeta() {
        if (typeof this.summaryGeneratedAt === 'string' && this.summaryGeneratedAt.trim().length > 0) {
            return `Сгенерирована в ${this.summaryGeneratedAt}`;
        }
        if (
            this.hasAnalysisDraft
            && typeof this.analysisDraftGeneratedAt === 'string'
            && this.analysisDraftGeneratedAt.trim().length > 0
        ) {
            return `Есть черновик анализа от ${this.analysisDraftGeneratedAt}`;
        }
        return 'Нажмите обновить для генерации summary';
    }

    _getEntityAvatarUrl(entity) {
        const attrs = entity?.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.avatar_url === 'string' && attrs.avatar_url.trim().length > 0) {
            return attrs.avatar_url;
        }
        return '';
    }

    _getEntitySubtitle(entity) {
        const attrs = entity?.attributes;
        if (attrs && typeof attrs === 'object') {
            const subtitleKeys = ['position', 'role', 'department', 'company', 'title'];
            for (const key of subtitleKeys) {
                const value = attrs[key];
                if (typeof value === 'string' && value.trim().length > 0) {
                    return value;
                }
            }
        }
        const subtype = this._getText(entity?.entity_subtype, '');
        if (subtype) {
            return subtype;
        }
        return this._getText(entity?.entity_type, 'entity');
    }

    _getEntityTone(index) {
        const tones = ['violet', 'yellow', 'orange'];
        return tones[index % tones.length];
    }

    _getEntityTypeConfig(entity) {
        if (!Array.isArray(this.entityTypes)) {
            throw new Error('entityTypes must be array');
        }
        const typeId = this._getText(entity?.entity_subtype, entity?.entity_type);
        if (!typeId) {
            return null;
        }
        return this.entityTypes.find((item) => item?.type_id === typeId) || null;
    }

    _getRelationshipTypeLabel(relationshipType) {
        if (typeof relationshipType !== 'string' || relationshipType.trim().length === 0) {
            return 'Связь';
        }
        if (!Array.isArray(this.relationshipTypes)) {
            throw new Error('relationshipTypes must be array');
        }
        const foundType = this.relationshipTypes.find((item) => item?.type_id === relationshipType);
        if (foundType && typeof foundType.name === 'string' && foundType.name.trim().length > 0) {
            return foundType.name.trim();
        }
        return relationshipType
            .split('_')
            .filter((part) => part.length > 0)
            .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
            .join(' ');
    }

    _getEntityLabelById(entityId) {
        if (typeof entityId !== 'string' || entityId.trim().length === 0) {
            return 'Неизвестная сущность';
        }
        if (!Array.isArray(this.relatedEntities)) {
            throw new Error('relatedEntities must be an array');
        }
        if (this.note?.entity_id === entityId) {
            return this._getText(this.note?.name, 'Текущая заметка');
        }
        const foundEntity = this.relatedEntities.find((entity) => entity?.entity_id === entityId);
        if (!foundEntity) {
            return entityId;
        }
        return this._getText(foundEntity.name, entityId);
    }

    _getRelationshipTypeConfig(relationshipType) {
        if (typeof relationshipType !== 'string' || relationshipType.trim().length === 0) {
            return null;
        }
        if (!Array.isArray(this.relationshipTypes)) {
            throw new Error('relationshipTypes must be array');
        }
        return this.relationshipTypes.find((item) => item?.type_id === relationshipType) || null;
    }

    _getRelationshipDirectionArrow(relationshipType) {
        const config = this._getRelationshipTypeConfig(relationshipType);
        if (config && config.is_directed === false) {
            return '<->';
        }
        return '->';
    }

    _getRelationshipWeightText(relationship) {
        const rawWeight = relationship?.weight;
        if (typeof rawWeight !== 'number' || !Number.isFinite(rawWeight)) {
            return '';
        }
        return `Вес: ${rawWeight.toFixed(2)}`;
    }

    _getNoteSubtypeOptions() {
        if (!Array.isArray(this.noteSubtypes)) {
            throw new Error('noteSubtypes must be array');
        }
        return this.noteSubtypes;
    }

    _getNoteSubtypeLabel() {
        const subtypeId = this._getText(this.note?.entity_subtype, '');
        if (subtypeId.length === 0) {
            return '';
        }
        const subtype = this._getNoteSubtypeOptions().find((item) => item?.type_id === subtypeId);
        if (!subtype) {
            return subtypeId;
        }
        return this._getText(subtype.name, subtypeId);
    }

    _getAttachmentName(attachment) {
        return this._getText(
            attachment?.filename,
            this._getText(attachment?.document_name, this._getText(attachment?.document_id, 'Файл')),
        );
    }

    _getAttachmentStatus(attachment) {
        return this._getText(attachment?.status, 'unknown');
    }

    _getEntityIcon(entity) {
        const typeConfig = this._getEntityTypeConfig(entity);
        if (typeConfig && typeof typeConfig.icon === 'string' && typeConfig.icon.trim().length > 0) {
            const rawIconName = typeConfig.icon.trim();
            if (/^[a-z0-9-]+$/i.test(rawIconName)) {
                return rawIconName;
            }
            const emojiIconAliases = {
                '🤝': 'share',
                '👤': 'user',
                '🏢': 'database',
            };
            const aliasIconName = emojiIconAliases[rawIconName];
            if (typeof aliasIconName === 'string') {
                return aliasIconName;
            }
        }
        const entityType = this._getText(entity?.entity_type, '');
        if (entityType === 'organization') {
            return 'database';
        }
        if (entityType === 'task') {
            return 'check';
        }
        return 'user';
    }

    _hexToRgba(hexColor, alpha) {
        if (typeof hexColor !== 'string' || !hexColor.startsWith('#') || hexColor.length !== 7) {
            return `rgba(153, 166, 249, ${alpha})`;
        }
        const red = parseInt(hexColor.slice(1, 3), 16);
        const green = parseInt(hexColor.slice(3, 5), 16);
        const blue = parseInt(hexColor.slice(5, 7), 16);
        return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }

    _getEntityAvatarStyle(entity, tone) {
        const typeConfig = this._getEntityTypeConfig(entity);
        if (typeConfig && typeof typeConfig.color === 'string' && typeConfig.color.trim().length > 0) {
            return `background: ${this._hexToRgba(typeConfig.color, 0.2)}; color: ${typeConfig.color};`;
        }
        if (tone === 'yellow') {
            return 'background: rgba(250, 209, 122, 0.45); color: #222222;';
        }
        if (tone === 'orange') {
            return 'background: rgba(255, 136, 92, 0.4); color: #222222;';
        }
        return 'background: rgba(153, 166, 249, 0.4); color: #222222;';
    }

    _getEntityScorePercent(entity) {
        const relevance = entity?.relevance;
        if (typeof relevance === 'number' && Number.isFinite(relevance)) {
            if (relevance > 1) {
                return Math.max(0, Math.min(100, Math.round(relevance)));
            }
            return Math.max(0, Math.min(100, Math.round(relevance * 100)));
        }
        const confidence = entity?.attributes?.confidence;
        if (typeof confidence === 'number' && Number.isFinite(confidence)) {
            if (confidence > 1) {
                return Math.max(0, Math.min(100, Math.round(confidence)));
            }
            return Math.max(0, Math.min(100, Math.round(confidence * 100)));
        }
        return 80;
    }

    _emitEntityOpen(entity) {
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity is required');
        }
        this.emit('entity-open', { entity });
    }

    _emitShareNote() {
        this.emit('share-note', { noteId: this.note.entity_id });
    }

    _emitDeleteNote() {
        this.emit('delete-note', { noteId: this.note.entity_id });
    }

    _emitEditNote() {
        this.emit('edit-note', { noteId: this.note.entity_id });
    }

    _emitSaveNote() {
        const title = this._draftTitle.trim();
        if (title.length === 0) {
            throw new Error('Название заметки не может быть пустым');
        }
        const subtype = this._draftSubtype.trim();
        const noteDate = this._draftNoteDate.trim();
        if (noteDate.length === 0) {
            throw new Error('Дата заметки не выбрана');
        }
        this.emit('save-note', {
            noteId: this.note.entity_id,
            name: title,
            description: this._draftText,
            entitySubtype: subtype.length > 0 ? subtype : null,
            noteDate,
            voiceMode: this._draftVoiceMode,
            voiceEntityId: (this._draftManualVoiceId || '').trim(),
            contextEntityId: (this._draftContextEntityId || '').trim(),
        });
    }

    _onVoiceModeChange(event) {
        this._draftVoiceMode = event.target.value;
    }

    _onManualVoiceInput(event) {
        this._draftManualVoiceId = event.target.value;
    }

    _onContextEntityInput(event) {
        this._draftContextEntityId = event.target.value;
    }

    _emitCancelEdit() {
        this.emit('cancel-edit-note', { noteId: this.note.entity_id });
    }

    _onTitleInput(event) {
        this._draftTitle = event.target.value;
    }

    _onTextInput(event) {
        this._draftText = event.target.value;
    }

    _onSubtypeChange(event) {
        this._draftSubtype = event.target.value;
    }

    _onNoteDateChange(event) {
        this._draftNoteDate = event.target.value;
    }

    _escapeHtml(rawText) {
        if (typeof rawText !== 'string') {
            return '';
        }
        return rawText
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    _renderMarkdown(text) {
        const escaped = this._escapeHtml(text);
        if (escaped.length === 0) {
            return html`<p class="note-text">Без описания</p>`;
        }
        if (window.marked && typeof window.marked.parse === 'function') {
            const htmlContent = window.marked.parse(escaped, {
                breaks: true,
                gfm: true,
            });
            return html`<div class="note-markdown">${unsafeHTML(htmlContent)}</div>`;
        }
        const htmlContent = escaped.replace(/\n/g, '<br>');
        return html`<div class="note-markdown">${unsafeHTML(htmlContent)}</div>`;
    }

    _emitSummaryRefresh() {
        this.emit('summary-refresh', { noteId: this.note.entity_id });
    }

    _emitOpenAnalysisDraft() {
        this.emit('open-analysis-draft', { noteId: this.note.entity_id });
    }

    _openFilePicker() {
        const fileInput = this.renderRoot?.querySelector('#note-attachment-input');
        if (!(fileInput instanceof HTMLInputElement)) {
            throw new Error('Attachment file input is not available');
        }
        fileInput.click();
    }

    _onAttachmentFileSelected(event) {
        const input = event.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('Attachment input must be HTMLInputElement');
        }
        if (!input.files || input.files.length === 0) {
            return;
        }
        const file = input.files[0];
        this.emit('upload-attachment', { noteId: this.note.entity_id, file });
        input.value = '';
    }

    _emitDeleteAttachment(attachment) {
        if (!attachment || typeof attachment !== 'object') {
            throw new Error('Attachment payload is required');
        }
        this.emit('delete-attachment', { noteId: this.note.entity_id, attachment });
    }

    _emitDeleteRelationship(relationship) {
        if (!relationship || typeof relationship !== 'object') {
            throw new Error('Relationship payload is required');
        }
        this.emit('delete-relationship', { noteId: this.note.entity_id, relationship });
    }

    render() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }

        const noteText = this.editable ? this._draftText : this._getText(this.note.description, 'Без описания');
        const noteTitle = this.editable ? this._draftTitle : this._getText(this.note.name, 'Заметка');
        const noteDate = this._formatNoteDate(this.note.note_date || this.note.updated_at || this.note.created_at);
        const noteSubtypeLabel = this._getNoteSubtypeLabel();
        const noteSubtypeOptions = this._getNoteSubtypeOptions();
        const taskEntities = this._getTaskEntities();
        const nonTaskEntities = this._getNonTaskEntities();
        const relationships = this._getRelationships();
        const attachments = Array.isArray(this.attachments) ? this.attachments : [];
        const summaryTags = Array.isArray(this.summaryEntities) ? this.summaryEntities : [];

        return html`
            <div class="layout ${this.editable ? 'is-editing' : ''}">
                <section class="note-main ${this.editable ? 'is-editing' : ''}">
                    <div class="note-header">
                        <div class="note-title-wrap">
                            ${this.editable ? html`
                                <input
                                    class="form-input note-title-input"
                                    type="text"
                                    .value=${noteTitle}
                                    @input=${this._onTitleInput}
                                    placeholder="Название заметки"
                                />
                                <div class="note-edit-meta">
                                    <select
                                        class="form-select note-subtype-select"
                                        .value=${this._draftSubtype}
                                        @change=${this._onSubtypeChange}
                                    >
                                        <option value="">Без подтипа</option>
                                        ${noteSubtypeOptions.map((item) => html`
                                            <option value=${item.type_id}>${this._getText(item.name, item.type_id)}</option>
                                        `)}
                                    </select>
                                    <platform-date-picker
                                        class="note-date-picker"
                                        mode="date"
                                        value-format="iso"
                                        label="Дата"
                                        .value=${this._draftNoteDate}
                                        @change=${this._onNoteDateChange}
                                    ></platform-date-picker>
                                </div>
                                <div class="note-edit-meta voice-context-row">
                                    <label class="form-label">Голос заметки</label>
                                    <select
                                        class="form-select"
                                        .value=${this._draftVoiceMode}
                                        @change=${this._onVoiceModeChange}
                                    >
                                        <option value="default">По умолчанию (неймспейс)</option>
                                        <option value="self">Я</option>
                                        <option value="none">Без голоса</option>
                                        <option value="manual">Контакт (id)</option>
                                    </select>
                                    ${this._draftVoiceMode === 'manual' ? html`
                                        <input
                                            class="form-input mono"
                                            type="text"
                                            placeholder="entity_id контакта"
                                            .value=${this._draftManualVoiceId}
                                            @input=${this._onManualVoiceInput}
                                        />
                                    ` : ''}
                                    <label class="form-label">Контекст (якорь)</label>
                                    <input
                                        class="form-input mono"
                                        type="text"
                                        placeholder="entity_id сделки/лида (необязательно)"
                                        .value=${this._draftContextEntityId}
                                        @input=${this._onContextEntityInput}
                                    />
                                </div>
                            ` : html`<h2 class="note-title">${noteTitle}</h2>`}
                            <p class="note-date">${noteDate}</p>
                            ${!this.editable && noteSubtypeLabel.length > 0 ? html`
                                <p class="note-subtype">
                                    <platform-icon name="tag" size="14"></platform-icon>
                                    ${noteSubtypeLabel}
                                </p>
                            ` : ''}
                        </div>
                        <div class="note-actions">
                            <div class="attach-dropdown">
                                <button
                                    class="round-btn attach-header-btn"
                                    type="button"
                                    title="Вложения: добавить файл"
                                    aria-label=${`Вложения, файлов: ${attachments.length}. Нажмите, чтобы добавить файл.`}
                                    ?disabled=${this.draftMode || this.processingAttachment}
                                    @click=${this._openFilePicker}
                                >
                                    <platform-icon name="paperclip" size="20"></platform-icon>
                                    <span class="attach-count-badge" aria-hidden="true">${attachments.length}</span>
                                </button>
                                <div class="attach-dropdown-panel" role="tooltip" @click=${(e) => e.stopPropagation()}>
                                    ${attachments.length === 0 ? html`
                                        <div class="attach-dropdown-empty">Нет вложений</div>
                                    ` : attachments.map((attachment) => html`
                                        <div class="attach-dropdown-row">
                                            <span class="attach-dropdown-name" title=${this._getAttachmentName(attachment)}>
                                                ${this._getAttachmentName(attachment)}
                                            </span>
                                            <button
                                                class="attach-dropdown-remove"
                                                type="button"
                                                title="Удалить файл"
                                                ?disabled=${this.processingAttachment || this.draftMode}
                                                @click=${() => this._emitDeleteAttachment(attachment)}
                                            >
                                                <platform-icon name="close" size="16"></platform-icon>
                                            </button>
                                        </div>
                                    `)}
                                </div>
                            </div>
                            <input
                                id="note-attachment-input"
                                type="file"
                                style="display: none;"
                                @change=${this._onAttachmentFileSelected}
                            />
                            <button
                                class="round-btn"
                                type="button"
                                title="Поделиться"
                                ?disabled=${this.draftMode}
                                @click=${this._emitShareNote}
                            >
                                <platform-icon name="share" size="20"></platform-icon>
                            </button>
                            <button
                                class="round-btn danger"
                                type="button"
                                title="Удалить"
                                ?disabled=${this.deletingNote || this.draftMode}
                                @click=${this._emitDeleteNote}
                            >
                                <platform-icon name="delete" size="20"></platform-icon>
                            </button>
                            ${this.editable ? html`
                                <button
                                    class="cancel-btn"
                                    type="button"
                                    ?disabled=${this.savingNote}
                                    @click=${this._emitCancelEdit}
                                >
                                    Отмена
                                </button>
                                <button
                                    class="edit-btn"
                                    type="button"
                                    ?disabled=${this.savingNote}
                                    @click=${this._emitSaveNote}
                                >
                                    ${this.savingNote ? 'Сохранение...' : 'Сохранить'}
                                </button>
                            ` : html`
                                <button class="edit-btn" type="button" @click=${this._emitEditNote}>Редактировать</button>
                            `}
                        </div>
                    </div>
                    ${this.editable ? html`
                        <textarea
                            class="form-textarea note-text-input"
                            .value=${noteText}
                            @input=${this._onTextInput}
                            placeholder="Введите текст заметки"
                        ></textarea>
                    ` : this._renderMarkdown(noteText)}
                </section>

                <aside class="sidebar">
                    <section class="card summary-card">
                        <div class="card-header">
                            <h3 class="summary-title">
                                <platform-icon name="ai" size="24" colored></platform-icon>
                                AI summary заметки
                            </h3>
                            <div class="summary-actions">
                                ${this.hasAnalysisDraft ? html`
                                    <button
                                        class="round-btn analysis-draft"
                                        type="button"
                                        title="Открыть черновик анализа"
                                        @click=${this._emitOpenAnalysisDraft}
                                    >
                                        <platform-icon name="ai" size="18" colored></platform-icon>
                                    </button>
                                ` : ''}
                                <button
                                    class="round-btn"
                                    type="button"
                                    title="Обновить"
                                    ?disabled=${this.processingEntities || this.draftMode}
                                    @click=${this._emitSummaryRefresh}
                                >
                                    <platform-icon
                                        class="refresh-icon ${this.processingEntities ? 'spinning' : ''}"
                                        name="refresh"
                                        size="18"
                                        colored
                                    ></platform-icon>
                                </button>
                            </div>
                        </div>
                        <p class="summary-meta">${this._getSummaryMeta()}</p>
                        <p class="summary-text">${this._getText(this.summaryText, 'Нет summary')}</p>
                        <div class="summary-tags">
                            ${summaryTags.map((tag) => html`
                                <span class="summary-tag">
                                    <platform-icon name="file" size="12"></platform-icon>
                                    ${tag}
                                </span>
                            `)}
                        </div>
                    </section>

                    <section class="card tasks-card">
                        <h3 class="tasks-title">Связанные задачи</h3>
                        <div class="tasks-list">
                            ${taskEntities.map((task) => {
                                const taskCompleted = task?.status === 'done' || task?.status === 'completed';
                                return html`
                                    <div class="task-row">
                                        <div class="task-main">
                                            <span class="checkbox ${taskCompleted ? 'checked' : ''}">
                                                ${taskCompleted ? html`<platform-icon name="check" size="14"></platform-icon>` : ''}
                                            </span>
                                            <span class="task-text ${taskCompleted ? 'completed' : ''}">${this._getText(task.name, 'Задача')}</span>
                                        </div>
                                        <button class="task-remove" type="button" aria-label="Удалить">
                                            <platform-icon name="close" size="14"></platform-icon>
                                        </button>
                                    </div>
                                `;
                            })}
                        </div>
                    </section>

                    <section class="entities-section">
                        <h3 class="entities-title">Связанные сущности</h3>
                        ${nonTaskEntities.map((entity, index) => {
                            const tone = this._getEntityTone(index);
                            const avatarUrl = this._getEntityAvatarUrl(entity);
                            const entityIcon = this._getEntityIcon(entity);
                            const scorePercent = this._getEntityScorePercent(entity);
                            return html`
                                <button
                                    class="entity-link ${tone === 'yellow' ? 'tone-yellow' : ''} ${tone === 'orange' ? 'tone-orange' : ''}"
                                    type="button"
                                    @click=${() => this._emitEntityOpen(entity)}
                                >
                                    <span class="entity-avatar" style=${this._getEntityAvatarStyle(entity, tone)}>
                                        ${avatarUrl
                                            ? html`<img src=${avatarUrl} alt=${this._getText(entity.name, 'Entity')} />`
                                            : html`<platform-icon name=${entityIcon} size="28"></platform-icon>`}
                                    </span>
                                    <span class="entity-data">
                                        <span>
                                            <p class="entity-name">${this._getText(entity.name, 'Entity')}</p>
                                            <p class="entity-subtitle">${this._getEntitySubtitle(entity)}</p>
                                        </span>
                                        <span class="entity-score">
                                            <span
                                                class="entity-score-fill ${tone === 'yellow' ? 'tone-yellow' : ''} ${tone === 'orange' ? 'tone-orange' : ''}"
                                                style=${`width: ${scorePercent}%;`}
                                            ></span>
                                        </span>
                                    </span>
                                </button>
                            `;
                        })}
                    </section>

                    <section class="relationships-section">
                        <div class="section-toolbar">
                            <h3 class="relationships-title">Связи</h3>
                        </div>
                        ${relationships.map((relationship) => {
                            const sourceId = this._getText(relationship.source_entity_id, '');
                            const targetId = this._getText(relationship.target_entity_id, '');
                            const relationshipType = this._getText(relationship.relationship_type, '');
                            const sourceLabel = this._getEntityLabelById(sourceId);
                            const targetLabel = this._getEntityLabelById(targetId);
                            const relationshipLabel = this._getRelationshipTypeLabel(relationshipType);
                            const directionArrow = this._getRelationshipDirectionArrow(relationshipType);
                            const weightText = this._getRelationshipWeightText(relationship);
                            return html`
                                <div class="relationship-link">
                                    <span class="relationship-avatar">
                                        <platform-icon name="share" size="24"></platform-icon>
                                    </span>
                                    <span class="relationship-data">
                                        <p class="relationship-name">${relationshipLabel}</p>
                                        <div class="relationship-entities">
                                            <button
                                                class="relationship-entity-btn"
                                                type="button"
                                                ?disabled=${sourceId.length === 0}
                                                @click=${() => this._emitEntityOpen({ entity_id: sourceId, name: sourceLabel })}
                                            >
                                                ${sourceLabel}
                                            </button>
                                            <span class="relationship-subtitle">${directionArrow}</span>
                                            <button
                                                class="relationship-entity-btn"
                                                type="button"
                                                ?disabled=${targetId.length === 0}
                                                @click=${() => this._emitEntityOpen({ entity_id: targetId, name: targetLabel })}
                                            >
                                                ${targetLabel}
                                            </button>
                                            ${weightText.length > 0 ? html`<span class="relationship-weight">${weightText}</span>` : ''}
                                        </div>
                                        <div class="relationship-actions">
                                            <button
                                                class="relationship-delete-btn"
                                                type="button"
                                                ?disabled=${this.processingRelationship || this.draftMode}
                                                @click=${() => this._emitDeleteRelationship(relationship)}
                                            >
                                                Удалить
                                            </button>
                                        </div>
                                    </span>
                                </div>
                            `;
                        })}
                    </section>
                </aside>
            </div>
        `;
    }
}

customElements.define('note-content', NoteContent);
