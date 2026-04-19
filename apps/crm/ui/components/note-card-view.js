/**
 * NoteCardView — карточка заметки CRM. Один компонент, два режима через
 * свойство `mode`:
 *
 *   - `view` (default): read-only представление с markdown, AI-summary,
 *     related entities, relationships, attachments. Шапка выдаёт три
 *     действия: edit / graph / delete (через emit).
 *   - `edit`: inline-форма поверх той же сущности — title, описание (с
 *     голосовым вводом), дата, теги, аплоад вложений. На сохранение шлёт
 *     `entitiesResource.create` (для note === null) или
 *     `entityUpdateOp.run({ id, body })` (для существующей заметки).
 *
 * Принимает:
 *   - `note: Entity | null` — заметка. null = режим создания (entity_type='note').
 *   - `card: { related_entities, relationships, attachments } | null` — данные
 *     для view-сайдбара (берутся из `crm/entity_card`).
 *   - `relationshipTypes` — массив { type_id, name } для подписей в view.
 *   - `mode: 'view' | 'edit'` — текущий режим (для note === null
 *     автоматически 'edit').
 *   - `defaultNamespace: string` — обязателен для режима создания.
 *
 * Эмитит:
 *   - `edit-note`                — клик по карандашу в шапке view.
 *   - `show-graph`               — клик по иконке графа в шапке view.
 *   - `delete-note`              — клик по корзине в шапке view.
 *   - `entity-open` { entityId } — клик по chip связанной сущности (view).
 *   - `cancel`                   — отмена в edit-режиме.
 *   - `saved` { entity }         — успешное сохранение существующей заметки.
 *   - `created` { entity }       — успешное создание новой заметки.
 *
 * Markdown рендерится через глобальный `window.marked`, подключённый в
 * `apps/crm/ui/index.html` (`/static/core/assets/js/marked.min.js`).
 */

import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_UPDATE_OP = 'crm/entity_update';
const FILE_UPLOAD_OP = 'crm/file_upload';
const VOICE_OP = 'crm/note_voice_input';
const ENTITY_SEARCH_OP = 'crm/entity_search';

const MENTION_REGEX = /@\[([^\]]+)\]\(([^)]+)\)/g;

const NOTE_DATE_FORMAT = new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
});

const SUMMARY_TIME_FORMAT = new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
});

function escapeHtml(text) {
    if (typeof text !== 'string') {
        return '';
    }
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

const MENTION_PLACEHOLDER_OPEN = '\u0001MENTION\u0002';
const MENTION_PLACEHOLDER_CLOSE = '\u0001/MENTION\u0002';

function _replaceMentionsWithPlaceholder(text) {
    return text.replace(MENTION_REGEX, (_match, name, id) => {
        return `${MENTION_PLACEHOLDER_OPEN}${id}\u0001${name}${MENTION_PLACEHOLDER_CLOSE}`;
    });
}

function _restoreMentionsHtml(html) {
    const openEsc = '\u0001MENTION\u0002';
    const closeEsc = '\u0001/MENTION\u0002';
    const re = new RegExp(`${openEsc}([^\u0001]+)\u0001([^\u0001]+)${closeEsc}`, 'g');
    return html.replace(re, (_m, id, name) => {
        const safeId = escapeHtml(id);
        const safeName = escapeHtml(name);
        return `<span class="mention-chip" data-entity-id="${safeId}">@${safeName}</span>`;
    });
}

function renderMarkdownToHtml(text) {
    const withPlaceholders = _replaceMentionsWithPlaceholder(typeof text === 'string' ? text : '');
    const escaped = escapeHtml(withPlaceholders);
    if (escaped.length === 0) {
        return '';
    }
    const rendered = window.marked && typeof window.marked.parse === 'function'
        ? window.marked.parse(escaped, { breaks: true, gfm: true })
        : escaped.replace(/\n/g, '<br>');
    return _restoreMentionsHtml(rendered);
}

function formatBytes(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
        return '';
    }
    if (value < 1024) {
        return `${value} B`;
    }
    if (value < 1024 * 1024) {
        return `${(value / 1024).toFixed(1)} KB`;
    }
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function _hasGetUserMediaApi() {
    return typeof navigator !== 'undefined'
        && typeof navigator.mediaDevices === 'object'
        && navigator.mediaDevices !== null
        && typeof navigator.mediaDevices.getUserMedia === 'function';
}

function _pickVoiceMimeType() {
    if (typeof MediaRecorder === 'undefined') return '';
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    for (const candidate of candidates) {
        if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(candidate)) {
            return candidate;
        }
    }
    return '';
}

function _formatDateInput(value) {
    if (typeof value !== 'string' || value.length === 0) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function _todayDateInput() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export class CRMNoteCardView extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        note: { attribute: false },
        card: { attribute: false },
        relationshipTypes: { attribute: false },
        mode: { type: String },
        defaultNamespace: { type: String },
        _editName: { state: true },
        _editDescription: { state: true },
        _editDate: { state: true },
        _editTags: { state: true },
        _editAttachmentIds: { state: true },
        _tagDraft: { state: true },
        _voiceState: { state: true },
        _formError: { state: true },
        _mentionOpen: { state: true },
        _mentionQuery: { state: true },
        _mentionResults: { state: true },
        _mentionLoading: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                min-height: 0;
                color: var(--text-primary);
                font-family: var(--font-sans);
            }

            /* ================== layout ================== */
            .layout {
                display: grid;
                grid-template-columns: minmax(0, 788fr) minmax(320px, 440fr);
                gap: var(--space-6);
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }
            .layout.edit-mode {
                grid-template-columns: minmax(0, 1fr);
            }
            @media (max-width: 1023px) {
                .layout {
                    grid-template-columns: 1fr;
                    overflow-y: auto;
                }
            }

            .main {
                display: flex;
                flex-direction: column;
                min-width: 0;
                min-height: 0;
                gap: var(--space-5);
                overflow-y: auto;
                padding-right: var(--space-2);
            }
            .sidebar {
                display: flex;
                flex-direction: column;
                gap: var(--space-6);
                min-width: 0;
                overflow-y: auto;
                padding-right: var(--space-1);
            }

            /* ================== note header ================== */
            .header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-4);
            }
            .title-block {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
                flex: 1;
            }
            .title {
                margin: 0;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
                color: var(--text-primary);
                word-break: break-word;
                font-family: 'Inter', var(--font-sans);
            }
            .title-input {
                margin: 0;
                width: 100%;
                font-size: 28px;
                line-height: 34px;
                font-weight: 700;
                color: var(--text-primary);
                background: transparent;
                border: none;
                border-bottom: 1px dashed var(--crm-stroke);
                padding: 2px 0;
                outline: none;
                font-family: 'Inter', var(--font-sans);
            }
            .title-input:focus { border-bottom-color: var(--accent); }
            .note-date {
                font-size: 16px;
                line-height: 20px;
                color: var(--crm-note-text-muted);
                font-weight: 400;
            }

            .header-actions {
                display: inline-flex;
                gap: var(--space-3);
                flex-shrink: 0;
                align-items: center;
            }

            /* round buttons (44x44) */
            .round-btn {
                width: 44px;
                height: 44px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-note-action-bg);
                border: none;
                border-radius: var(--radius-full);
                color: var(--text-primary);
                cursor: pointer;
                transition: background var(--duration-fast);
            }
            .round-btn:hover:not(:disabled) {
                background: var(--crm-note-action-bg-hover);
            }
            .round-btn.danger {
                background: var(--crm-note-action-orange-bg);
                color: var(--crm-note-action-orange-color);
            }
            .round-btn.danger:hover:not(:disabled) {
                background: var(--crm-note-action-orange-bg);
                filter: brightness(1.1);
            }
            .round-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }

            /* primary pill button (Edit / Save) */
            .pill-btn {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 8px 24px;
                height: 44px;
                background: var(--accent);
                color: #FFFFFF;
                border: none;
                border-radius: var(--radius-full);
                font-size: 16px;
                line-height: 20px;
                font-weight: 400;
                cursor: pointer;
                transition: filter var(--duration-fast), background var(--duration-fast);
            }
            .pill-btn:hover:not(:disabled) { filter: brightness(1.05); }
            .pill-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .pill-btn.ghost {
                background: var(--crm-note-action-bg);
                color: var(--text-primary);
            }

            /* ================== note content (markdown) ================== */
            .markdown {
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-weight: 400;
                word-break: break-word;
            }
            .markdown p {
                margin: 0 0 16px 0;
            }
            .markdown p:last-child { margin-bottom: 0; }
            .markdown h1, .markdown h2, .markdown h3, .markdown h4 {
                margin: 24px 0 8px 0;
                color: var(--text-primary);
                font-family: 'Inter', var(--font-sans);
            }
            .markdown h1 { font-size: 28px; line-height: 34px; }
            .markdown h2 { font-size: 24px; line-height: 30px; }
            .markdown h3 { font-size: 20px; line-height: 26px; }
            .markdown h4 { font-size: 16px; line-height: 20px; font-weight: 600; }
            .markdown ul, .markdown ol { margin: 0 0 16px 0; padding-left: 24px; }
            .markdown li { margin-bottom: 4px; }
            .markdown strong { font-weight: 700; }
            .markdown a {
                color: var(--accent);
                text-decoration: none;
                border-bottom: 1px solid currentColor;
            }
            .markdown a:hover { color: var(--accent-hover); }
            .markdown code {
                background: var(--crm-note-input-bg);
                padding: 2px 6px;
                border-radius: 6px;
                font-family: var(--font-mono);
                font-size: 0.9em;
            }
            .markdown pre {
                background: var(--crm-note-input-bg);
                padding: 12px 16px;
                border-radius: var(--radius-md);
                overflow-x: auto;
                margin: 0 0 16px 0;
            }
            .markdown pre code {
                background: transparent;
                padding: 0;
            }
            .markdown blockquote {
                margin: 0 0 16px 0;
                padding-left: 16px;
                border-left: 3px solid var(--accent);
                color: var(--text-secondary);
            }
            .mention-chip {
                display: inline-flex;
                align-items: center;
                padding: 2px 8px;
                margin: 0 2px;
                background: var(--crm-note-related-violet-bg);
                color: var(--text-primary);
                border-radius: var(--radius-full);
                font-size: 0.95em;
                cursor: pointer;
                transition: filter var(--duration-fast);
            }
            .mention-chip:hover { filter: brightness(0.95); }

            .empty-text {
                font-size: 16px;
                line-height: 20px;
                color: var(--crm-note-text-muted);
                font-style: italic;
            }

            /* ================== sidebar cards ================== */
            .card {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-5);
                border-radius: var(--radius-lg);
            }
            .card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .card-title {
                margin: 0;
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
                font-family: 'Inter', var(--font-sans);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }

            /* AI summary card */
            .summary-card {
                background: var(--crm-note-summary-bg);
            }
            .summary-card .card-title {
                background: var(--crm-note-summary-title-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                color: transparent;
            }
            .summary-spark {
                width: 24px;
                height: 24px;
                background: var(--crm-note-icon-gradient);
                -webkit-mask: var(--summary-spark-mask) center / contain no-repeat;
                mask: var(--summary-spark-mask) center / contain no-repeat;
                flex-shrink: 0;
            }
            .summary-meta {
                margin: 0;
                font-size: 12px;
                line-height: 15px;
                color: var(--crm-note-text-muted);
            }
            .summary-text {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
                white-space: pre-wrap;
            }
            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
            }
            .summary-tag {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                font-size: 12px;
                line-height: 15px;
                color: var(--text-primary);
                border-radius: var(--radius-full);
            }
            .summary-tag.tag-violet { background: var(--crm-accent-violet); }
            .summary-tag.tag-yellow { background: var(--crm-accent-yellow); }
            .summary-tag.tag-orange { background: var(--crm-accent-orange); color: #FFFFFF; }

            /* Tasks card */
            .tasks-card {
                background: var(--crm-note-tasks-bg);
            }
            .tasks-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .task-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: 32px;
            }
            .task-check {
                width: 24px;
                height: 24px;
                border-radius: 4px;
                border: 2px solid var(--crm-note-checkbox-pending-border);
                background: transparent;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: background var(--duration-fast), border-color var(--duration-fast);
                padding: 0;
            }
            .task-check.checked {
                background: var(--crm-note-checkbox-checked-bg);
                border-color: var(--crm-note-checkbox-checked-bg);
                color: var(--crm-note-checkbox-checked-mark);
            }
            .task-text {
                flex: 1;
                min-width: 0;
                font-size: 16px;
                line-height: 20px;
                color: var(--text-primary);
                word-break: break-word;
            }
            .task-text.done {
                color: var(--crm-note-text-strikethrough);
                text-decoration: line-through;
            }
            .task-remove {
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--crm-note-text-strikethrough);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                flex-shrink: 0;
            }
            .task-remove:hover { color: var(--text-primary); }
            .task-add-input {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 10px 20px;
                background: var(--crm-note-input-bg);
                border-radius: var(--radius-full);
                height: 44px;
                box-sizing: border-box;
            }
            .task-add-input input {
                flex: 1;
                min-width: 0;
                background: transparent;
                border: none;
                outline: none;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-family: inherit;
            }
            .task-add-input input::placeholder { color: var(--crm-note-text-muted); }

            /* Related entities */
            .related-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .related-card {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: 12px;
                border-radius: var(--radius-lg);
                background: var(--crm-note-related-violet-bg);
                cursor: pointer;
                border: none;
                width: 100%;
                text-align: left;
                color: var(--text-primary);
                font-family: inherit;
                transition: filter var(--duration-fast);
            }
            .related-card:hover { filter: brightness(0.97); }
            .related-card.tone-violet { background: var(--crm-note-related-violet-bg); }
            .related-card.tone-yellow { background: var(--crm-note-related-yellow-bg); }
            .related-card.tone-orange { background: var(--crm-note-related-orange-bg); }

            .related-icon {
                width: 64px;
                height: 64px;
                border-radius: var(--radius-md);
                background: var(--crm-note-related-icon-gradient);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: #FFFFFF;
                flex-shrink: 0;
            }

            .related-body {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
                flex: 1;
            }
            .related-name {
                margin: 0;
                font-size: 16px;
                line-height: 20px;
                font-weight: 600;
                color: var(--text-primary);
                font-family: 'Inter', var(--font-sans);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .related-position {
                margin: 0;
                font-size: 12px;
                line-height: 15px;
                color: var(--crm-note-text-muted);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .related-empty {
                font-size: 16px;
                line-height: 20px;
                color: var(--crm-note-text-muted);
            }

            /* ================== EDIT inputs ================== */
            .edit-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .edit-label {
                font-size: 12px;
                line-height: 15px;
                color: var(--crm-note-text-muted);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .description-edit-wrap {
                position: relative;
            }
            .description-edit {
                width: 100%;
                box-sizing: border-box;
                min-height: 220px;
                padding: 16px 56px 16px 16px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-note-input-bg);
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-family: inherit;
                resize: vertical;
                outline: none;
            }
            .description-edit:focus { border-color: var(--accent); }
            .voice-btn {
                position: absolute;
                top: 12px;
                right: 12px;
                width: 36px;
                height: 36px;
                border-radius: var(--radius-full);
                background: var(--crm-note-action-bg);
                border: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .voice-btn:hover:not(:disabled) { background: var(--crm-note-action-bg-hover); color: var(--text-primary); }
            .voice-btn.recording { background: var(--accent-secondary); color: #FFFFFF; }
            .voice-btn.processing { opacity: 0.5; cursor: progress; }

            .edit-row {
                display: grid;
                grid-template-columns: minmax(140px, 220px) minmax(0, 1fr);
                gap: var(--space-4);
            }
            @media (max-width: 700px) {
                .edit-row { grid-template-columns: 1fr; }
            }
            .date-input {
                width: 100%;
                box-sizing: border-box;
                padding: 10px 16px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-note-input-bg);
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-family: inherit;
                outline: none;
            }
            .date-input:focus { border-color: var(--accent); }

            .tags-wrap {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 8px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-note-input-bg);
            }
            .tag-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 4px 10px;
                background: var(--accent);
                color: #FFFFFF;
                border-radius: var(--radius-full);
                font-size: 12px;
                line-height: 15px;
            }
            .tag-chip button {
                background: transparent;
                border: none;
                color: inherit;
                cursor: pointer;
                padding: 0;
                display: inline-flex;
                align-items: center;
            }
            .tag-input {
                flex: 1;
                min-width: 80px;
                background: transparent;
                border: none;
                outline: none;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-family: inherit;
            }
            .tag-input::placeholder { color: var(--crm-note-text-muted); }

            .attachments-edit {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .attachment-edit-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 8px 12px;
                background: var(--crm-note-input-bg);
                border-radius: var(--radius-md);
                font-size: 16px;
                line-height: 20px;
            }
            .attachment-edit-row .name { flex: 1; min-width: 0; }
            .attachment-edit-row .icon-btn {
                width: 24px;
                height: 24px;
                border: none;
                background: transparent;
                color: var(--crm-note-text-muted);
                cursor: pointer;
                border-radius: var(--radius-full);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .attachment-edit-row .icon-btn:hover { color: var(--text-primary); }
            .upload-btn {
                align-self: flex-start;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 8px 16px;
                height: 44px;
                background: var(--crm-note-action-bg);
                border: none;
                border-radius: var(--radius-full);
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                font-family: inherit;
                cursor: pointer;
            }
            .upload-btn:hover { background: var(--crm-note-action-bg-hover); }

            .form-error {
                padding: 10px 16px;
                background: var(--crm-danger-bg);
                color: var(--error);
                border-radius: var(--radius-md);
                font-size: 14px;
            }

            /* mention popover (existing semantics) */
            .mention-popover {
                position: absolute;
                z-index: 30;
                top: calc(100% + 4px);
                left: 0;
                right: 0;
                max-height: 240px;
                overflow-y: auto;
                background: var(--crm-surface-elevated, var(--glass-solid-strong));
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-medium);
            }
            .mention-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 8px 12px;
                cursor: pointer;
                width: 100%;
                background: transparent;
                border: none;
                color: var(--text-primary);
                text-align: left;
                font-family: inherit;
                font-size: 14px;
            }
            .mention-item:hover { background: var(--crm-note-action-bg); }
            .mention-empty {
                padding: 8px 12px;
                color: var(--crm-note-text-muted);
                font-size: 13px;
            }
        `,
    ];

    constructor() {
        super();
        this.note = null;
        this.card = null;
        this.relationshipTypes = [];
        this.mode = 'view';
        this.defaultNamespace = '';

        this._editName = '';
        this._editDescription = '';
        this._editDate = '';
        this._editTags = [];
        this._editAttachmentIds = [];
        this._editAttachmentsMeta = {};
        this._tagDraft = '';
        this._voiceState = 'idle';
        this._formError = '';
        this._mediaRecorder = null;
        this._audioChunks = [];

        this._mentionOpen = false;
        this._mentionQuery = '';
        this._mentionResults = [];
        this._mentionLoading = false;
        this._mentionedEntityIds = new Set();
        this._mentionTriggerIndex = -1;
        this._mentionDebounce = null;
        this._mentionRequestId = null;

        this._entities = this.useResource(ENTITIES_NAME);
        this._updateOp = this.useOp(ENTITY_UPDATE_OP);
        this._fileUpload = this.useOp(FILE_UPLOAD_OP);
        this._voice = this.useOp(VOICE_OP);
        this._entitySearch = this.useOp(ENTITY_SEARCH_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        this._hydrateEditFromNote();

        this.useEvent(this._entities.resource.events.CREATED, (event) => {
            const created = event.payload && event.payload.item;
            if (!created || typeof created !== 'object') return;
            if (created.entity_type !== 'note') return;
            if (this.note !== null) return;
            this.emit('created', { entity: created });
        });

        this.useEvent(this._updateOp.op.events.SUCCEEDED, (event) => {
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result !== 'object') return;
            if (this.note === null || result.entity_id !== this.note.entity_id) return;
            this.emit('saved', { entity: result });
        });

        this.useEvent(this._entities.resource.events.CREATE_FAILED, (event) => {
            const message = event && event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : this.t('note_edit.err_save');
            this._formError = message;
        });
        this.useEvent(this._updateOp.op.events.FAILED, (event) => {
            const message = event && event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : this.t('note_edit.err_save');
            this._formError = message;
        });

        this.useEvent(this._fileUpload.op.events.SUCCEEDED, (event) => {
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result.file_id !== 'string') return;
            this._editAttachmentIds = [...this._editAttachmentIds, result.file_id];
            this._editAttachmentsMeta = {
                ...this._editAttachmentsMeta,
                [result.file_id]: {
                    name: result.original_name || result.file_id,
                    size: result.size_bytes,
                },
            };
        });

        this.useEvent(this._voice.op.events.SUCCEEDED, (event) => {
            const result = event && event.payload && event.payload.result;
            this._voiceState = 'idle';
            this._mediaRecorder = null;
            this._audioChunks = [];
            if (!result || typeof result.text !== 'string' || result.text.trim().length === 0) {
                this.toast('toast.note.voice_empty', { type: 'warning' });
                return;
            }
            const insert = result.text.trim();
            this._editDescription = this._editDescription.length > 0
                ? `${this._editDescription}\n\n${insert}`
                : insert;
        });
        this.useEvent(this._voice.op.events.FAILED, () => {
            this._voiceState = 'idle';
            this._mediaRecorder = null;
            this._audioChunks = [];
        });

        this.useEvent(this._entitySearch.op.events.SUCCEEDED, (event) => {
            const meta = event && event.meta;
            if (this._mentionRequestId === null || (meta && meta.causation_id !== this._mentionRequestId)) return;
            const result = event && event.payload && event.payload.result;
            const items = result && Array.isArray(result.items) ? result.items : [];
            this._mentionResults = items.filter((it) => this.note === null || it.entity_id !== this.note.entity_id);
            this._mentionLoading = false;
        });
        this.useEvent(this._entitySearch.op.events.FAILED, (event) => {
            const meta = event && event.meta;
            if (this._mentionRequestId === null || (meta && meta.causation_id !== this._mentionRequestId)) return;
            this._mentionResults = [];
            this._mentionLoading = false;
        });
    }

    disconnectedCallback() {
        if (this._mentionDebounce !== null) {
            clearTimeout(this._mentionDebounce);
            this._mentionDebounce = null;
        }
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('note')) {
            this._hydrateEditFromNote();
        }
        if (this.note === null && this.mode !== 'edit') {
            this.mode = 'edit';
        }
    }

    _hydrateEditFromNote() {
        const note = this.note;
        if (note === null) {
            this._editName = '';
            this._editDescription = '';
            this._editDate = '';
            this._editTags = [];
            this._editAttachmentIds = [];
            this._editAttachmentsMeta = {};
            this._mentionedEntityIds = new Set();
            this._formError = '';
            return;
        }
        this._editName = typeof note.name === 'string' ? note.name : '';
        this._editDescription = typeof note.description === 'string' ? note.description : '';
        const dateAttr = note.attributes && typeof note.attributes === 'object'
            ? note.attributes.note_date
            : null;
        const sourceDate = typeof note.note_date === 'string' && note.note_date.length > 0
            ? note.note_date
            : (typeof dateAttr === 'string' ? dateAttr : '');
        this._editDate = _formatDateInput(sourceDate);
        this._editTags = Array.isArray(note.tags) ? [...note.tags] : [];
        this._editAttachmentIds = Array.isArray(note.attachment_ids) ? [...note.attachment_ids] : [];
        this._editAttachmentsMeta = {};
        this._mentionedEntityIds = this._extractMentionedIds(this._editDescription);
        this._formError = '';
    }

    _formatNoteDate(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return NOTE_DATE_FORMAT.format(parsed);
    }

    _formatSummaryTime(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return SUMMARY_TIME_FORMAT.format(parsed);
    }

    _summaryText() {
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        const text = attrs.ai_summary;
        if (typeof text !== 'string') {
            return '';
        }
        return text.trim();
    }

    _summaryGeneratedAt() {
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        const value = attrs.ai_summary_generated_at;
        if (typeof value !== 'string') {
            return '';
        }
        return this._formatSummaryTime(value);
    }

    _summaryEntities() {
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return [];
        }
        const items = attrs.ai_summary_entities;
        if (!Array.isArray(items)) {
            return [];
        }
        return items
            .filter((item) => typeof item === 'string' && item.trim().length > 0)
            .slice(0, 8);
    }

    _voiceContextChips() {
        const relationships = Array.isArray(this.card?.relationships)
            ? this.card.relationships
            : [];
        const noteId = this.note.entity_id;
        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        const findOutgoingTarget = (typeId) => {
            const rel = relationships.find(
                (r) => r.relationship_type === typeId && r.source_entity_id === noteId,
            );
            if (!rel) return null;
            const targetId = rel.target_entity_id;
            const related = cardRelated.find((e) => e.entity_id === targetId);
            if (!related) return null;
            return related.name && related.name.length > 0 ? related.name : targetId;
        };
        return {
            voice: findOutgoingTarget('note_voice'),
            context: findOutgoingTarget('in_context'),
        };
    }

    _relationshipTypeLabel(typeId) {
        if (!Array.isArray(this.relationshipTypes)) {
            return typeId;
        }
        const found = this.relationshipTypes.find((rt) => rt && rt.type_id === typeId);
        if (!found) return typeId;
        return typeof found.name === 'string' && found.name.length > 0 ? found.name : typeId;
    }

    _entityLabelById(entityId) {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return '';
        }
        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        const related = cardRelated.find((e) => e.entity_id === entityId);
        if (!related) return entityId;
        return typeof related.name === 'string' && related.name.length > 0 ? related.name : entityId;
    }

    _emitEntityOpen(entityId) {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        this.emit('entity-open', { entityId });
    }

    _onMarkdownClick(event) {
        const target = event.target;
        if (target === null || typeof target.closest !== 'function') return;
        const chip = target.closest('.mention-chip');
        if (chip === null) return;
        const entityId = chip.getAttribute('data-entity-id');
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        event.preventDefault();
        this._emitEntityOpen(entityId);
    }

    _onNameInput(e) { this._editName = e.target.value; }
    _onDescriptionInput(e) {
        this._editDescription = e.target.value;
        this._mentionedEntityIds = this._extractMentionedIds(this._editDescription);
        this._maybeOpenMention(e.target);
    }
    _onDescriptionKeydown(e) {
        if (!this._mentionOpen) return;
        if (e.key === 'Escape') {
            e.preventDefault();
            this._closeMention();
        }
    }
    _onDateChange(e) { this._editDate = e.target.value; }

    _extractMentionedIds(text) {
        const ids = new Set();
        if (typeof text !== 'string' || text.length === 0) return ids;
        let match;
        const re = new RegExp(MENTION_REGEX.source, 'g');
        while ((match = re.exec(text)) !== null) {
            ids.add(match[2]);
        }
        return ids;
    }

    _maybeOpenMention(textareaEl) {
        if (textareaEl === null || textareaEl === undefined) return;
        const caret = textareaEl.selectionStart;
        const value = textareaEl.value;
        if (typeof caret !== 'number') return;
        const triggerInfo = this._findMentionTrigger(value, caret);
        if (triggerInfo === null) {
            this._closeMention();
            return;
        }
        this._mentionTriggerIndex = triggerInfo.start;
        this._mentionQuery = triggerInfo.query;
        this._mentionOpen = true;
        if (this._mentionDebounce !== null) {
            clearTimeout(this._mentionDebounce);
        }
        if (this._mentionQuery.length === 0) {
            this._mentionResults = [];
            this._mentionLoading = false;
            return;
        }
        this._mentionLoading = true;
        this._mentionDebounce = setTimeout(() => {
            this._mentionDebounce = null;
            const namespace = this._currentNamespaceForSearch();
            const payload = { q: this._mentionQuery, limit: 10 };
            if (typeof namespace === 'string' && namespace.length > 0) {
                payload.namespace = namespace;
            }
            this._mentionRequestId = this._entitySearch.run(payload);
        }, 200);
    }

    _findMentionTrigger(value, caret) {
        if (typeof value !== 'string' || value.length === 0) return null;
        let i = caret - 1;
        while (i >= 0) {
            const ch = value[i];
            if (ch === '@') {
                const before = i === 0 ? '' : value[i - 1];
                if (before === '' || /\s/.test(before)) {
                    const query = value.slice(i + 1, caret);
                    if (query.length === 0) return { start: i, query };
                    if (/\s/.test(query)) return null;
                    return { start: i, query };
                }
                return null;
            }
            if (/\s/.test(ch)) return null;
            i -= 1;
        }
        return null;
    }

    _closeMention() {
        this._mentionOpen = false;
        this._mentionQuery = '';
        this._mentionResults = [];
        this._mentionLoading = false;
        this._mentionTriggerIndex = -1;
        if (this._mentionDebounce !== null) {
            clearTimeout(this._mentionDebounce);
            this._mentionDebounce = null;
        }
    }

    _currentNamespaceForSearch() {
        if (this.note !== null && typeof this.note.namespace === 'string' && this.note.namespace.length > 0) {
            return this.note.namespace;
        }
        if (typeof this.defaultNamespace === 'string' && this.defaultNamespace.length > 0) {
            return this.defaultNamespace;
        }
        return null;
    }

    _renderMentionPopover() {
        if (this._mentionLoading) {
            return html`
                <div class="mention-popover">
                    <div class="mention-empty">${this.t('note_edit.mention_searching')}</div>
                </div>
            `;
        }
        if (this._mentionQuery.length === 0) {
            return html`
                <div class="mention-popover">
                    <div class="mention-empty">${this.t('note_edit.mention_min_query')}</div>
                </div>
            `;
        }
        if (this._mentionResults.length === 0) {
            return html`
                <div class="mention-popover">
                    <div class="mention-empty">${this.t('note_edit.mention_no_results')}</div>
                </div>
            `;
        }
        return html`
            <div class="mention-popover">
                ${this._mentionResults.map((item) => html`
                    <button
                        type="button"
                        class="mention-row"
                        @click=${() => this._onMentionPick(item)}
                    >
                        <platform-icon name="link" size="12"></platform-icon>
                        <span class="mention-name">${item.name}</span>
                        <span class="mention-type">${typeof item.entity_type === 'string' ? item.entity_type : ''}</span>
                    </button>
                `)}
            </div>
        `;
    }

    _onMentionPick(item) {
        const textareaEl = this.renderRoot.querySelector('.description-edit');
        if (textareaEl === null) return;
        if (this._mentionTriggerIndex < 0) return;
        const before = this._editDescription.slice(0, this._mentionTriggerIndex);
        const triggerEnd = this._mentionTriggerIndex + 1 + this._mentionQuery.length;
        const after = this._editDescription.slice(triggerEnd);
        const insert = `@[${item.name}](${item.entity_id}) `;
        const next = `${before}${insert}${after}`;
        this._editDescription = next;
        this._mentionedEntityIds = new Set(this._mentionedEntityIds);
        this._mentionedEntityIds.add(item.entity_id);
        this._closeMention();
        const newCaret = before.length + insert.length;
        Promise.resolve().then(() => {
            const ta = this.renderRoot.querySelector('.description-edit');
            if (ta !== null) {
                ta.focus();
                ta.setSelectionRange(newCaret, newCaret);
            }
        });
    }

    _onTagDraftInput(e) { this._tagDraft = e.target.value; }
    _onTagDraftKeydown(e) {
        if (e.key !== 'Enter' && e.key !== ',') return;
        e.preventDefault();
        const value = this._tagDraft.trim().replace(/,$/, '');
        if (value.length === 0) return;
        if (this._editTags.indexOf(value) !== -1) {
            this._tagDraft = '';
            return;
        }
        this._editTags = [...this._editTags, value];
        this._tagDraft = '';
    }
    _onRemoveTag(tag) {
        this._editTags = this._editTags.filter((t) => t !== tag);
    }

    _onUploadClick() {
        const input = this.renderRoot.querySelector('input[type=file]');
        if (input !== null) input.click();
    }
    _onUploadFiles(e) {
        const fileList = e.target.files;
        if (fileList === null) return;
        const files = Array.from(fileList);
        for (const file of files) {
            this._fileUpload.run({ file });
        }
        e.target.value = '';
    }
    _onRemoveAttachment(fileId) {
        this._editAttachmentIds = this._editAttachmentIds.filter((id) => id !== fileId);
    }

    async _onVoiceToggle() {
        if (this._voiceState === 'recording') {
            if (this._mediaRecorder !== null && this._mediaRecorder.state === 'recording') {
                this._mediaRecorder.stop();
            }
            return;
        }
        if (this._voiceState !== 'idle') return;
        if (typeof window === 'undefined' || !window.isSecureContext) {
            this.toast('toast.note.voice_unavailable_https', { type: 'warning' });
            return;
        }
        if (!_hasGetUserMediaApi() || typeof MediaRecorder === 'undefined') {
            this.toast('toast.note.voice_unavailable_recorder', { type: 'warning' });
            return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = _pickVoiceMimeType();
        this._mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
        this._audioChunks = [];
        const resolvedMime = this._mediaRecorder.mimeType || mimeType || 'audio/webm';
        this._mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) this._audioChunks.push(e.data); };
        this._mediaRecorder.onstop = () => {
            stream.getTracks().forEach((t) => t.stop());
            this._voiceState = 'processing';
            const blob = new Blob(this._audioChunks, { type: resolvedMime });
            this._voice.run({ audio: blob, file_name: 'voice-input.webm' });
        };
        this._mediaRecorder.start();
        this._voiceState = 'recording';
    }

    _validateEdit() {
        if (this._editName.trim().length === 0 && this._editDescription.trim().length === 0) {
            return this.t('note_edit.err_name_or_description_required');
        }
        return null;
    }

    _buildEditBody() {
        const noteDate = this._editDate.length > 0 ? this._editDate : _todayDateInput();
        const body = {
            name: this._editName.trim().length > 0 ? this._editName.trim() : this.t('note_page.untitled'),
            description: this._editDescription.trim().length > 0 ? this._editDescription.trim() : null,
            attributes: {},
            tags: this._editTags,
            attachment_ids: this._editAttachmentIds,
            note_date: noteDate,
        };
        const mentionedIds = [...this._mentionedEntityIds];
        if (mentionedIds.length > 0) {
            body.mentioned_entity_ids = mentionedIds;
        }
        return body;
    }

    _onSaveEdit() {
        const error = this._validateEdit();
        if (typeof error === 'string') {
            this._formError = error;
            return;
        }
        this._formError = '';
        const body = this._buildEditBody();
        if (this.note === null) {
            const namespace = this.defaultNamespace;
            if (typeof namespace !== 'string' || namespace.length === 0) {
                this._formError = this.t('note_edit.err_namespace_required');
                return;
            }
            this._entities.create({
                entity_type: 'note',
                namespace,
                ...body,
            });
            return;
        }
        this._updateOp.run({
            id: this.note.entity_id,
            body,
        });
    }

    _onCancelEdit() {
        this.emit('cancel');
    }

    _attachmentLabel(fileId) {
        const meta = this._editAttachmentsMeta[fileId];
        if (meta && typeof meta.name === 'string' && meta.name.length > 0) return meta.name;
        return fileId;
    }

    _renderRelatedEntities() {
        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        const entities = cardRelated.filter(
            (e) => e && e.entity_id !== this.note.entity_id && this._entityKind(e) !== 'task',
        );
        if (entities.length === 0) {
            return html`<div class="related-empty">${this.t('note_view.no_related')}</div>`;
        }
        return html`
            <div class="related-list">
                ${entities.map((entity) => {
                    const tone = this._relatedTone(entity);
                    const subtitle = this._relatedSubtitle(entity);
                    const name = entity.name && entity.name.length > 0 ? entity.name : entity.entity_id;
                    const iconName = this._relatedIcon(entity);
                    return html`
                        <button
                            type="button"
                            class="related-card tone-${tone}"
                            @click=${() => this._emitEntityOpen(entity.entity_id)}
                        >
                            <span class="related-icon">
                                <platform-icon name=${iconName} size="32"></platform-icon>
                            </span>
                            <span class="related-body">
                                <p class="related-name">${name}</p>
                                ${subtitle.length > 0
                                    ? html`<p class="related-position">${subtitle}</p>`
                                    : ''}
                            </span>
                        </button>
                    `;
                })}
            </div>
        `;
    }

    _entityKind(entity) {
        if (!entity || typeof entity.entity_type !== 'string') return '';
        return entity.entity_type;
    }

    _relatedTone(entity) {
        const type = this._entityKind(entity);
        if (type === 'company' || type === 'organization' || type === 'team') return 'yellow';
        if (type === 'note' || type === 'event' || type === 'meeting' || type === 'document') return 'orange';
        return 'violet';
    }

    _relatedIcon(entity) {
        const type = this._entityKind(entity);
        if (type === 'company' || type === 'organization' || type === 'team') return 'building';
        if (type === 'note') return 'note';
        if (type === 'event' || type === 'meeting') return 'calendar';
        if (type === 'document') return 'folder';
        if (type === 'task') return 'check';
        return 'user';
    }

    _relatedSubtitle(entity) {
        if (entity && typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) {
            return entity.entity_subtype;
        }
        if (entity && typeof entity.entity_type === 'string') {
            return entity.entity_type;
        }
        return '';
    }

    _noteTasks() {
        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        return cardRelated.filter((e) => e && this._entityKind(e) === 'task');
    }

    _isTaskDone(task) {
        if (!task) return false;
        if (task.status === 'completed' || task.status === 'done') return true;
        if (task.attributes && (task.attributes.completed === true || task.attributes.is_done === true)) return true;
        return typeof task.completed_at === 'string' && task.completed_at.length > 0;
    }

    _onTaskToggle(taskId, nextDone) {
        if (typeof taskId !== 'string' || taskId.length === 0) return;
        this.emit('task-toggle', { entityId: taskId, completed: nextDone });
    }

    _onTaskRemove(taskId) {
        if (typeof taskId !== 'string' || taskId.length === 0) return;
        this.emit('task-remove', { entityId: taskId });
    }

    _onTaskAddKeydown(event) {
        if (event.key !== 'Enter' || event.shiftKey) return;
        const value = typeof event.target.value === 'string' ? event.target.value.trim() : '';
        if (value.length === 0) return;
        event.preventDefault();
        event.target.value = '';
        this.emit('task-add', { text: value });
    }

    _renderRelationships() {
        const noteId = this.note.entity_id;
        const cardRelationships = this.card !== null && Array.isArray(this.card.relationships)
            ? this.card.relationships
            : [];
        const relationships = cardRelationships.filter(
            (r) => r && r.relationship_type !== 'note_voice' && r.relationship_type !== 'in_context',
        );
        if (relationships.length === 0) {
            return html`<div class="panel-empty">${this.t('note_view.no_relationships')}</div>`;
        }
        return html`
            ${relationships.map((rel) => {
                const sourceId = rel.source_entity_id;
                const targetId = rel.target_entity_id;
                const isOutgoing = sourceId === noteId;
                const otherId = isOutgoing ? targetId : sourceId;
                const otherLabel = this._entityLabelById(otherId);
                const arrow = isOutgoing ? '→' : '←';
                return html`
                    <div class="relationship-row">
                        <p class="relationship-name">${this._relationshipTypeLabel(rel.relationship_type)}</p>
                        <div class="relationship-line">
                            <span>${this.t('note_view.this_note')}</span>
                            <span class="relationship-arrow">${arrow}</span>
                            <button
                                type="button"
                                class="entity-row"
                                style="padding: 2px 6px; width: auto; background: transparent;"
                                @click=${() => this._emitEntityOpen(otherId)}
                            >
                                <span class="entity-name">${otherLabel}</span>
                            </button>
                        </div>
                    </div>
                `;
            })}
        `;
    }

    _renderAttachments() {
        const attachments = Array.isArray(this.card?.attachments) ? this.card.attachments : [];
        if (attachments.length === 0) {
            return html`<div class="panel-empty">${this.t('note_view.no_attachments')}</div>`;
        }
        return html`
            ${attachments.map((att) => {
                const filename = typeof att.filename === 'string' && att.filename.length > 0
                    ? att.filename
                    : (typeof att.document_id === 'string' ? att.document_id : '—');
                const sizeText = formatBytes(att.size_bytes);
                const downloadUrl = typeof att.download_url === 'string' && att.download_url.length > 0
                    ? att.download_url
                    : '';
                return html`
                    <div class="attachment-row">
                        <span class="attachment-icon">
                            <platform-icon name="folder" size="16"></platform-icon>
                        </span>
                        <span class="attachment-info">
                            <p class="attachment-name">${filename}</p>
                            <p class="attachment-meta">
                                ${sizeText}${sizeText ? ' · ' : ''}${typeof att.status === 'string' ? att.status : ''}
                            </p>
                        </span>
                        ${downloadUrl ? html`
                            <a
                                class="attachment-link"
                                href=${downloadUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                download=${filename}
                            >
                                <platform-icon name="download" size="14"></platform-icon>
                                ${this.t('note_view.download')}
                            </a>
                        ` : nothing}
                    </div>
                `;
            })}
        `;
    }

    render() {
        if (this.mode === 'edit') {
            return this._renderEdit();
        }
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('CRMNoteCardView: .note is required for view mode');
        }
        return this._renderView();
    }

    _renderView() {
        const title = typeof this.note.name === 'string' && this.note.name.length > 0
            ? this.note.name
            : this.t('note_view.untitled');
        const description = typeof this.note.description === 'string' ? this.note.description : '';
        const dateText = this._formatNoteDate(
            this.note.note_date || this.note.updated_at || this.note.created_at,
        );
        const summaryText = this._summaryText();
        const summaryTime = this._summaryGeneratedAt();
        const summaryEntities = this._summaryEntities();
        const tasks = this._noteTasks();

        return html`
            <div class="layout">
                <section class="main">
                    <header class="header">
                        <div class="title-block">
                            <h1 class="title">${title}</h1>
                            ${dateText
                                ? html`<span class="note-date">${this.t('note_view.date_prefix', { date: dateText })}</span>`
                                : ''}
                        </div>
                        <div class="header-actions">
                            <button
                                type="button"
                                class="round-btn"
                                title=${this.t('note_view.action_show_graph')}
                                @click=${() => this.emit('show-graph')}
                            >
                                <platform-icon name="git-branch" size="20"></platform-icon>
                            </button>
                            <button
                                type="button"
                                class="round-btn danger"
                                title=${this.t('note_view.action_delete')}
                                @click=${() => this.emit('delete-note')}
                            >
                                <platform-icon name="trash" size="20"></platform-icon>
                            </button>
                            <button
                                type="button"
                                class="pill-btn"
                                title=${this.t('note_view.action_edit')}
                                @click=${() => this.emit('edit-note')}
                            >
                                <platform-icon name="edit" size="16"></platform-icon>
                                ${this.t('note_view.action_edit')}
                            </button>
                        </div>
                    </header>
                    ${description.length > 0
                        ? html`<article class="markdown" @click=${this._onMarkdownClick}>${unsafeHTML(renderMarkdownToHtml(description))}</article>`
                        : html`<p class="empty-text">${this.t('note_view.no_description')}</p>`}
                </section>

                <aside class="sidebar">
                    ${this._renderSummaryCard(summaryText, summaryTime, summaryEntities)}
                    ${this._renderTasksCard(tasks)}
                    ${this._renderRelatedSection()}
                    ${this._renderAttachmentsSection()}
                </aside>
            </div>
        `;
    }

    _renderSummaryCard(summaryText, summaryTime, summaryEntities) {
        return html`
            <section class="card summary-card">
                <div class="card-header">
                    <h3 class="card-title">
                        <platform-icon name="ai" size="20"></platform-icon>
                        ${this.t('note_view.summary_title')}
                    </h3>
                    <button
                        type="button"
                        class="round-btn"
                        title=${this.t('note_view.summary_refresh')}
                        @click=${() => this.emit('refresh-summary')}
                        style="width: 36px; height: 36px;"
                    >
                        <platform-icon name="refresh" size="16"></platform-icon>
                    </button>
                </div>
                ${summaryTime
                    ? html`<p class="summary-meta">${this.t('note_view.summary_generated_at', { time: summaryTime })}</p>`
                    : ''}
                ${summaryText.length > 0
                    ? html`<p class="summary-text">${summaryText}</p>`
                    : html`<p class="summary-text" style="color: var(--crm-note-text-muted);">${this.t('note_view.no_summary')}</p>`}
                ${summaryEntities.length > 0 ? html`
                    <div class="summary-tags">
                        ${summaryEntities.map((tag, idx) => {
                            const tone = ['violet', 'yellow', 'orange'][idx % 3];
                            return html`
                                <span class="summary-tag tag-${tone}">
                                    <platform-icon name="folder" size="12"></platform-icon>
                                    ${tag}
                                </span>
                            `;
                        })}
                    </div>
                ` : ''}
            </section>
        `;
    }

    _renderTasksCard(tasks) {
        return html`
            <section class="card tasks-card">
                <h3 class="card-title">${this.t('note_view.tasks_title')}</h3>
                <div class="tasks-list">
                    ${tasks.length === 0
                        ? html`<p class="related-empty">${this.t('note_view.no_tasks')}</p>`
                        : tasks.map((task) => {
                            const done = this._isTaskDone(task);
                            const text = task.name && task.name.length > 0 ? task.name : task.entity_id;
                            return html`
                                <div class="task-row">
                                    <button
                                        type="button"
                                        class="task-check ${done ? 'checked' : ''}"
                                        title=${done ? this.t('note_view.task_undone') : this.t('note_view.task_done')}
                                        @click=${() => this._onTaskToggle(task.entity_id, !done)}
                                    >
                                        ${done ? html`<platform-icon name="check" size="14"></platform-icon>` : ''}
                                    </button>
                                    <button
                                        type="button"
                                        class="task-text ${done ? 'done' : ''}"
                                        style="background: transparent; border: none; padding: 0; text-align: left; cursor: pointer; font: inherit;"
                                        @click=${() => this._emitEntityOpen(task.entity_id)}
                                    >${text}</button>
                                    <button
                                        type="button"
                                        class="task-remove"
                                        title=${this.t('note_view.task_remove')}
                                        @click=${() => this._onTaskRemove(task.entity_id)}
                                    >
                                        <platform-icon name="close" size="14"></platform-icon>
                                    </button>
                                </div>
                            `;
                        })}
                </div>
                <label class="task-add-input">
                    <platform-icon name="plus" size="18"></platform-icon>
                    <input
                        type="text"
                        placeholder=${this.t('note_view.task_add_placeholder')}
                        @keydown=${this._onTaskAddKeydown}
                    />
                </label>
            </section>
        `;
    }

    _renderRelatedSection() {
        return html`
            <section>
                <h3 class="card-title" style="margin-bottom: var(--space-4);">${this.t('note_view.related_entities')}</h3>
                ${this._renderRelatedEntities()}
            </section>
        `;
    }

    _renderAttachmentsSection() {
        const attachments = Array.isArray(this.card?.attachments) ? this.card.attachments : [];
        if (attachments.length === 0) return '';
        return html`
            <section>
                <h3 class="card-title" style="margin-bottom: var(--space-4);">${this.t('note_view.attachments')}</h3>
                ${this._renderAttachments()}
            </section>
        `;
    }

    _renderEdit() {
        const isCreate = this.note === null;
        const busy = isCreate ? this._entities.loading : this._updateOp.busy;
        const uploading = this._fileUpload.busy;

        return html`
            <div class="layout edit-mode">
                <section class="main">
                    <header class="header">
                        <div class="title-block">
                            <input
                                class="title-input"
                                type="text"
                                placeholder=${this.t('note_edit.placeholder_title')}
                                .value=${this._editName}
                                @input=${this._onNameInput}
                            />
                        </div>
                        <div class="header-actions">
                            <button
                                type="button"
                                class="round-btn"
                                title=${this.t('note_edit.action_cancel')}
                                @click=${() => this._onCancelEdit()}
                                ?disabled=${busy}
                            >
                                <platform-icon name="close" size="20"></platform-icon>
                            </button>
                            <button
                                type="button"
                                class="pill-btn"
                                ?disabled=${busy || uploading || this._voiceState === 'processing'}
                                @click=${() => this._onSaveEdit()}
                            >
                                <platform-icon name=${busy ? 'loader' : 'save'} size="16"></platform-icon>
                                ${busy
                                    ? this.t('note_edit.action_saving')
                                    : isCreate
                                        ? this.t('note_edit.action_create')
                                        : this.t('note_edit.action_save')}
                            </button>
                        </div>
                    </header>

                    <div class="edit-field">
                        <label class="edit-label">${this.t('note_edit.field_description')}</label>
                        <div class="description-edit-wrap">
                            <textarea
                                class="description-edit"
                                placeholder=${this.t('note_edit.placeholder_description')}
                                .value=${this._editDescription}
                                @input=${this._onDescriptionInput}
                                @keydown=${this._onDescriptionKeydown}
                            ></textarea>
                            <button
                                type="button"
                                class="voice-btn ${this._voiceState}"
                                title=${this._voiceState === 'recording'
                                    ? this.t('note_edit.voice_stop')
                                    : this.t('note_edit.voice_start')}
                                @click=${() => this._onVoiceToggle()}
                                ?disabled=${this._voiceState === 'processing'}
                            >
                                <platform-icon
                                    name=${this._voiceState === 'recording' ? 'square' : 'mic'}
                                    size="16"
                                ></platform-icon>
                            </button>
                            ${this._mentionOpen ? this._renderMentionPopover() : ''}
                        </div>
                    </div>

                    <div class="edit-row">
                        <div class="edit-field">
                            <label class="edit-label">${this.t('note_edit.field_date')}</label>
                            <input
                                class="date-input"
                                type="date"
                                .value=${this._editDate}
                                @change=${this._onDateChange}
                            />
                        </div>
                        <div class="edit-field">
                            <label class="edit-label">${this.t('note_edit.field_tags')}</label>
                            <div class="tags-wrap">
                                ${this._editTags.map((tag) => html`
                                    <span class="tag-chip">
                                        ${tag}
                                        <button type="button" @click=${() => this._onRemoveTag(tag)}>
                                            <platform-icon name="close" size="10"></platform-icon>
                                        </button>
                                    </span>
                                `)}
                                <input
                                    type="text"
                                    class="tag-input"
                                    placeholder=${this.t('note_edit.placeholder_tag')}
                                    .value=${this._tagDraft}
                                    @input=${this._onTagDraftInput}
                                    @keydown=${this._onTagDraftKeydown}
                                />
                            </div>
                        </div>
                    </div>

                    <div class="edit-field">
                        <label class="edit-label">${this.t('note_edit.field_attachments')}</label>
                        <div class="attachments-edit">
                            ${this._editAttachmentIds.map((fileId) => html`
                                <div class="attachment-edit-row">
                                    <platform-icon name="paperclip" size="14"></platform-icon>
                                    <span class="name">${this._attachmentLabel(fileId)}</span>
                                    <button
                                        type="button"
                                        class="icon-btn"
                                        title=${this.t('note_edit.attachment_remove')}
                                        @click=${() => this._onRemoveAttachment(fileId)}
                                    >
                                        <platform-icon name="close" size="12"></platform-icon>
                                    </button>
                                </div>
                            `)}
                            <button type="button" class="upload-btn" @click=${() => this._onUploadClick()}>
                                <platform-icon name="cloud" size="14"></platform-icon>
                                ${uploading
                                    ? this.t('note_edit.attachment_uploading')
                                    : this.t('note_edit.attachment_add')}
                            </button>
                            <input
                                type="file"
                                multiple
                                style="display: none;"
                                @change=${this._onUploadFiles}
                            />
                        </div>
                    </div>

                    ${this._formError.length > 0
                        ? html`<div class="form-error">${this._formError}</div>`
                        : ''}
                </section>
            </div>
        `;
    }
}

customElements.define('crm-note-card-view', CRMNoteCardView);
