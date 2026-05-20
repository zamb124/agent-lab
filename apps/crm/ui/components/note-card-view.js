/**
 * NoteCardView — карточка заметки CRM. Один компонент, два режима через
 * свойство `mode`:
 *
 *   - `view` (default): представление только для чтения с markdown, AI-сводкой,
 *     сайдбар (задачи, связанные объекты). Вложения — из шапки (popover).
 *     Текст вложений подставляется в тело заметки на сервере при загрузке.
 *     Шапка: attachments / (десктоп) переключатель графа / edit / delete.
 *     Родитель задаёт `mobileHeaderPanel`: `'' | 'summary' | 'neighbors' | 'graph'`.
 *     При `'graph'` в основной колонке только мини-граф (в других режимах canvas не монтируется);
 *     иначе markdown на высоту колонки со скроллом у `.main`.
 *     На узком экране блок `.mobile-header-panels` рендерится только для summary/neighbors.
 *   - `edit`: inline-форма — title, описание (с голосовым вводом), дата, теги,
 *     аплоад вложений. Текст из файлов добавляется в описание на сервере.
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
 *   - `mobileHeaderPanel` — оверлеи на мобилке и режим графа в колонке (страница заметки).
 *   - `markdownFormatting`, `markdownFormatProgress` — индикатор format Markdown (view): баннер под шапкой.
 *
 * Эмитит:
 *   - `edit-note`                — клик по карандашу в шапке view.
 *   - `delete-note`              — клик по корзине в шапке view.
 *   - `overlay-panel-toggle` { panel: 'graph' } — десктоп: переключить inline-граф (обрабатывает страница).
 *   - `entity-open` { entityId, entity_type? } — клик по связанной сущности или превью графа.
 *   - `cancel`                   — отмена в edit-режиме.
 *   - `saved` { entity }         — успешное сохранение существующей заметки.
 *   - `created` { entity }       — успешное создание новой заметки.
 *
 * Markdown рендерится через глобальный `window.marked`, подключённый в
 * `apps/crm/ui/index.html` (`/static/core/assets/js/marked.min.js`).
 */

import { html, css, nothing, render } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { selectCrmSidebarOrDefaultNamespace } from '../utils/crm-namespace-select.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-spinner.js';
import './entity-hover-preview.js';
import './crm-related-neighbor-rows.js';
import './crm-mini-graph.js';
import { relatedEntityCardSharedStyles } from '../styles/related-entity-card.styles.js';
import { extractNeighborEdges } from '../utils/neighbor-edges.js';
import { searchScorePercent, relationshipConfidencePercent } from '../utils/search-score-percent.js';
import {
    buildSummaryEntityLookupFromRelated,
    entityDisplayIconName,
    entityKind,
    fallbackEntityGlyph,
    resolveSummaryChipEntity,
    summaryChipUnresolvedIconName,
} from '../utils/related-entity-presenter.js';
import { NOTE_ROOT_ENTITY_TYPE_ID } from '../constants/entity-type-ids.js';
import { getUserMediaCompat, hasGetUserMediaApi, pickVoiceMimeType } from '@platform/lib/utils/voice-recording.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { escapeHtml as _escapeHtmlCanon } from '@platform/lib/utils/escape-html.js';
import { formatPlatformDate, formatPlatformTime } from '@platform/lib/utils/format-platform-date.js';
import { stripOuterMarkdownCodeFence } from '@platform/lib/utils/strip-outer-markdown-fence.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_UPDATE_OP = 'crm/entity_update';
const FILE_UPLOAD_OP = 'crm/file_upload';
const ATTACHMENT_UPLOAD_OP = 'crm/attachment_upload';
const ATTACHMENT_DELETE_OP = 'crm/attachment_delete';
const VOICE_OP = 'crm/note_voice_input';
const ENTITY_SEARCH_OP = 'crm/entity_search';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const NAMESPACES_NAME = 'crm/namespaces';
let NOTE_ATTACHMENT_INPUT_SEQ = 0;

const MENTION_REGEX = /@\[([^\]]+)\]\(([^)]+)\)/g;
const ENTITY_LINK_REGEX = /\[([^\]]+)\]\(entity:([^)]+)\)/g;

const NOTE_DATE_OPTIONS = Object.freeze({
    day: '2-digit',
    month: 'long',
    year: 'numeric',
});

const escapeHtml = _escapeHtmlCanon;

const MENTION_PLACEHOLDER_OPEN = '\u0001MENTION\u0002';
const MENTION_PLACEHOLDER_CLOSE = '\u0001/MENTION\u0002';

function _replaceMentionsWithPlaceholder(text) {
    const withMentionTokens = text.replace(MENTION_REGEX, (_match, name, id) => {
        const normalizedId = typeof id === 'string' && id.startsWith('entity:') ? id.slice('entity:'.length) : id;
        return `${MENTION_PLACEHOLDER_OPEN}${normalizedId}\u0001${name}${MENTION_PLACEHOLDER_CLOSE}`;
    });
    return withMentionTokens.replace(ENTITY_LINK_REGEX, (_match, name, id) => {
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
        const label = safeName.startsWith('@') ? safeName : `@${safeName}`;
        return `<span class="mention-chip" data-entity-id="${safeId}">${label}</span>`;
    });
}

function renderMarkdownToHtml(text) {
    const normalizedMd = stripOuterMarkdownCodeFence(typeof text === 'string' ? text : '');
    const withPlaceholders = _replaceMentionsWithPlaceholder(normalizedMd);
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
    return formatFileSize(value);
}

function _getFileExtension(filename) {
    if (typeof filename !== 'string') {
        return '';
    }
    const trimmed = filename.trim().toLowerCase();
    const dotIndex = trimmed.lastIndexOf('.');
    if (dotIndex <= 0 || dotIndex === trimmed.length - 1) {
        return '';
    }
    return trimmed.slice(dotIndex + 1);
}

function _resolveAttachmentIconName(filename, contentType) {
    const ext = _getFileExtension(filename);
    const mime = typeof contentType === 'string' ? contentType.toLowerCase() : '';
    if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'heic'].includes(ext)) {
        return 'image';
    }
    if (mime.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'].includes(ext)) {
        return 'microphone';
    }
    if (mime.startsWith('video/') || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) {
        return 'play';
    }
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
        return 'chart';
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
        return 'box';
    }
    if (mime === 'application/pdf' || ext === 'pdf') {
        return 'doc-detail';
    }
    if ([
        'doc', 'docx', 'txt', 'rtf', 'md', 'odt', 'ppt', 'pptx',
    ].includes(ext)) {
        return 'text-fields';
    }
    if ([
        'json', 'xml', 'yaml', 'yml', 'py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'sql',
    ].includes(ext)) {
        return 'code';
    }
    return 'paperclip';
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
        mobileHeaderPanel: { type: String },
        aiAnalyzing: { type: Boolean, attribute: 'ai-analyzing' },
        aiStatusText: { type: String, attribute: 'ai-status-text' },
        aiProgressPct: { type: Number, attribute: 'ai-progress-pct' },
        aiProgressStage: { type: String, attribute: 'ai-progress-stage' },
        aiProgressStatus: { type: String, attribute: 'ai-progress-status' },
        markdownFormatting: { type: Boolean, attribute: 'markdown-formatting' },
        markdownFormatProgress: { attribute: false },
        /** Узел в slot actions у page-header на мобилке; тулбар портится через lit render(). */
        mobileHeaderActionsHost: { attribute: false },
        mobileToolbarPorted: { type: Boolean, reflect: true, attribute: 'mobile-toolbar-ported' },
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
        _mentionHoverEntityId: { state: true },
        _mentionHoverAnchorRect: { state: true },
        _mentionPreviewOpen: { state: true },
        _attachmentsPopoverOpen: { state: true },
        _attachmentsPopoverMode: { state: true },
        _editSubtype: { state: true },
        _editVoiceEntityId: { state: true },
        _editContextEntityId: { state: true },
        _voiceSearchQuery: { state: true },
        _voiceSearchOpen: { state: true },
        _voiceSearchResults: { state: true },
        _voiceSearchLoading: { state: true },
        _contextSearchQuery: { state: true },
        _contextSearchOpen: { state: true },
        _contextSearchResults: { state: true },
        _contextSearchLoading: { state: true },
        _voiceSearchFilteredNoMatch: { state: true },
        _contextSearchFilteredNoMatch: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        relatedEntityCardSharedStyles,
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
                    align-content: start;
                    gap: var(--space-4);
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
            @media (max-width: 1023px) {
                .main,
                .sidebar {
                    overflow: visible;
                    padding-right: 0;
                }
            }

            /* ================== note header ================== */
            .header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-4);
                position: relative;
            }
            .title-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
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
            .desktop-graph-toggle {
                display: none;
            }
            @media (min-width: 768px) {
                .desktop-graph-toggle {
                    display: inline-flex;
                }
            }
            .desktop-graph-toggle.active {
                background: var(--accent);
                color: #ffffff;
            }
            .mobile-header-panels {
                display: none;
            }
            .attachments-menu {
                position: relative;
            }
            .attachments-badge {
                position: absolute;
                right: -2px;
                top: -2px;
                min-width: 18px;
                height: 18px;
                border-radius: 999px;
                background: var(--accent);
                color: #fff;
                font-size: 11px;
                line-height: 18px;
                text-align: center;
                padding: 0 5px;
                box-sizing: border-box;
                border: 1px solid var(--crm-surface-elevated, var(--glass-solid-strong));
                font-weight: 600;
            }
            .attachments-popover {
                position: absolute;
                top: calc(100% + 8px);
                right: 0;
                width: min(420px, 80vw);
                max-height: 360px;
                overflow: auto;
                z-index: 40;
                background: var(--crm-surface-elevated, var(--glass-solid-strong));
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .attachments-popover-row {
                display: grid;
                grid-template-columns: auto minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-2);
                padding: 8px;
                border-radius: var(--radius-md);
                background: transparent;
            }
            .attachments-popover-row:hover {
                background: var(--crm-note-action-bg);
            }
            .attachments-popover-info {
                min-width: 0;
            }
            .attachments-popover-name {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .attachments-popover-meta {
                margin: 0;
                font-size: 12px;
                line-height: 16px;
                color: var(--crm-note-text-muted);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .attachments-popover-actions {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            .attachment-action-btn {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: none;
                border-radius: var(--radius-full);
                background: transparent;
                color: var(--crm-note-text-muted);
                cursor: pointer;
                text-decoration: none;
            }
            .attachment-action-btn:hover {
                background: var(--crm-note-action-bg-hover);
                color: var(--text-primary);
            }
            .attachments-popover-empty {
                padding: 10px 12px;
                color: var(--crm-note-text-muted);
                font-size: 13px;
                line-height: 16px;
            }
            .visually-hidden-file-input {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                border: 0;
                opacity: 0;
                pointer-events: none;
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
            .note-primary-pane {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .note-text-scroll {
                flex: 1 1 auto;
                min-height: 0;
                max-height: none;
                overflow-x: hidden;
                overflow-y: visible;
                padding-right: var(--space-1);
                box-sizing: border-box;
            }
            .note-text-body-wrap {
                position: relative;
                min-height: 0;
            }
            .note-markdown-format-btn {
                position: absolute;
                top: var(--space-2);
                right: var(--space-2);
                z-index: 2;
                width: 36px;
                height: 36px;
                padding: 0;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-note-action-bg);
                color: var(--text-primary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
                transition: background var(--duration-fast), filter var(--duration-fast);
            }
            .note-markdown-format-btn:hover:not(:disabled) {
                background: var(--glass-tint-medium);
                filter: brightness(1.02);
            }
            .note-markdown-format-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .note-markdown-format-btn svg {
                display: block;
                flex-shrink: 0;
            }
            .note-markdown-format-banner {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                flex-shrink: 0;
                margin-bottom: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            .note-markdown-format-banner-main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .note-markdown-format-banner-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: 500;
            }
            .note-markdown-format-banner-pct {
                flex-shrink: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-weight: 600;
            }
            .note-markdown-format-banner-line {
                width: 100%;
                height: 6px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .note-markdown-format-banner-line > span {
                display: block;
                height: 100%;
                background: var(--accent);
                transition: width var(--duration-fast);
            }
            .note-markdown-format-banner-line.indeterminate {
                position: relative;
            }
            .note-markdown-format-banner-line.indeterminate > span {
                position: absolute;
                left: 0;
                top: 0;
                width: 32%;
                min-width: 48px;
                transition: none;
                animation: noteMarkdownProgressIndeterminate 1.15s ease-in-out infinite;
            }
            @keyframes noteMarkdownProgressIndeterminate {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(420%); }
            }
            .note-text-scroll.markdown-format-status-active .markdown {
                opacity: 0.55;
                transition: opacity var(--duration-fast);
            }
            .note-text-scroll .markdown {
                min-height: 0;
            }
            .markdown {
                box-sizing: border-box;
                min-height: 220px;
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
                color: var(--accent);
                border-radius: var(--radius-full);
                font-size: 0.95em;
                cursor: pointer;
                font-weight: 700;
                transition: filter var(--duration-fast), transform var(--duration-fast), background var(--duration-fast);
            }
            .mention-chip:hover {
                background: rgba(153, 166, 249, 0.28);
                transform: translateY(-1px);
            }

            .empty-text {
                font-size: 16px;
                line-height: 20px;
                color: var(--crm-note-text-muted);
                font-style: italic;
            }

            /* ================== inline graph (view) ================== */
            .note-graph-preview-host {
                flex: 1 1 auto;
                min-height: min(280px, 40vh);
                height: auto;
                max-height: none;
                display: flex;
                flex-direction: column;
                min-width: 0;
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                overflow: hidden;
                box-sizing: border-box;
            }
            .note-graph-preview-host crm-mini-graph {
                flex: 1 1 0%;
                min-height: 0;
                width: 100%;
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
            .summary-analysis-error {
                margin: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .summary-analysis-error-title {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                font-weight: 700;
                color: var(--error);
            }
            .summary-analysis-error-detail {
                margin: 0;
                font-size: 13px;
                line-height: 18px;
                font-weight: 500;
                color: var(--error);
                opacity: 0.92;
                white-space: pre-wrap;
                word-break: break-word;
            }
            .summary-analysis-error-hint {
                margin: 0;
                font-size: 12px;
                line-height: 16px;
                color: var(--crm-note-text-muted);
            }
            .summary-status {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                color: var(--text-secondary);
            }
            .summary-status.analyzing {
                animation: summaryPulse 1.25s ease-in-out infinite;
            }
            .summary-refresh-icon.spinning {
                animation: summarySpin 1s linear infinite;
            }
            .summary-progress {
                margin: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .summary-progress-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .summary-progress-stage {
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .summary-progress-pct {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .summary-progress-line {
                width: 100%;
                height: 6px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .summary-progress-line > span {
                display: block;
                height: 100%;
                background: var(--accent);
                transition: width var(--duration-fast);
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
            .summary-tag.summary-tag--clickable {
                cursor: pointer;
                border: none;
                font: inherit;
                box-sizing: border-box;
            }
            .summary-tag.summary-tag--clickable:hover {
                filter: brightness(1.12);
            }

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

            @media (max-width: 767px) {
                :host([mobile-toolbar-ported]) .header .header-actions {
                    display: none;
                }
                .sidebar > .summary-card,
                .sidebar > .neighbors-section {
                    display: none;
                }
                .header {
                    flex-direction: column;
                    align-items: stretch;
                    gap: var(--space-3);
                }
                .title {
                    font-size: 24px;
                    line-height: 30px;
                }
                .title-input {
                    font-size: 24px;
                    line-height: 30px;
                }
                .header-actions {
                    width: 100%;
                    max-width: 100%;
                    gap: var(--space-2);
                    overflow: visible;
                    padding-bottom: 2px;
                }
                .mobile-header-panels {
                    display: block;
                    position: fixed;
                    top: calc(env(safe-area-inset-top, 0px) + 72px);
                    right: var(--space-3);
                    width: min(340px, calc(100vw - 24px));
                    z-index: 70;
                    max-height: min(320px, calc(100vh - 140px));
                    overflow: auto;
                    border: 1px solid var(--crm-stroke);
                    border-radius: var(--radius-lg);
                    background: var(--crm-surface-elevated, var(--glass-solid-strong));
                    box-shadow: var(--glass-shadow-medium);
                    padding: var(--space-2);
                }
                .mobile-header-panels::before {
                    content: '';
                    position: fixed;
                    top: calc(env(safe-area-inset-top, 0px) + 64px);
                    right: 58px;
                    width: 14px;
                    height: 14px;
                    border-left: 1px solid var(--crm-stroke);
                    border-top: 1px solid var(--crm-stroke);
                    background: var(--crm-surface-elevated, var(--glass-solid-strong));
                    transform: rotate(45deg);
                }
                .mobile-header-panels > .card,
                .mobile-header-panels > .neighbors-section {
                    position: relative;
                    z-index: 1;
                    max-height: none;
                    box-shadow: none;
                }
                .mobile-header-panels > .neighbors-section {
                    padding: var(--space-3);
                    border-radius: var(--radius-md);
                    background: var(--crm-surface-elevated, var(--glass-solid-strong));
                }
                .round-btn {
                    width: 40px;
                    height: 40px;
                    flex: 0 0 40px;
                }
                .pill-btn {
                    width: 40px;
                    flex: 0 0 40px;
                    justify-content: center;
                    height: 40px;
                    padding: 0;
                    gap: 0;
                    font-size: 0;
                    line-height: 0;
                }
                .attachments-popover {
                    position: fixed;
                    left: var(--space-3);
                    right: var(--space-3);
                    top: auto;
                    width: auto;
                    max-height: min(360px, calc(100vh - 160px));
                }
                .card {
                    padding: var(--space-4);
                }
                .card-header {
                    align-items: flex-start;
                }
                .summary-tags {
                    gap: var(--space-2);
                }
                .summary-tag {
                    max-width: 100%;
                    white-space: normal;
                    text-align: left;
                }
                .task-add-input {
                    padding: 10px 14px;
                }
            }

            .panel-empty {
                font-size: 14px;
                line-height: 18px;
                color: var(--crm-note-text-muted);
            }

            /* ================== EDIT inputs ================== */
            .note-semantics-edit {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                margin-bottom: var(--space-2);
            }
            .note-semantics-edit.semantics-toolbar {
                flex-direction: column;
            }
            @media (min-width: 901px) {
                .note-semantics-edit.semantics-toolbar {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
                    gap: var(--space-3);
                    align-items: start;
                }
                .note-semantics-edit.semantics-toolbar .semantics-field {
                    min-width: 0;
                }
                .note-semantics-edit.semantics-toolbar platform-field {
                    min-width: 0;
                }
            }
            .semantics-hint {
                margin: 0;
                font-size: 11px;
                line-height: 14px;
                color: var(--crm-note-text-muted);
                font-weight: 400;
            }
            .note-semantics-edit .semantics-field.picker-field .entity-search-wrap {
                position: relative;
                display: flex;
                align-items: center;
                min-height: 0;
                width: 100%;
                box-sizing: border-box;
            }
            .semantics-picker-pill .entity-search-wrap input[data-canon='search-as-you-type'] {
                box-sizing: border-box;
                flex: 1;
                min-width: 0;
                width: auto;
                padding-right: 36px;
            }
            .semantics-clear {
                position: absolute;
                right: 8px;
                top: 50%;
                transform: translateY(-50%);
                width: 28px;
                height: 28px;
                border: none;
                border-radius: var(--radius-full);
                background: transparent;
                color: var(--crm-note-text-muted);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }
            .semantics-clear:hover {
                background: var(--crm-note-action-bg);
                color: var(--text-primary);
            }
            .view-meta-ribbon {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .meta-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-note-action-bg);
                color: var(--text-primary);
                font-size: 13px;
                line-height: 18px;
                font-weight: 500;
                cursor: pointer;
                font-family: inherit;
            }
            .meta-pill:hover {
                background: var(--crm-note-action-bg-hover);
            }
            .meta-pill.kind-pill {
                cursor: default;
                background: var(--glass-tint-medium);
            }
            .meta-pill.context-pill {
                border-color: var(--glass-border-medium);
            }
            .description-edit-wrap {
                position: relative;
            }
            .note-description-pill .description-edit {
                box-sizing: border-box;
                width: 100%;
                min-height: 220px;
                padding-right: 56px;
                resize: vertical;
            }
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
                align-items: start;
            }
            @media (max-width: 700px) {
                .edit-row { grid-template-columns: 1fr; }
            }
            .edit-row platform-field {
                min-width: 0;
            }

            .tags-wrap {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 8px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-note-input-bg);
            }
            .tags-field-pill .tags-wrap {
                border: none;
                background: transparent;
                padding: 0;
                align-items: center;
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

            .mention-popover--entity-list {
                display: flex;
                flex-direction: column;
                min-width: 0;
            }

            .mention-row {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                margin: 0;
                padding: var(--space-2) var(--space-3);
                box-sizing: border-box;
                border: none;
                border-bottom: 1px solid var(--crm-stroke);
                border-radius: 0;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: 14px;
                line-height: 1.3;
                text-align: left;
                cursor: pointer;
                -webkit-appearance: none;
                appearance: none;
            }

            .mention-row:last-child {
                border-bottom: none;
            }

            .mention-row:hover,
            .mention-row:focus-visible {
                background: var(--crm-note-action-bg);
                outline: none;
            }

            .mention-row-lead {
                flex-shrink: 0;
                width: 36px;
                height: 36px;
                border-radius: var(--radius-md);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-medium);
                color: var(--accent);
            }

            .mention-row-body {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
                align-items: flex-start;
            }

            .mention-row .mention-name {
                font-weight: 500;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                width: 100%;
                max-width: 100%;
            }

            .mention-row .mention-type {
                font-size: 12px;
                line-height: 1.2;
                color: var(--crm-note-text-muted);
            }

            @keyframes summarySpin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }

            @keyframes summaryPulse {
                0%, 100% { opacity: 0.55; }
                50% { opacity: 1; }
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
        this.mobileHeaderPanel = '';
        this.aiAnalyzing = false;
        this.aiStatusText = '';
        this.aiProgressPct = 0;
        this.aiProgressStage = '';
        this.aiProgressStatus = '';
        this.markdownFormatting = false;
        this.markdownFormatProgress = null;
        this.mobileHeaderActionsHost = null;
        this.mobileToolbarPorted = false;
        this._lastMobileToolbarPortHost = null;
        this._onMobileToolbarPortResize = () => this._syncMobileToolbarPort();

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
        this._mentionHoverEntityId = '';
        this._mentionHoverAnchorRect = null;
        this._mentionPreviewOpen = false;
        this._mentionedEntityIds = new Set();
        this._mentionTriggerIndex = -1;
        this._mentionDebounce = null;
        this._mentionRequestId = null;
        this._entitySearchPurpose = 'mention';

        this._voiceSearchRequestId = null;
        this._contextSearchRequestId = null;
        this._mentionPreviewCloseTimer = null;
        this._mentionPreviewPinned = false;
        this._attachmentsPopoverOpen = false;
        this._attachmentsPopoverMode = '';
        this._attachmentsPopoverCloseTimer = null;
        NOTE_ATTACHMENT_INPUT_SEQ += 1;
        this._attachmentInputId = `crm-note-attachment-input-${NOTE_ATTACHMENT_INPUT_SEQ}`;

        this._editSubtype = '';
        this._editVoiceEntityId = '';
        this._editContextEntityId = '';
        this._voiceSearchQuery = '';
        this._voiceSearchOpen = false;
        this._voiceSearchResults = [];
        this._voiceSearchLoading = false;
        this._voiceSearchFilteredNoMatch = false;
        this._contextSearchQuery = '';
        this._contextSearchOpen = false;
        this._contextSearchResults = [];
        this._contextSearchLoading = false;
        this._contextSearchFilteredNoMatch = false;
        this._voiceSearchDeb = null;
        this._contextSearchDeb = null;

        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME, { autoload: false });
        this._namespacesRes = this.useResource(NAMESPACES_NAME, { autoload: true });
        this._updateOp = this.useOp(ENTITY_UPDATE_OP);
        this._fileUpload = this.useOp(FILE_UPLOAD_OP);
        this._attachmentUpload = this.useOp(ATTACHMENT_UPLOAD_OP);
        this._attachmentDelete = this.useOp(ATTACHMENT_DELETE_OP);
        this._voice = this.useOp(VOICE_OP);
        this._entitySearch = this.useOp(ENTITY_SEARCH_OP);
        this._graphView = this.useSlice('crm/graph_view');
        this._uploadTargetMode = 'edit';

        this._crmSidebarDefaultNsSel = this.select(selectCrmSidebarOrDefaultNamespace);
        this._localeSel = this.select((s) => {
            const loc = s.i18n && typeof s.i18n.locale === 'string' ? s.i18n.locale.trim() : '';
            if (loc.length > 0) {
                return loc;
            }
            return 'en';
        });
    }

    connectedCallback() {
        super.connectedCallback();

        this._hydrateEditFromNote();

        this.useEvent(this._entities.resource.events.CREATED, (event) => {
            const created = event.payload && event.payload.item;
            if (!created || typeof created !== 'object') return;
            if (created.entity_type !== NOTE_ROOT_ENTITY_TYPE_ID) return;
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
            const uploadedSize = typeof result.file_size === 'number'
                ? result.file_size
                : (typeof result.size_bytes === 'number' ? result.size_bytes : 0);
            const uploadedUrl = typeof result.url === 'string' && result.url.length > 0
                ? result.url
                : (typeof result.download_url === 'string' ? result.download_url : '');
            this._editAttachmentIds = [...this._editAttachmentIds, result.file_id];
            this._editAttachmentsMeta = {
                ...this._editAttachmentsMeta,
                [result.file_id]: {
                    name: result.original_name || result.file_id,
                    size: uploadedSize,
                    content_type: result.content_type,
                    download_url: uploadedUrl,
                },
            };
        });

        this.useEvent(this._attachmentUpload.op.events.SUCCEEDED, (event) => {
            if (this.mode !== 'view') {
                return;
            }
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result !== 'object') {
                return;
            }
            if (result.markdown_format_queued !== true) {
                return;
            }
            this.emit('markdown-format-attachment-queued');
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
            const cid = meta && typeof meta.causation_id === 'string' ? meta.causation_id : null;
            const purpose = this._entitySearchPurpose;
            const result = event && event.payload && event.payload.result;
            const rawItems = result && Array.isArray(result.items) ? result.items : [];

            if (purpose === 'mention') {
                if (this._mentionRequestId === null || cid !== this._mentionRequestId) return;
                this._mentionResults = rawItems.filter(
                    (it) => this.note === null || it.entity_id !== this.note.entity_id,
                );
                this._mentionLoading = false;
                return;
            }
            if (purpose === 'voice') {
                if (this._voiceSearchRequestId === null || cid !== this._voiceSearchRequestId) return;
                const allow = this._voiceTargetTypeIdSet();
                const filtered = rawItems.filter(
                    (it) => typeof it.entity_type === 'string' && allow.has(it.entity_type),
                );
                this._voiceSearchFilteredNoMatch = rawItems.length > 0 && filtered.length === 0;
                this._voiceSearchResults = filtered;
                this._voiceSearchLoading = false;
                return;
            }
            if (purpose === 'context') {
                if (this._contextSearchRequestId === null || cid !== this._contextSearchRequestId) return;
                const allow = this._contextAnchorTypeIdSet();
                const filtered = rawItems.filter(
                    (it) => typeof it.entity_type === 'string' && allow.has(it.entity_type),
                );
                this._contextSearchFilteredNoMatch = rawItems.length > 0 && filtered.length === 0;
                this._contextSearchResults = filtered;
                this._contextSearchLoading = false;
            }
        });
        this.useEvent(this._entitySearch.op.events.FAILED, (event) => {
            const meta = event && event.meta;
            const cid = meta && typeof meta.causation_id === 'string' ? meta.causation_id : null;
            const purpose = this._entitySearchPurpose;
            if (purpose === 'mention') {
                if (this._mentionRequestId === null || cid !== this._mentionRequestId) return;
                this._mentionResults = [];
                this._mentionLoading = false;
                return;
            }
            if (purpose === 'voice') {
                if (this._voiceSearchRequestId === null || cid !== this._voiceSearchRequestId) return;
                this._voiceSearchResults = [];
                this._voiceSearchFilteredNoMatch = false;
                this._voiceSearchLoading = false;
                return;
            }
            if (purpose === 'context') {
                if (this._contextSearchRequestId === null || cid !== this._contextSearchRequestId) return;
                this._contextSearchResults = [];
                this._contextSearchFilteredNoMatch = false;
                this._contextSearchLoading = false;
            }
        });

        window.addEventListener('resize', this._onMobileToolbarPortResize);
    }

    disconnectedCallback() {
        if (this._mentionDebounce !== null) {
            clearTimeout(this._mentionDebounce);
            this._mentionDebounce = null;
        }
        if (this._voiceSearchDeb !== null) {
            clearTimeout(this._voiceSearchDeb);
            this._voiceSearchDeb = null;
        }
        if (this._contextSearchDeb !== null) {
            clearTimeout(this._contextSearchDeb);
            this._contextSearchDeb = null;
        }
        if (this._mentionPreviewCloseTimer !== null) {
            clearTimeout(this._mentionPreviewCloseTimer);
            this._mentionPreviewCloseTimer = null;
        }
        if (this._attachmentsPopoverCloseTimer !== null) {
            clearTimeout(this._attachmentsPopoverCloseTimer);
            this._attachmentsPopoverCloseTimer = null;
        }
        window.removeEventListener('resize', this._onMobileToolbarPortResize);
        this._teardownMobileToolbarPortRendering();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (
            changed.has('note')
            || changed.has('card')
            || changed.has('defaultNamespace')
            || changed.has('mode')
        ) {
            this._reloadNoteEntityTypesList();
            if (this.mode === 'edit') {
                this._hydrateEditFromNote();
            }
        }
        if (this.note === null && this.mode !== 'edit') {
            this.mode = 'edit';
        }
    }

    _reloadNoteEntityTypesList() {
        const ns = this._effectiveNamespace();
        if (typeof ns !== 'string' || ns.length === 0) {
            return;
        }
        this._entityTypes.load({ namespace: ns, limit: 200, offset: 0 });
    }

    _effectiveNamespace() {
        if (this.note !== null && typeof this.note.namespace === 'string' && this.note.namespace.length > 0) {
            return this.note.namespace;
        }
        if (typeof this.defaultNamespace === 'string' && this.defaultNamespace.trim().length > 0) {
            return this.defaultNamespace.trim();
        }
        const sel = this._crmSidebarDefaultNsSel;
        if (sel && typeof sel.value === 'string' && sel.value.length > 0) {
            return sel.value;
        }
        return 'default';
    }

    _namespaceRecord() {
        const ns = this._effectiveNamespace();
        if (typeof ns !== 'string' || ns.length === 0) {
            return undefined;
        }
        const res = this._namespacesRes;
        if (res === undefined || res === null || typeof res.byId !== 'object' || res.byId === null) {
            return undefined;
        }
        return res.byId[ns];
    }

    _namespaceCrmSettings() {
        const row = this._namespaceRecord();
        if (row === undefined || row === null) {
            return null;
        }
        const cs = row.crm_settings;
        if (cs === undefined || cs === null || typeof cs !== 'object') {
            return null;
        }
        return cs;
    }

    _showNoteVoiceAuthorUi() {
        const cs = this._namespaceCrmSettings();
        if (cs !== null && cs.show_note_voice_ui === false) {
            return false;
        }
        return true;
    }

    _entityTypeItems() {
        const ctrl = this._entityTypes;
        if (
            ctrl === undefined
            || ctrl === null
            || ctrl.items === undefined
            || !Array.isArray(ctrl.items)
        ) {
            return [];
        }
        return ctrl.items;
    }

    _voiceTargetTypeIdSet() {
        const ids = new Set();
        const items = this._entityTypeItems();
        for (const row of items) {
            if (typeof row !== 'object' || row === null) continue;
            if (typeof row.type_id !== 'string' || row.type_id.length === 0) continue;
            if (row.is_voice_target === true) {
                ids.add(row.type_id);
            }
        }
        return ids;
    }

    _contextAnchorTypeIdSet() {
        const ids = new Set();
        const items = this._entityTypeItems();
        for (const row of items) {
            if (typeof row !== 'object' || row === null) continue;
            if (typeof row.type_id !== 'string' || row.type_id.length === 0) continue;
            if (row.is_context_anchor === true) {
                ids.add(row.type_id);
            }
        }
        return ids;
    }

    _contextAnchorSearchPlaceholder() {
        const ids = [...this._contextAnchorTypeIdSet()];
        if (ids.length === 0) {
            return this.t('note_edit.context_anchor_search');
        }
        const parts = ids
            .map((typeId) => this._subtypeNameByTypeId(typeId))
            .filter((label) => label.length > 0);
        if (parts.length === 0) {
            return this.t('note_edit.context_anchor_search');
        }
        const typesLabel = parts.slice(0, 16).join(', ');
        return this.t('note_edit.context_anchor_search_types', { types: typesLabel });
    }

    _noteFamilySubtypeSelectableIdsSorted() {
        const types = this._entityTypeItems();
        if (types.length === 0) {
            return [];
        }
        const noteRow = types.find(
            (row) => typeof row === 'object' && row !== null && row.type_id === NOTE_ROOT_ENTITY_TYPE_ID,
        );
        if (noteRow === undefined) {
            return [];
        }
        const childrenByParent = new Map();
        for (const row of types) {
            if (typeof row !== 'object' || row === null) continue;
            if (typeof row.type_id !== 'string' || row.type_id.length === 0) continue;
            const p =
                typeof row.parent_type_id === 'string' && row.parent_type_id.length > 0
                    ? row.parent_type_id
                    : '';
            const list = childrenByParent.has(p) ? childrenByParent.get(p) : [];
            list.push(row.type_id);
            childrenByParent.set(p, list);
        }
        const out = [];
        const queue = [NOTE_ROOT_ENTITY_TYPE_ID];
        while (queue.length > 0) {
            const cur = queue.shift();
            const rawKids = childrenByParent.get(cur);
            const kids =
                rawKids !== undefined && Array.isArray(rawKids) ? rawKids : [];
            for (const k of kids) {
                if (k !== NOTE_ROOT_ENTITY_TYPE_ID) {
                    out.push(k);
                }
                queue.push(k);
            }
        }
        const nameById = new Map();
        for (const row of types) {
            if (typeof row !== 'object' || row === null) continue;
            if (typeof row.type_id !== 'string') continue;
            const label = typeof row.name === 'string' && row.name.length > 0 ? row.name : row.type_id;
            nameById.set(row.type_id, label.toLowerCase());
        }
        out.sort((a, b) => {
            const la = nameById.has(a) ? nameById.get(a) : a;
            const lb = nameById.has(b) ? nameById.get(b) : b;
            if (la < lb) return -1;
            if (la > lb) return 1;
            return a.localeCompare(b);
        });
        return out;
    }

    _subtypeNameByTypeId(typeId) {
        if (typeof typeId !== 'string' || typeId.length === 0) {
            return '';
        }
        const items = this._entityTypeItems();
        for (const row of items) {
            if (typeof row !== 'object' || row === null) continue;
            if (row.type_id === typeId) {
                if (typeof row.name === 'string' && row.name.length > 0) {
                    return row.name;
                }
                return typeId;
            }
        }
        return typeId;
    }

    _pickerIconNameForItem(item) {
        if (!item || typeof item !== 'object') {
            return fallbackEntityGlyph();
        }
        return entityDisplayIconName(item, this._entityTypeItems());
    }

    _pickerTypeLabelForItem(item) {
        if (!item || typeof item !== 'object') {
            return '';
        }
        const root = typeof item.entity_type === 'string' ? item.entity_type.trim() : '';
        const sub = typeof item.entity_subtype === 'string' ? item.entity_subtype.trim() : '';
        if (sub.length > 0) {
            return `${this._subtypeNameByTypeId(root)} / ${this._subtypeNameByTypeId(sub)}`;
        }
        return this._subtypeNameByTypeId(root);
    }

    _hydrateGraphEditorsFromCard() {
        if (this.note === null) {
            this._editVoiceEntityId = '';
            this._editContextEntityId = '';
            return;
        }
        const relationships = Array.isArray(this.card?.relationships) ? this.card.relationships : [];
        const noteId = this.note.entity_id;
        const v = relationships.find(
            (r) => r.relationship_type === 'note_voice' && r.source_entity_id === noteId,
        );
        this._editVoiceEntityId =
            typeof v?.target_entity_id === 'string' && v.target_entity_id.length > 0
                ? v.target_entity_id
                : '';
        const c = relationships.find(
            (r) => r.relationship_type === 'in_context' && r.source_entity_id === noteId,
        );
        this._editContextEntityId =
            typeof c?.target_entity_id === 'string' && c.target_entity_id.length > 0
                ? c.target_entity_id
                : '';

        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        let voiceLabel = '';
        if (this._editVoiceEntityId.length > 0) {
            const row = cardRelated.find((x) => x.entity_id === this._editVoiceEntityId);
            voiceLabel =
                row !== null && row !== undefined && typeof row.name === 'string' && row.name.length > 0
                    ? row.name
                    : this._editVoiceEntityId;
        }
        let ctxLabel = '';
        if (this._editContextEntityId.length > 0) {
            const rowCtx = cardRelated.find((x) => x.entity_id === this._editContextEntityId);
            ctxLabel =
                rowCtx !== null
                && rowCtx !== undefined
                && typeof rowCtx.name === 'string'
                && rowCtx.name.length > 0
                    ? rowCtx.name
                    : this._editContextEntityId;
        }
        if (voiceLabel.length > 0) {
            this._voiceSearchQuery = voiceLabel;
        }
        if (ctxLabel.length > 0) {
            this._contextSearchQuery = ctxLabel;
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
            this._editSubtype = '';
            this._editVoiceEntityId = '';
            this._editContextEntityId = '';
            this._voiceSearchQuery = '';
            this._contextSearchQuery = '';
            this._voiceSearchOpen = false;
            this._contextSearchOpen = false;
            this._voiceSearchResults = [];
            this._voiceSearchLoading = false;
            this._voiceSearchFilteredNoMatch = false;
            this._contextSearchResults = [];
            this._contextSearchLoading = false;
            this._contextSearchFilteredNoMatch = false;
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
        const subRaw = typeof note.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        this._editSubtype = subRaw.length > 0 ? subRaw : '';
        this._hydrateGraphEditorsFromCard();
    }

    _activeLocale() {
        const raw = this._localeSel.value;
        return typeof raw === 'string' && raw.length > 0 ? raw : 'en';
    }

    _formatNoteDate(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return formatPlatformDate(parsed, this._activeLocale(), NOTE_DATE_OPTIONS);
    }

    _formatSummaryTime(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return formatPlatformTime(parsed, this._activeLocale());
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

    _noteAnalysisErrorMessage() {
        const note = this.note;
        if (!note || typeof note !== 'object') {
            return '';
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        const msg = attrs.ai_analysis_last_error;
        if (typeof msg !== 'string') {
            return '';
        }
        return msg.trim();
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
            if (!rel || typeof rel.target_entity_id !== 'string' || rel.target_entity_id.length === 0) {
                return null;
            }
            const targetId = rel.target_entity_id;
            const related = cardRelated.find((e) => e.entity_id === targetId);
            const label =
                related !== undefined
                && typeof related.name === 'string'
                && related.name.length > 0
                    ? related.name
                    : targetId;
            const entity_type =
                related !== undefined && typeof related.entity_type === 'string'
                    ? related.entity_type
                    : '';
            const entity_subtype =
                related !== undefined && typeof related.entity_subtype === 'string'
                    ? related.entity_subtype
                    : '';
            return { entity_id: targetId, label, entity_type, entity_subtype };
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

    _emitEntityOpen(entityId, entityType) {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        if (typeof entityType === 'string' && entityType.trim().length > 0) {
            this.emit('entity-open', { entityId, entity_type: entityType.trim() });
            return;
        }
        this.emit('entity-open', { entityId });
    }

    _openMentionPreview(chip) {
        const entityId = chip.getAttribute('data-entity-id');
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        if (this._mentionPreviewCloseTimer !== null) {
            clearTimeout(this._mentionPreviewCloseTimer);
            this._mentionPreviewCloseTimer = null;
        }
        const rect = chip.getBoundingClientRect();
        this._mentionHoverEntityId = entityId;
        this._mentionHoverAnchorRect = {
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
        };
        this._mentionPreviewOpen = true;
    }

    _closeMentionPreviewNow() {
        if (this._mentionPreviewCloseTimer !== null) {
            clearTimeout(this._mentionPreviewCloseTimer);
            this._mentionPreviewCloseTimer = null;
        }
        this._mentionPreviewOpen = false;
        this._mentionHoverEntityId = '';
        this._mentionHoverAnchorRect = null;
        this._mentionPreviewPinned = false;
    }

    _scheduleMentionPreviewClose() {
        if (this._mentionPreviewPinned) {
            return;
        }
        if (this._mentionPreviewCloseTimer !== null) {
            clearTimeout(this._mentionPreviewCloseTimer);
        }
        this._mentionPreviewCloseTimer = window.setTimeout(() => {
            this._mentionPreviewCloseTimer = null;
            if (!this._mentionPreviewPinned) {
                this._closeMentionPreviewNow();
            }
        }, 120);
    }

    _closestMentionChipFromTarget(target) {
        if (target === null || target === undefined) {
            return null;
        }
        const el = target instanceof Element
            ? target
            : (target instanceof Node ? target.parentElement : null);
        if (el === null || typeof el.closest !== 'function') {
            return null;
        }
        return el.closest('.mention-chip');
    }

    _onMarkdownMouseMove(event) {
        const chip = this._closestMentionChipFromTarget(event.target);
        if (chip === null) {
            return;
        }
        this._openMentionPreview(chip);
    }

    _onMarkdownMouseLeave(event) {
        const relatedTarget = event ? event.relatedTarget : null;
        if (relatedTarget instanceof Node && this.renderRoot.contains(relatedTarget)) {
            const inPreview = relatedTarget.closest && relatedTarget.closest('crm-entity-hover-preview');
            if (inPreview) {
                return;
            }
        }
        this._scheduleMentionPreviewClose();
    }

    _onPreviewEnter() {
        this._mentionPreviewPinned = true;
        if (this._mentionPreviewCloseTimer !== null) {
            clearTimeout(this._mentionPreviewCloseTimer);
            this._mentionPreviewCloseTimer = null;
        }
    }

    _onPreviewLeave() {
        this._mentionPreviewPinned = false;
        this._scheduleMentionPreviewClose();
    }

    _onPreviewOpen(event) {
        const entityId = event.detail && typeof event.detail.entityId === 'string'
            ? event.detail.entityId
            : this._mentionHoverEntityId;
        this._closeMentionPreviewNow();
        this._emitEntityOpen(entityId);
    }

    _onMarkdownClick(event) {
        const target = event.target;
        const targetElement = target instanceof Element
            ? target
            : (target instanceof Node ? target.parentElement : null);
        if (targetElement === null) return;
        const entityLink = targetElement.closest('a[href^="entity:"]');
        if (entityLink !== null) {
            const href = entityLink.getAttribute('href');
            if (typeof href === 'string' && href.startsWith('entity:') && href.length > 'entity:'.length) {
                event.preventDefault();
                this._closeMentionPreviewNow();
                this._emitEntityOpen(href.slice('entity:'.length));
                return;
            }
        }
        const chip = targetElement.closest('.mention-chip');
        if (chip === null) return;
        const entityId = chip.getAttribute('data-entity-id');
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        event.preventDefault();
        this._closeMentionPreviewNow();
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
            this._entitySearchPurpose = 'mention';
            this._mentionRequestId = this._dispatchEntitySearchRequested(payload);
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

    _dispatchEntitySearchRequested(payload) {
        const ev = this.dispatch(this._entitySearch.op.events.REQUESTED, payload, { source: 'local' });
        if (!ev || typeof ev.id !== 'string') {
            throw new Error('CRMNoteCardView: entity search REQUESTED did not return event id');
        }
        return ev.id;
    }

    _renderEntityPickerPopover(kind, loading, queryMinLen, emptyKey, rows, onPick, noRowsKey) {
        if (loading === true) {
            return html`
                <div class="mention-popover mention-popover--entity-list">
                    <div class="mention-empty">${this.t('note_edit.mention_searching')}</div>
                </div>
            `;
        }
        if (typeof queryMinLen === 'number' && queryMinLen > 0) {
            const q = kind === 'voice'
                ? (typeof this._voiceSearchQuery === 'string' ? this._voiceSearchQuery.trim() : '')
                : (typeof this._contextSearchQuery === 'string' ? this._contextSearchQuery.trim() : '');
            if (q.length < queryMinLen) {
                return html`
                    <div class="mention-popover mention-popover--entity-list">
                        <div class="mention-empty">${this.t(emptyKey)}</div>
                    </div>
                `;
            }
        }
        if (!Array.isArray(rows) || rows.length === 0) {
            const key = typeof noRowsKey === 'string' && noRowsKey.length > 0
                ? noRowsKey
                : 'note_edit.entity_search_none';
            return html`
                <div class="mention-popover mention-popover--entity-list">
                    <div class="mention-empty">${this.t(key)}</div>
                </div>
            `;
        }
        return html`
            <div class="mention-popover mention-popover--entity-list">
                ${rows.map(
                    (item) => html`
                        <button type="button" class="mention-row" @click=${() => onPick(item)}>
                            <span class="mention-row-lead">
                                <platform-icon name=${this._pickerIconNameForItem(item)} size="16"></platform-icon>
                            </span>
                            <span class="mention-row-body">
                                <span class="mention-name">${typeof item.name === 'string' ? item.name : ''}</span>
                                <span class="mention-type">${this._pickerTypeLabelForItem(item)}</span>
                            </span>
                        </button>
                    `,
                )}
            </div>
        `;
    }

    _runVoiceEntitySearch() {
        const q = typeof this._voiceSearchQuery === 'string' ? this._voiceSearchQuery.trim() : '';
        if (q.length === 0) {
            this._voiceSearchResults = [];
            this._voiceSearchLoading = false;
            this._voiceSearchFilteredNoMatch = false;
            return;
        }
        this._voiceSearchLoading = true;
        this._voiceSearchFilteredNoMatch = false;
        const payload = { q, limit: 22 };
        const ns = this._currentNamespaceForSearch();
        if (typeof ns === 'string' && ns.length > 0) {
            payload.namespace = ns;
        }
        this._entitySearchPurpose = 'voice';
        this._voiceSearchRequestId = this._dispatchEntitySearchRequested(payload);
    }

    _runContextEntitySearch() {
        const q = typeof this._contextSearchQuery === 'string' ? this._contextSearchQuery.trim() : '';
        if (q.length === 0) {
            this._contextSearchResults = [];
            this._contextSearchLoading = false;
            this._contextSearchFilteredNoMatch = false;
            return;
        }
        this._contextSearchLoading = true;
        this._contextSearchFilteredNoMatch = false;
        const payload = { q, limit: 22 };
        const ns = this._currentNamespaceForSearch();
        if (typeof ns === 'string' && ns.length > 0) {
            payload.namespace = ns;
        }
        this._entitySearchPurpose = 'context';
        this._contextSearchRequestId = this._dispatchEntitySearchRequested(payload);
    }

    _onVoiceSearchInput(e) {
        const value = e.target instanceof HTMLInputElement ? e.target.value : '';
        this._voiceSearchQuery = value;
        this._voiceSearchOpen = true;
        if (this._voiceSearchDeb !== null) {
            clearTimeout(this._voiceSearchDeb);
            this._voiceSearchDeb = null;
        }
        this._voiceSearchDeb = window.setTimeout(() => {
            this._voiceSearchDeb = null;
            this._runVoiceEntitySearch();
        }, 220);
    }

    _onContextSearchInput(e) {
        const value = e.target instanceof HTMLInputElement ? e.target.value : '';
        this._contextSearchQuery = value;
        this._contextSearchOpen = true;
        if (this._contextSearchDeb !== null) {
            clearTimeout(this._contextSearchDeb);
            this._contextSearchDeb = null;
        }
        this._contextSearchDeb = window.setTimeout(() => {
            this._contextSearchDeb = null;
            this._runContextEntitySearch();
        }, 220);
    }

    _onPickVoiceSearchItem(item) {
        if (!item || typeof item.entity_id !== 'string' || item.entity_id.length === 0) {
            return;
        }
        this._editVoiceEntityId = item.entity_id;
        const label = typeof item.name === 'string' && item.name.length > 0 ? item.name : item.entity_id;
        this._voiceSearchQuery = label;
        this._voiceSearchOpen = false;
    }

    _onPickContextSearchItem(item) {
        if (!item || typeof item.entity_id !== 'string' || item.entity_id.length === 0) {
            return;
        }
        this._editContextEntityId = item.entity_id;
        const label = typeof item.name === 'string' && item.name.length > 0 ? item.name : item.entity_id;
        this._contextSearchQuery = label;
        this._contextSearchOpen = false;
    }

    _subtypeEnumConfig(subtypes) {
        if (!Array.isArray(subtypes)) {
            throw new Error('CRMNoteCardView._subtypeEnumConfig: subtypes must be an array');
        }
        const values = [{ value: '', label: this.t('note_edit.subtype_plain') }];
        for (let i = 0; i < subtypes.length; i += 1) {
            const tid = subtypes[i];
            if (typeof tid !== 'string') {
                throw new Error('CRMNoteCardView._subtypeEnumConfig: subtype id must be a string');
            }
            values.push({ value: tid, label: this._subtypeNameByTypeId(tid) });
        }
        return { values };
    }

    _onEditSubtypeChange(e) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new Error('CRMNoteCardView._onEditSubtypeChange: expected string detail.value');
        }
        this._editSubtype = v;
    }

    _onEditDateChange(e) {
        const v = e.detail.value;
        if (v === null || v === undefined) {
            this._editDate = '';
            return;
        }
        if (typeof v !== 'string') {
            throw new Error('CRMNoteCardView._onEditDateChange: expected string or null detail.value');
        }
        this._editDate = v;
    }

    _onClearVoicePick() {
        this._editVoiceEntityId = '';
        this._voiceSearchQuery = '';
        this._voiceSearchResults = [];
        this._voiceSearchOpen = false;
        this._voiceSearchFilteredNoMatch = false;
    }

    _onClearContextPick() {
        this._editContextEntityId = '';
        this._contextSearchQuery = '';
        this._contextSearchResults = [];
        this._contextSearchOpen = false;
        this._contextSearchFilteredNoMatch = false;
    }

    _renderEditNoteSemantics() {
        const subtypes = this._noteFamilySubtypeSelectableIdsSorted();
        const showVoice = this._showNoteVoiceAuthorUi() === true && this._voiceTargetTypeIdSet().size > 0;
        const showContext = this._contextAnchorTypeIdSet().size > 0;
        if (subtypes.length === 0 && !showVoice && !showContext) {
            return html``;
        }
        return html`
            <div class="note-semantics-edit semantics-toolbar">
                ${subtypes.length > 0
                    ? html`
                        <div class="semantics-field">
                            <platform-field
                                type="enum"
                                mode="edit"
                                .label=${this.t('note_edit.field_note_kind')}
                                .config=${this._subtypeEnumConfig(subtypes)}
                                .value=${this._editSubtype}
                                @change=${this._onEditSubtypeChange}
                            ></platform-field>
                        </div>
                    `
                    : ''}
                ${showVoice
                    ? html`
                        <div class="semantics-field picker-field field-pill semantics-picker-pill" data-mode="edit">
                            <div class="field-pill-head">
                                <span class="field-pill-label">${this.t('note_edit.field_voice_author')}</span>
                            </div>
                            <div class="field-pill-control">
                                <div class="field-pill-control-main">
                                    <div class="entity-search-wrap">
                                        <input
                                            type="text"
                                            class="field-pill-input"
                                            data-canon="search-as-you-type"
                                            placeholder=${this.t('note_edit.voice_author_search')}
                                            .value=${this._voiceSearchQuery}
                                            @focus=${() => { this._voiceSearchOpen = true; this._runVoiceEntitySearch(); }}
                                            @input=${this._onVoiceSearchInput}
                                        />
                                        ${this._editVoiceEntityId.length > 0
                                            ? html`
                                                <button type="button" class="semantics-clear" @click=${this._onClearVoicePick}>
                                                    <platform-icon name="close" size="12"></platform-icon>
                                                </button>
                                            `
                                            : ''}
                                        ${this._voiceSearchOpen
                                            ? this._renderEntityPickerPopover(
                                                'voice',
                                                this._voiceSearchLoading,
                                                0,
                                                'note_edit.entity_search_min',
                                                this._voiceSearchResults,
                                                (it) => this._onPickVoiceSearchItem(it),
                                                this._voiceSearchFilteredNoMatch === true
                                                    ? 'note_edit.entity_search_none_matching_voice'
                                                    : 'note_edit.entity_search_none',
                                            )
                                            : ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `
                    : ''}
                ${showContext
                    ? html`
                        <div class="semantics-field picker-field field-pill semantics-picker-pill" data-mode="edit">
                            <div class="field-pill-head">
                                <span class="field-pill-label">${this.t('note_edit.field_context_anchor')}</span>
                            </div>
                            <div class="field-pill-control">
                                <div class="field-pill-control-main">
                                    <div class="entity-search-wrap">
                                        <input
                                            type="text"
                                            class="field-pill-input"
                                            data-canon="search-as-you-type"
                                            placeholder=${this._contextAnchorSearchPlaceholder()}
                                            .value=${this._contextSearchQuery}
                                            @focus=${() => {
                                                this._contextSearchOpen = true;
                                                this._runContextEntitySearch();
                                            }}
                                            @input=${this._onContextSearchInput}
                                        />
                                        ${this._editContextEntityId.length > 0
                                            ? html`
                                                <button type="button" class="semantics-clear" @click=${this._onClearContextPick}>
                                                    <platform-icon name="close" size="12"></platform-icon>
                                                </button>
                                            `
                                            : ''}
                                        ${this._contextSearchOpen
                                            ? this._renderEntityPickerPopover(
                                                'context',
                                                this._contextSearchLoading,
                                                0,
                                                'note_edit.entity_search_min',
                                                this._contextSearchResults,
                                                (it) => this._onPickContextSearchItem(it),
                                                this._contextSearchFilteredNoMatch === true
                                                    ? 'note_edit.entity_search_none_matching_anchor'
                                                    : 'note_edit.entity_search_none',
                                            )
                                            : ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `
                    : ''}
            </div>
        `;
    }

    _renderViewNoteMetaRibbon() {
        const chipsData = this._voiceContextChips();
        const subtypeId =
            this.note !== null && typeof this.note.entity_subtype === 'string' && this.note.entity_subtype.length > 0
                ? this.note.entity_subtype
                : '';
        const subtypeReadable = subtypeId.length > 0 ? this._subtypeNameByTypeId(subtypeId) : '';
        const hasChips =
            chipsData.voice !== null
            || chipsData.context !== null
            || subtypeReadable.length > 0;
        if (!hasChips) {
            return html``;
        }
        return html`
            <div class="view-meta-ribbon">
                ${subtypeReadable.length > 0
                    ? html`<span class="meta-pill kind-pill">${subtypeReadable}</span>`
                    : ''}
                ${chipsData.voice !== null
                    ? html`
                        <button
                            type="button"
                            class="meta-pill"
                            @click=${() => this._emitEntityOpen(chipsData.voice.entity_id)}
                            title=${this.t('note_edit.field_voice_author')}
                        >
                            <platform-icon
                                name=${this._pickerIconNameForItem(chipsData.voice)}
                                size="12"
                            ></platform-icon>
                            ${chipsData.voice.label}
                        </button>
                    `
                    : ''}
                ${chipsData.context !== null
                    ? html`
                        <button
                            type="button"
                            class="meta-pill context-pill"
                            @click=${() => this._emitEntityOpen(chipsData.context.entity_id)}
                            title=${this.t('note_edit.field_context_anchor')}
                        >
                            <platform-icon
                                name=${this._pickerIconNameForItem(chipsData.context)}
                                size="12"
                            ></platform-icon>
                            ${chipsData.context.label}
                        </button>
                    `
                    : ''}
            </div>
        `;
    }

    _renderMentionPopover() {
        if (this._mentionLoading) {
            return html`
                <div class="mention-popover mention-popover--entity-list">
                    <div class="mention-empty">${this.t('note_edit.mention_searching')}</div>
                </div>
            `;
        }
        if (this._mentionQuery.length === 0) {
            return html`
                <div class="mention-popover mention-popover--entity-list">
                    <div class="mention-empty">${this.t('note_edit.mention_min_query')}</div>
                </div>
            `;
        }
        if (this._mentionResults.length === 0) {
            return html`
                <div class="mention-popover mention-popover--entity-list">
                    <div class="mention-empty">${this.t('note_edit.mention_no_results')}</div>
                </div>
            `;
        }
        return html`
            <div class="mention-popover mention-popover--entity-list">
                ${this._mentionResults.map((item) => html`
                    <button
                        type="button"
                        class="mention-row"
                        @click=${() => this._onMentionPick(item)}
                    >
                        <span class="mention-row-lead">
                            <platform-icon name=${this._pickerIconNameForItem(item)} size="16"></platform-icon>
                        </span>
                        <span class="mention-row-body">
                            <span class="mention-name">${typeof item.name === 'string' ? item.name : ''}</span>
                            <span class="mention-type">${this._pickerTypeLabelForItem(item)}</span>
                        </span>
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

    _onUploadClick(mode = 'edit') {
        if (mode !== 'view' && mode !== 'edit') {
            throw new Error('CRMNoteCardView._onUploadClick: mode must be "view" or "edit"');
        }
        this._uploadTargetMode = mode;
        const input = this.renderRoot.querySelector('[data-role="note-attachment-input"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('CRMNoteCardView._onUploadClick: attachment input not found');
        }
        input.click();
    }

    _onUploadFiles(e) {
        const fileList = e.target.files;
        if (fileList === null) return;
        const files = Array.from(fileList);
        const targetMode = this._uploadTargetMode;
        if (targetMode === 'view') {
            if (!this.note || typeof this.note.entity_id !== 'string' || this.note.entity_id.length === 0) {
                throw new Error('CRMNoteCardView._onUploadFiles: note.entity_id required for view upload');
            }
            for (const file of files) {
                this._attachmentUpload.run({
                    entity_id: this.note.entity_id,
                    file,
                });
            }
        } else {
            for (const file of files) {
                this._fileUpload.run({ file });
            }
        }
        this._uploadTargetMode = 'edit';
        e.target.value = '';
    }
    _onRemoveAttachment(fileId) {
        this._editAttachmentIds = this._editAttachmentIds.filter((id) => id !== fileId);
    }

    _viewAttachments() {
        const attachments = Array.isArray(this.card?.attachments) ? this.card.attachments : [];
        return attachments.map((item) => {
            const attachmentId = typeof item.document_id === 'string' ? item.document_id : '';
            const filename = typeof item.filename === 'string' && item.filename.length > 0
                ? item.filename
                : attachmentId;
            const metadata = item && typeof item.metadata === 'object' && item.metadata !== null
                ? item.metadata
                : {};
            const contentType = typeof metadata.content_type === 'string' ? metadata.content_type : '';
            const sizeBytes = typeof item.size_bytes === 'number'
                ? item.size_bytes
                : (typeof metadata.size_bytes === 'number'
                    ? metadata.size_bytes
                    : (typeof metadata.file_size === 'number' ? metadata.file_size : 0));
            const downloadUrl = typeof item.download_url === 'string' && item.download_url.length > 0
                ? item.download_url
                : (typeof item.url === 'string' ? item.url : '');
            return {
                id: attachmentId,
                filename,
                sizeBytes,
                status: typeof item.status === 'string' ? item.status : '',
                downloadUrl,
                contentType,
                canDelete: attachmentId.length > 0,
            };
        });
    }

    _editAttachments() {
        const viewMap = new Map();
        for (const item of this._viewAttachments()) {
            if (item.id.length > 0) {
                viewMap.set(item.id, item);
            }
        }
        return this._editAttachmentIds.map((fileId) => {
            const localMeta = this._editAttachmentsMeta[fileId];
            const cardItem = viewMap.get(fileId);
            const filename = localMeta && typeof localMeta.name === 'string' && localMeta.name.length > 0
                ? localMeta.name
                : (cardItem ? cardItem.filename : fileId);
            const localSize = localMeta && typeof localMeta.size === 'number'
                ? localMeta.size
                : (localMeta && typeof localMeta.file_size === 'number' ? localMeta.file_size : 0);
            const sizeBytes = localSize > 0
                ? localSize
                : (cardItem ? cardItem.sizeBytes : 0);
            const contentType = localMeta && typeof localMeta.content_type === 'string'
                ? localMeta.content_type
                : (cardItem ? cardItem.contentType : '');
            const downloadUrl = localMeta && typeof localMeta.download_url === 'string'
                ? localMeta.download_url
                : (cardItem ? cardItem.downloadUrl : '');
            return {
                id: fileId,
                filename,
                sizeBytes,
                status: cardItem ? cardItem.status : '',
                downloadUrl,
                contentType,
                canDelete: true,
            };
        });
    }

    _attachmentItemsForMode(mode) {
        if (mode === 'edit') {
            return this._editAttachments();
        }
        return this._viewAttachments();
    }

    _openAttachmentsPopover(mode) {
        this._cancelAttachmentsPopoverClose();
        this._attachmentsPopoverMode = mode;
        this._attachmentsPopoverOpen = true;
    }

    _closeAttachmentsPopover() {
        this._cancelAttachmentsPopoverClose();
        this._attachmentsPopoverOpen = false;
        this._attachmentsPopoverMode = '';
    }

    _scheduleAttachmentsPopoverClose() {
        this._cancelAttachmentsPopoverClose();
        this._attachmentsPopoverCloseTimer = setTimeout(() => {
            this._attachmentsPopoverCloseTimer = null;
            this._closeAttachmentsPopover();
        }, 140);
    }

    _cancelAttachmentsPopoverClose() {
        if (this._attachmentsPopoverCloseTimer === null) {
            return;
        }
        clearTimeout(this._attachmentsPopoverCloseTimer);
        this._attachmentsPopoverCloseTimer = null;
    }

    _onAttachmentsFocusOut(event) {
        const next = event.relatedTarget;
        if (next instanceof Node && event.currentTarget.contains(next)) {
            return;
        }
        this._closeAttachmentsPopover();
    }

    _onDeleteViewAttachment(attachmentId) {
        if (!this.note || typeof this.note.entity_id !== 'string' || this.note.entity_id.length === 0) {
            throw new Error('CRMNoteCardView._onDeleteViewAttachment: note entity_id required');
        }
        if (typeof attachmentId !== 'string' || attachmentId.length === 0) {
            throw new Error('CRMNoteCardView._onDeleteViewAttachment: attachmentId required');
        }
        this._attachmentDelete.run({
            entity_id: this.note.entity_id,
            attachment_id: attachmentId,
        });
    }

    _onDeleteEditAttachment(attachmentId) {
        if (typeof attachmentId !== 'string' || attachmentId.length === 0) {
            throw new Error('CRMNoteCardView._onDeleteEditAttachment: attachmentId required');
        }
        this._editAttachmentIds = this._editAttachmentIds.filter((id) => id !== attachmentId);
    }

    _renderAttachmentsHeaderButton(mode) {
        const count = this._attachmentItemsForMode(mode).length;
        const editMode = mode === 'edit';
        const isOpen = this._attachmentsPopoverOpen && this._attachmentsPopoverMode === mode;
        const buttonTitle = editMode ? this.t('note_edit.attachment_add') : this.t('note_view.action_attachments');
        const handleClick = () => {
            if (isOpen) {
                this._closeAttachmentsPopover();
            }
            this._onUploadClick(mode);
        };
        return html`
            <div
                class="attachments-menu"
                @mouseenter=${() => this._openAttachmentsPopover(mode)}
                @mouseleave=${() => this._scheduleAttachmentsPopoverClose()}
                @focusin=${() => this._openAttachmentsPopover(mode)}
                @focusout=${this._onAttachmentsFocusOut}
            >
                <button
                    type="button"
                    class="round-btn"
                    title=${buttonTitle}
                    aria-haspopup="menu"
                    aria-expanded=${String(isOpen)}
                    @click=${handleClick}
                >
                    <platform-icon name="paperclip" size="20"></platform-icon>
                    <span class="attachments-badge">${count}</span>
                </button>
                ${isOpen ? this._renderAttachmentsPopover(mode) : nothing}
            </div>
        `;
    }

    _renderAttachmentRow(item, mode) {
        if (mode !== 'view' && mode !== 'edit') {
            throw new Error('CRMNoteCardView._renderAttachmentRow: mode must be "view" or "edit"');
        }
        const iconName = _resolveAttachmentIconName(item.filename, item.contentType);
        const metaParts = [];
        const bytes = formatBytes(item.sizeBytes);
        if (bytes.length > 0) metaParts.push(bytes);
        if (item.status.length > 0) metaParts.push(item.status);
        const metaText = metaParts.join(' · ');
        return html`
            <div class="attachments-popover-row">
                <platform-icon name=${iconName} size="16"></platform-icon>
                <div class="attachments-popover-info">
                    <p class="attachments-popover-name">${item.filename}</p>
                    <p class="attachments-popover-meta">${metaText}</p>
                </div>
                <div class="attachments-popover-actions">
                    ${item.downloadUrl.length > 0 ? html`
                        <a
                            class="attachment-action-btn"
                            href=${item.downloadUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            download=${item.filename}
                            title=${this.t('note_view.download')}
                        >
                            <platform-icon name="import" size="14"></platform-icon>
                        </a>
                    ` : nothing}
                    ${item.canDelete ? html`
                        <button
                            type="button"
                            class="attachment-action-btn"
                            title=${mode === 'edit'
                                ? this.t('note_edit.attachment_remove')
                                : this.t('note_view.attachment_remove')}
                            @click=${() => mode === 'edit'
                                ? this._onDeleteEditAttachment(item.id)
                                : this._onDeleteViewAttachment(item.id)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </button>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _renderAttachmentsPopover(mode) {
        const items = this._attachmentItemsForMode(mode);
        return html`
            <div
                class="attachments-popover"
                role="menu"
                @mouseenter=${() => this._cancelAttachmentsPopoverClose()}
                @mouseleave=${() => this._scheduleAttachmentsPopoverClose()}
            >
                ${items.length === 0
                    ? html`<div class="attachments-popover-empty">${this.t('note_view.attachments_empty_popover')}</div>`
                    : items.map((item) => this._renderAttachmentRow(item, mode))}
            </div>
        `;
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
        if (!hasGetUserMediaApi() || typeof MediaRecorder === 'undefined') {
            this.toast('toast.note.voice_unavailable_recorder', { type: 'warning' });
            return;
        }
        const stream = await getUserMediaCompat({ audio: true });
        const mimeType = pickVoiceMimeType();
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
        const hasAttachments = this._editAttachmentIds.length > 0;
        if (this._editName.trim().length === 0 && this._editDescription.trim().length === 0 && !hasAttachments) {
            return this.t('note_edit.err_name_or_description_required');
        }
        return null;
    }

    _attachNoteSemanticsToBody(body, isCreate) {
        const st = typeof this._editSubtype === 'string' ? this._editSubtype.trim() : '';
        if (!isCreate) {
            body.entity_subtype = st.length > 0 ? st : null;
        } else if (st.length > 0) {
            body.entity_subtype = st;
        }
        const allowVoice = this._showNoteVoiceAuthorUi() === true && this._voiceTargetTypeIdSet().size > 0;
        if (allowVoice) {
            const v = typeof this._editVoiceEntityId === 'string' ? this._editVoiceEntityId.trim() : '';
            body.voice_entity_id = v.length > 0 ? v : null;
        }
        if (this._contextAnchorTypeIdSet().size > 0) {
            const c = typeof this._editContextEntityId === 'string' ? this._editContextEntityId.trim() : '';
            body.context_entity_id = c.length > 0 ? c : null;
        }
    }

    _buildEditBody(isCreate) {
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
        this._attachNoteSemanticsToBody(body, Boolean(isCreate));
        return body;
    }

    _onSaveEdit() {
        const error = this._validateEdit();
        if (typeof error === 'string') {
            this._formError = error;
            return;
        }
        this._formError = '';
        if (this.note === null) {
            const namespace = this.defaultNamespace;
            if (typeof namespace !== 'string' || namespace.length === 0) {
                this._formError = this.t('note_edit.err_namespace_required');
                return;
            }
            const body = this._buildEditBody(true);
            this._entities.create({
                entity_type: NOTE_ROOT_ENTITY_TYPE_ID,
                namespace,
                ...body,
            });
            return;
        }
        const body = this._buildEditBody(false);
        this._updateOp.run({
            id: this.note.entity_id,
            body,
        });
    }

    _onCancelEdit() {
        this.emit('cancel');
    }

    _noteNeighborRows() {
        if (this.card === null || this.note === null || typeof this.note.entity_id !== 'string') {
            return [];
        }
        const edges = extractNeighborEdges(this.card, this.note.entity_id);
        return edges.map(({ rel, otherId, otherEntity, isOutgoing }) => ({
            relationshipId: rel.relationship_id,
            otherId,
            otherEntity,
            relationshipTypeLabel: this._relationshipTypeLabel(rel.relationship_type),
            directionText: isOutgoing
                ? `${this.t('note_view.this_note')} →`
                : `${this.t('note_view.this_note')} ←`,
            weight: typeof rel.weight === 'number' && Number.isFinite(rel.weight) ? rel.weight : null,
            confidencePercent: relationshipConfidencePercent(rel),
            scorePercent: searchScorePercent(otherEntity),
        }));
    }

    _renderNoteGraphInlineSection() {
        if (!this.note || typeof this.note !== 'object') {
            return nothing;
        }
        const noteIdRaw = this.note.entity_id;
        const noteId = typeof noteIdRaw === 'string' ? noteIdRaw.trim() : '';
        if (noteId.length === 0) {
            return nothing;
        }
        const entityNs =
            typeof this.note.namespace === 'string' && this.note.namespace.length > 0
                ? this.note.namespace
                : '';
        const vm = this._graphView.value.viewMode;
        return html`
            <div class="note-graph-preview-host">
                <crm-mini-graph
                    fill-container
                    embed-chrome
                    show-view-mode-toggle
                    .entityId=${noteId}
                    namespace=${entityNs}
                    .viewMode=${vm}
                    @view-mode-request=${(e) => {
                        const d = e.detail;
                        const next = d && typeof d.viewMode === 'string' ? d.viewMode.trim() : '';
                        if (next !== 'mindmap' && next !== '3d') {
                            throw new Error('NoteCardView: view-mode-request requires viewMode mindmap|3d');
                        }
                        this._graphView.setViewMode({ viewMode: next });
                    }}
                    @entity-open=${(e) =>
                        this._emitEntityOpen(e.detail.entityId, e.detail.entity_type)}
                ></crm-mini-graph>
            </div>
        `;
    }

    _renderNeighborsSection() {
        const rows = this._noteNeighborRows();
        return html`
            <section class="neighbors-section">
                <h3 class="card-title" style="margin-bottom: var(--space-4);">${this.t('entity_card.related_objects_section')}</h3>
                <crm-related-neighbor-rows
                    .rows=${rows}
                    .entityTypeRows=${this._entityTypeItems()}
                    .emptyText=${this.t('note_view.no_neighbors')}
                    .showRemove=${false}
                    @entity-open=${(e) =>
                        this._emitEntityOpen(e.detail.entityId, e.detail.entity_type)}
                ></crm-related-neighbor-rows>
            </section>
        `;
    }

    _renderMobileHeaderPanel(summaryText, summaryTime, summaryEntities) {
        if (this.mobileHeaderPanel === 'summary') {
            return this._renderSummaryCard(summaryText, summaryTime, summaryEntities);
        }
        if (this.mobileHeaderPanel === 'neighbors') {
            return this._renderNeighborsSection();
        }
        return nothing;
    }

    _noteTasks() {
        const cardRelated = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        return cardRelated.filter((e) => e && entityKind(e) === 'task');
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

    _renderEditHeaderActionsContent() {
        const isCreate = this.note === null;
        const busy = isCreate ? this._entities.createInFlight : this._updateOp.busy;
        const uploading = this._fileUpload.busy;
        return html`
            ${this._renderAttachmentsHeaderButton('edit')}
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
        `;
    }

    /**
     * @param {boolean} includeDesktopGraphToggle — на мобилке в шапке страницы граф отдельно; в карточке на узком экране не дублировать.
     */
    _renderViewHeaderActionsContent(includeDesktopGraphToggle) {
        const panelGraph = this.mobileHeaderPanel === 'graph';
        return html`
            ${this._renderAttachmentsHeaderButton('view')}
            ${includeDesktopGraphToggle
                ? html`
                    <button
                        type="button"
                        class=${`round-btn desktop-graph-toggle ${panelGraph ? 'active' : ''}`}
                        title=${this.t('note_view.graph_inline_title')}
                        aria-expanded=${String(panelGraph)}
                        @click=${() => this.emit('overlay-panel-toggle', { panel: 'graph' })}
                    >
                        <platform-icon name="git-branch" size="20"></platform-icon>
                    </button>
                `
                : nothing}
            <button
                type="button"
                class="round-btn danger"
                title=${this.t('note_view.action_delete')}
                @click=${() => this.emit('delete-note')}
            >
                <platform-icon name="trash" size="20"></platform-icon>
            </button>
            ${includeDesktopGraphToggle
                ? html`
                    <button
                        type="button"
                        class="pill-btn"
                        title=${this.t('note_view.action_edit')}
                        @click=${() => this.emit('edit-note')}
                    >
                        <platform-icon name="edit" size="16"></platform-icon>
                        ${this.t('note_view.action_edit')}
                    </button>
                `
                : html`
                    <button
                        type="button"
                        class="round-btn"
                        title=${this.t('note_view.action_edit')}
                        aria-label=${this.t('note_view.action_edit')}
                        @click=${() => this.emit('edit-note')}
                    >
                        <platform-icon name="edit" size="20"></platform-icon>
                    </button>
                `}
        `;
    }

    _teardownMobileToolbarPortRendering() {
        if (this._lastMobileToolbarPortHost !== null) {
            render(nothing, this._lastMobileToolbarPortHost);
            this._lastMobileToolbarPortHost = null;
        }
    }

    _syncMobileToolbarPort() {
        const host = this.mobileHeaderActionsHost;
        const mobile = typeof window !== 'undefined'
            && window.matchMedia('(max-width: 767px)').matches;
        const shouldPort = Boolean(host && mobile);
        if (this.mobileToolbarPorted !== shouldPort) {
            this.mobileToolbarPorted = shouldPort;
        }

        if (this._lastMobileToolbarPortHost !== null && this._lastMobileToolbarPortHost !== host) {
            render(nothing, this._lastMobileToolbarPortHost);
            this._lastMobileToolbarPortHost = null;
        }

        if (!host) {
            return;
        }

        if (!mobile) {
            render(nothing, host);
            if (this._lastMobileToolbarPortHost === host) {
                this._lastMobileToolbarPortHost = null;
            }
            return;
        }

        let tpl;
        if (this.mode === 'edit') {
            tpl = html`
                <div class="header-actions">
                    ${this._renderEditHeaderActionsContent()}
                </div>
            `;
        } else {
            if (!this.note || typeof this.note !== 'object') {
                render(nothing, host);
                if (this._lastMobileToolbarPortHost === host) {
                    this._lastMobileToolbarPortHost = null;
                }
                return;
            }
            tpl = html`
                <div class="header-actions">
                    ${this._renderViewHeaderActionsContent(false)}
                </div>
            `;
        }
        render(tpl, host);
        this._lastMobileToolbarPortHost = host;
    }

    _renderMarkdownFormatStatusBanner() {
        if (!this.markdownFormatting) {
            return nothing;
        }
        const mfProg = this.markdownFormatProgress;
        const mfHasNums = mfProg !== null && typeof mfProg === 'object'
            && typeof mfProg.done === 'number'
            && typeof mfProg.total === 'number'
            && mfProg.total > 0;
        const mfPct = mfHasNums ? Math.min(100, Math.round((mfProg.done / mfProg.total) * 100)) : 0;
        return html`
            <div class="note-markdown-format-banner" role="status" aria-live="polite">
                <glass-spinner size="sm"></glass-spinner>
                <div class="note-markdown-format-banner-main">
                    <div class="note-markdown-format-banner-head">
                        <span>${
                            mfHasNums
                                ? this.t('note_view.markdown_format_progress', { done: mfProg.done, total: mfProg.total })
                                : this.t('note_view.markdown_formatting')
                        }</span>
                        ${mfHasNums ? html`<span class="note-markdown-format-banner-pct">${mfPct}%</span>` : ''}
                    </div>
                    ${mfHasNums
                        ? html`<div class="note-markdown-format-banner-line"><span style="width:${mfPct}%;"></span></div>`
                        : html`<div class="note-markdown-format-banner-line indeterminate"><span></span></div>`}
                </div>
            </div>
        `;
    }

    updated(changed) {
        super.updated(changed);
        this._syncMobileToolbarPort();
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
        const panelGraph = this.mobileHeaderPanel === 'graph';
        const mobileFloatingPanel =
            this.mobileHeaderPanel === 'summary' || this.mobileHeaderPanel === 'neighbors';

        return html`
            <div class="layout">
                <section class="main">
                    <header class="header">
                        <div class="title-block">
                            <h1 class="title">${title}</h1>
                            ${dateText
                                ? html`<span class="note-date">${this.t('note_view.date_prefix', { date: dateText })}</span>`
                                : ''}
                            ${this._renderViewNoteMetaRibbon()}
                        </div>
                        <div class="header-actions">
                            ${this._renderViewHeaderActionsContent(true)}
                        </div>
                        ${mobileFloatingPanel
                            ? html`
                                <div class="mobile-header-panels">
                                    ${this._renderMobileHeaderPanel(summaryText, summaryTime, summaryEntities)}
                                </div>
                            `
                            : nothing}
                    </header>
                    ${panelGraph ? nothing : this._renderMarkdownFormatStatusBanner()}
                    <div class="note-primary-pane">
                        ${panelGraph
                            ? this._renderNoteGraphInlineSection()
                            : html`
                                <div class=${`note-text-scroll${this.markdownFormatting ? ' markdown-format-status-active' : ''}`}>
                                    <div class="note-text-body-wrap">
                                        ${description.length > 0
                                            ? html`
                                                <article
                                                    class="markdown"
                                                    @click=${this._onMarkdownClick}
                                                    @mousemove=${this._onMarkdownMouseMove}
                                                    @mouseleave=${this._onMarkdownMouseLeave}
                                                >
                                                    ${unsafeHTML(renderMarkdownToHtml(description))}
                                                </article>
                                                <button
                                                    type="button"
                                                    class="note-markdown-format-btn"
                                                    title=${this.t('note_view.markdown_format_action')}
                                                    ?disabled=${this.markdownFormatting}
                                                    @click=${() => this.emit('format-markdown-request')}
                                                >
                                                    <svg
                                                        xmlns="http://www.w3.org/2000/svg"
                                                        width="20"
                                                        height="20"
                                                        viewBox="0 0 24 24"
                                                        fill="none"
                                                        stroke="currentColor"
                                                        stroke-width="2"
                                                        stroke-linecap="round"
                                                        stroke-linejoin="round"
                                                        aria-hidden="true"
                                                    >
                                                        <path d="M4 6h16" />
                                                        <path d="M7 12h10" />
                                                        <path d="M10 18h4" />
                                                        <path d="M4 18h3" />
                                                    </svg>
                                                </button>
                                            `
                                            : html`<p class="empty-text">${this.t('note_view.no_description')}</p>`}
                                    </div>
                                </div>
                            `}
                    </div>
                </section>

                <aside class="sidebar">
                    ${this._renderSummaryCard(summaryText, summaryTime, summaryEntities)}
                    ${this._renderTasksCard(tasks)}
                    ${this._renderNeighborsSection()}
                </aside>
            </div>
            ${this._renderAttachmentInput()}
            <crm-entity-hover-preview
                ?preview-open=${this._mentionPreviewOpen}
                .entityId=${this._mentionHoverEntityId}
                .anchorRect=${this._mentionHoverAnchorRect}
                @preview-enter=${this._onPreviewEnter}
                @preview-leave=${this._onPreviewLeave}
                @open=${this._onPreviewOpen}
            ></crm-entity-hover-preview>
        `;
    }

    _renderSummaryCard(summaryText, summaryTime, summaryEntities) {
        const stage = typeof this.aiProgressStage === 'string' ? this.aiProgressStage : '';
        const status = typeof this.aiProgressStatus === 'string' ? this.aiProgressStatus : '';
        const progressPctRaw = typeof this.aiProgressPct === 'number' ? this.aiProgressPct : 0;
        const progressPct = Math.max(0, Math.min(100, progressPctRaw));
        const stageOrStatus = stage.length > 0
            ? stage
            : (status.length > 0 ? status : this.t('note_view.summary_progress_stage_fallback'));
        const relatedForLookup = this.card !== null && Array.isArray(this.card.related_entities)
            ? this.card.related_entities
            : [];
        const summaryLookup = buildSummaryEntityLookupFromRelated(relatedForLookup);
        const typeRows = this._entityTypeItems();
        const analysisErr = this._noteAnalysisErrorMessage();
        return html`
            <section class="card summary-card">
                <div class="card-header">
                    <h3 class="card-title">
                        <platform-icon name="ai" size="20" colored></platform-icon>
                        ${this.t('note_view.summary_title')}
                    </h3>
                    <button
                        type="button"
                        class="round-btn"
                        title=${this.t('note_view.summary_refresh')}
                        ?disabled=${this.aiAnalyzing}
                        @click=${() => this.emit('refresh-summary')}
                        style="width: 36px; height: 36px;"
                    >
                        <platform-icon
                            class=${`summary-refresh-icon ${this.aiAnalyzing ? 'spinning' : ''}`}
                            name="refresh"
                            size="16"
                        ></platform-icon>
                    </button>
                </div>
                ${summaryTime
                    ? html`<p class="summary-meta">${this.t('note_view.summary_generated_at', { time: summaryTime })}</p>`
                    : ''}
                ${this.aiAnalyzing
                    ? html`<p class="summary-status analyzing">${this.aiStatusText}</p>`
                    : summaryText.length > 0
                    ? html`
                        <p class="summary-text">${summaryText}</p>
                        ${analysisErr.length > 0
                            ? html`
                                <div class="summary-analysis-error">
                                    <p class="summary-analysis-error-title">${this.t('note_view.summary_analysis_failed_title')}</p>
                                    <p class="summary-analysis-error-detail">${analysisErr}</p>
                                    <p class="summary-analysis-error-hint">${this.t('note_view.summary_analysis_retry_hint')}</p>
                                </div>`
                            : nothing}`
                    : analysisErr.length > 0
                    ? html`
                        <div class="summary-analysis-error">
                            <p class="summary-analysis-error-title">${this.t('note_view.summary_analysis_failed_title')}</p>
                            <p class="summary-analysis-error-detail">${analysisErr}</p>
                            <p class="summary-analysis-error-hint">${this.t('note_view.summary_analysis_retry_hint')}</p>
                        </div>`
                    : html`<p class="summary-text" style="color: var(--crm-note-text-muted);">${this.t('note_view.no_summary')}</p>`}
                ${this.aiAnalyzing
                    ? html`
                        <div class="summary-progress">
                            <div class="summary-progress-head">
                                <span class="summary-progress-stage">${stageOrStatus}</span>
                                <span class="summary-progress-pct">${progressPct}%</span>
                            </div>
                            <div class="summary-progress-line">
                                <span style="width:${progressPct}%;"></span>
                            </div>
                        </div>
                    `
                    : nothing}
                ${summaryEntities.length > 0 ? html`
                    <div class="summary-tags">
                        ${summaryEntities.map((tag, idx) => {
                            const tone = ['violet', 'yellow', 'orange'][idx % 3];
                            const resolved = resolveSummaryChipEntity(tag, summaryLookup);
                            const chipIcon = resolved
                                ? entityDisplayIconName(resolved, typeRows)
                                : summaryChipUnresolvedIconName();
                            if (resolved) {
                                return html`
                                    <button
                                        type="button"
                                        class="summary-tag summary-tag--clickable tag-${tone}"
                                        @click=${(e) => {
                                            e.stopPropagation();
                                            this._emitEntityOpen(resolved.entity_id);
                                        }}
                                    >
                                        <platform-icon name=${chipIcon} size="12"></platform-icon>${tag}
                                    </button>
                                `;
                            }
                            return html`
                                <span class="summary-tag tag-${tone}">
                                    <platform-icon name=${chipIcon} size="12"></platform-icon>${tag}
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
                        data-canon="composer"
                        placeholder=${this.t('note_view.task_add_placeholder')}
                        @keydown=${this._onTaskAddKeydown}
                    />
                </label>
            </section>
        `;
    }

    _renderAttachmentInput() {
        return html`
            <input
                id=${this._attachmentInputId}
                type="file"
                multiple
                class="visually-hidden-file-input"
                data-role="note-attachment-input"
                @change=${this._onUploadFiles}
            />
        `;
    }

    _renderEdit() {
        return html`
            <div class="layout edit-mode">
                <section class="main">
                    <header class="header">
                        <div class="title-block">
                            <input
                                class="title-input"
                                type="text"
                                data-canon="inline-edit"
                                placeholder=${this.t('note_edit.placeholder_title')}
                                .value=${this._editName}
                                @input=${this._onNameInput}
                            />
                        </div>
                        <div class="header-actions">
                            ${this._renderEditHeaderActionsContent()}
                        </div>
                    </header>

                    ${this._renderEditNoteSemantics()}

                    <div class="field-pill field-pill--textarea note-description-pill">
                        <div class="field-pill-head">
                            <span class="field-pill-label">${this.t('note_edit.field_description')}</span>
                        </div>
                        <div class="description-edit-wrap">
                            <textarea
                                class="field-pill-textarea description-edit"
                                data-canon="mention"
                                placeholder=${this.t('note_edit.placeholder_description')}
                                .value=${this._editDescription}
                                @input=${this._onDescriptionInput}
                                @keydown=${this._onDescriptionKeydown}
                            ></textarea>
                            <button
                                type="button"
                                class="voice-btn ${this._voiceState}"
                                title=${this._voiceState === 'recording'
                                    ? this.t('note_edit.voice_dictation_stop')
                                    : this.t('note_edit.voice_dictation_start')}
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
                        <platform-field
                            type="date"
                            mode="edit"
                            .label=${this.t('note_edit.field_date')}
                            .value=${this._editDate.length > 0 ? this._editDate : null}
                            @change=${this._onEditDateChange}
                        ></platform-field>
                        <div class="field-pill tags-field-pill" data-mode="edit">
                            <div class="field-pill-head">
                                <span class="field-pill-label">${this.t('note_edit.field_tags')}</span>
                            </div>
                            <div class="field-pill-control">
                                <div class="field-pill-control-main">
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
                                            data-canon="composer"
                                            placeholder=${this.t('note_edit.placeholder_tag')}
                                            .value=${this._tagDraft}
                                            @input=${this._onTagDraftInput}
                                            @keydown=${this._onTagDraftKeydown}
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    ${this._renderAttachmentInput()}

                    ${this._formError.length > 0
                        ? html`<div class="form-error">${this._formError}</div>`
                        : ''}
                </section>
            </div>
        `;
    }
}

customElements.define('crm-note-card-view', CRMNoteCardView);
