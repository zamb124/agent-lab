/**
 * DailyNotesPage — главный экран CRM («ежедневник»).
 *
 * Источники данных (только helpers, никаких прямых импортов resource-объектов):
 *   - useCursorList('crm/notes_list')   — лента заметок за выбранный диапазон дат
 *   - useOp('crm/note_latest_range')    — стартовый диапазон по последним 50 заметкам
 *   - useOp('crm/note_search')          — текстовый/семантический поиск по заметкам
 *   - useOp('crm/daily_summary')        — AI-сводка одного дня
 *   - useOp('crm/period_summary')       — AI-сводка диапазона
 *   - useOp('crm/task_daily_summary_start') / 'crm/task_period_summary_start' — пересчёт сводки
 *   - <platform-voice-dictation> — STT-only WS (VAD final → создание заметки)
 *   - useOp('crm/note_analyze_start')   — старт AI-анализа заметки
 *   - useOp('crm/entity_cards_bulk')    — batch-загрузка карточек связанных entity
 *
 * В реальном времени: push `crm/note/updated` → merge в `crm/notes_list`;
 * страница обновляет локальный card/summary/tasks map, без HTTP list reload.
 * `crm/daily_summary/updated` / `crm/period_summary/updated` → summary ops
 * extraReducer; `crm/task/updated` → tasks resource.
 * `crm/period_summary/updated`, `crm/task/updated` (прогресс `note_analyze` в slice
 * `crm/tasks` без поллинга). Backend публикует через `core/events/dispatcher.py`.
 * Изменение namespace приходит как `ui/namespace/changed` (CoreEvents.UI_NAMESPACE_CHANGED) —
 * page перезапрашивает ленту и сводку.
 *
 * Открытие заметки: страница навигирует на роут `note` (`/crm/notes/:itemId`),
 * редактирование живёт на `note-page`, отдельной модалки нет. Создание новой
 * Создание новой заметки передаёт `itemId='new'`/`itemId='draft-<ts>'`.
 * Диктовка с тулбара пишет текст в `crm/note_compose.description`, затем
 * тот же `itemId='new'`; `note-page` / `note-card-view` забирает seed.
 *
 * Открытие связанной entity (chip / related): пока entity-page не реализован,
 * страница показывает информационный toast и не пытается открыть несуществующую
 * модалку.
 */

import { html, css } from 'lit';
import { CRMNamespacePage } from './crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { CRM_NOTE_UPDATED, CRM_TASK_UPDATED } from '../events/types.js';
import { stripOuterMarkdownCodeFence } from '@platform/lib/utils/strip-outer-markdown-fence.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-voice-dictation.js';
import '@platform/lib/components/layout/page-header.js';
import {
    buildSummaryEntityLookupFromNoteBuckets,
    entityDisplayIconName,
    normalizeSummaryEntityLabelKey,
    resolveSummaryChipEntity,
    summaryChipUnresolvedIconName,
} from '../_helpers/related-entity-presenter.js';
import { openCrmLaraAssistant } from '../_helpers/open-crm-lara-assistant.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    CursorListController,
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type {
    CrmDailyNotesUiController,
    CrmNoteComposeController,
} from '../events/crm.types.js';

const ENTITY_TYPES_RESOURCE = 'crm/entity_types';
const SUMMARY_ENTITY_TOKEN_RE = /\[(@?[^\]]+)\]\(entity:([^)]+)\)/gi;

function _formatIsoDate(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _today() {
    return _formatIsoDate(new Date());
}

function _tomorrow() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return _formatIsoDate(d);
}

function _formatHHMM(date: Date): string {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

const SUMMARY_CHIP_TONES = ['blue', 'cyan', 'orange', 'rose'];
const ENTITY_TAG_TONES = ['primary', 'secondary', 'accent'];
const NOTE_SUBTYPE_ICONS = {
    call: 'phone-call',
    meeting: 'calendar',
    email: 'mail',
    task: 'tasks',
    note: 'doc-detail',
};
const SEARCH_MODES = ['text', 'semantic', 'hybrid'];
const ACTIVE_ANALYZE_TASK_STATUSES = new Set(['pending', 'running']);

export class CRMDailyNotesPage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        _query: { state: true },
        _searchMode: { state: true },
        _isMobile: { state: true },
        _summaryOpen: { state: true },
        _noteEntitiesByNoteId: { state: true },
        _analyzeTasksByNoteId: { state: true },
        _searchResults: { state: true },
        _searchLoading: { state: true },
        _creatingNote: { state: true },
        _mobileHeaderSearch: { state: true },
    };
    declare _query: string;
    declare _searchMode: string;
    declare _isMobile: boolean;
    declare _summaryOpen: boolean;
    declare _noteEntitiesByNoteId: Record<string, Record<string, any>[]>;
    declare _analyzeTasksByNoteId: Record<string, Record<string, any>>;
    declare _searchResults: Record<string, any>[];
    declare _searchLoading: boolean;
    declare _creatingNote: boolean;
    declare _mobileHeaderSearch: boolean;

    static override styles: CSSResultGroup = [
        CRMNamespacePage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                box-sizing: border-box;
                width: 100%;
                max-width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 324px;
                gap: 24px;
                width: 100%;
                max-width: 100%;
                min-width: 0;
                flex: 1;
                min-height: 0;
                overflow: hidden;
                --crm-list-card-bg: color-mix(in srgb, var(--text-primary) 5%, transparent);
                --crm-list-card-bg-hover: color-mix(in srgb, var(--text-primary) 8%, transparent);
            }

            .main-column {
                display: flex;
                flex-direction: column;
                min-width: 0;
                min-height: 0;
                overflow: hidden;
                position: relative;
            }

            .section-label {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
            }

            .title-settings {
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }

            .top-row {
                display: grid;
                grid-template-columns: auto minmax(260px, 1fr) auto;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                margin-left: auto;
                gap: var(--space-2);
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid transparent;
                background: var(--crm-surface-muted);
                min-height: 44px;
                width: 100%;
            }

            .search-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-base);
                outline: none;
            }

            .date-input {
                min-width: 180px;
                --platform-date-picker-labeled-bg: var(--crm-surface-muted);
                --platform-date-picker-labeled-border: transparent;
                --platform-date-picker-labeled-height: 44px;
                --platform-date-picker-labeled-padding: 0 var(--space-3);
            }

            .cta-btn {
                min-height: 44px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--platform-btn-primary-text);
                font-size: var(--text-lg);
                font-weight: 500;
                padding: 0 var(--space-6);
                cursor: pointer;
                transition: background var(--duration-fast);
                white-space: nowrap;
            }
            .cta-btn:hover { background: var(--crm-daily-notes-cta-hover); }
            .cta-btn:disabled { opacity: 0.7; cursor: not-allowed; }
            .cta-btn-content {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }

            .toolbar-voice {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
            }

            .cards-scroll {
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
                min-width: 0;
                padding-right: var(--space-2);
            }

            .cards-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 24px;
                align-content: start;
                width: 100%;
                max-width: 100%;
                min-width: 0;
            }

            .note-card {
                border: none;
                background: var(--crm-list-card-bg);
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                min-height: 222px;
                min-width: 0;
                box-sizing: border-box;
                overflow: hidden;
                cursor: pointer;
                transition: background var(--duration-fast);
            }
            .note-card:hover {
                background: var(--crm-list-card-bg-hover);
            }

            .note-tags {
                display: flex;
                flex-wrap: nowrap;
                gap: 12px;
                min-height: 24px;
                overflow-x: auto;
                overflow-y: hidden;
                scrollbar-width: none;
            }
            .note-tags::-webkit-scrollbar { display: none; }

            .note-type-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border-radius: 8px;
                background: var(--crm-surface-elevated);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

            .note-tag {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 12px;
                min-height: 24px;
                font-size: 12px;
                line-height: 15px;
                border-radius: 14px;
                color: rgba(34, 34, 34, 0.95);
                font-weight: 400;
                border: none;
                cursor: pointer;
                transition: filter var(--duration-fast);
                white-space: nowrap;
                flex: 0 0 auto;
            }
            .note-tag.primary { background: #99A6F9; }
            .note-tag.secondary { background: #FAD17A; }
            .note-tag.accent { background: #FF885C; }

            .note-title {
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                overflow-wrap: anywhere;
            }
            .note-text {
                margin: 0;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                overflow-wrap: anywhere;
            }
            .note-preview-error {
                margin: 0;
                display: flex;
                flex-direction: column;
                gap: 6px;
                overflow-wrap: anywhere;
            }
            .note-preview-error-title {
                font-size: 16px;
                line-height: 20px;
                font-weight: 700;
                color: var(--error);
            }
            .note-preview-error-detail {
                margin: 0;
                font-size: 14px;
                line-height: 18px;
                font-weight: 600;
                color: var(--error);
                opacity: 0.92;
            }
            .note-analysis-progress {
                margin-top: 2px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .note-analysis-progress-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .note-analysis-progress-stage {
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .note-analysis-progress-pct {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
            }
            .note-analysis-progress-line {
                width: 100%;
                height: 5px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .note-analysis-progress-line > span {
                display: block;
                height: 100%;
                background: var(--accent);
                transition: width var(--duration-fast);
            }

            .note-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-top: auto;
            }

            .note-footer-right {
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }
            .published-at { color: var(--text-tertiary); font-size: 12px; }

            .analyze-btn {
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                border-radius: 16px;
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }
            .analyze-btn.has-draft {
                border-color: var(--accent-secondary);
                background: rgba(255, 136, 92, 0.18);
                color: var(--accent-secondary);
            }
            .analyze-btn.has-applied {
                border-color: rgba(34, 197, 94, 0.5);
                background: rgba(34, 197, 94, 0.12);
                color: #16a34a;
            }
            .analyze-btn.needs-ai {
                border-color: rgba(139, 92, 246, 0.5);
                background: rgba(139, 92, 246, 0.14);
                color: #8b5cf6;
                animation: ai-pulse 2s ease-in-out infinite;
            }
            .analyze-btn.analysis-failed {
                border-color: var(--error-border);
                background: var(--error-bg);
                color: var(--error);
                animation: none;
            }
            .analyze-btn.analyzing { animation: analyze-busy 1.2s ease-in-out infinite; cursor: wait; }
            .analyze-btn:disabled { opacity: 0.72; cursor: not-allowed; }
            @keyframes analyze-busy { 0%,100% { opacity: 1; } 50% { opacity: 0.55; } }
            @keyframes ai-pulse {
                0%,100% { box-shadow: 0 0 6px rgba(139,92,246,0.2); }
                50% { box-shadow: 0 0 12px rgba(139,92,246,0.4); }
            }

            .summary-panel {
                background: var(--crm-summary-bg);
                border-radius: 16px;
                border: none;
                padding: 20px;
                display: flex;
                flex-direction: column;
                min-height: 0;
                max-height: 100%;
                overflow: hidden;
            }
            .summary-header {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .summary-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin: 0;
                min-width: 0;
            }
            .summary-title-text {
                flex: 1 1 auto;
                min-width: 0;
                font-size: 20px;
                font-weight: 700;
                line-height: 26px;
                background: var(--crm-summary-title-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .summary-title-icon {
                width: 20px;
                height: 20px;
                flex-shrink: 0;
                background: var(--crm-summary-title-gradient);
                -webkit-mask: var(--crm-summary-spark-mask) center / contain no-repeat;
                mask: var(--crm-summary-spark-mask) center / contain no-repeat;
            }
            .summary-refresh-btn {
                width: 24px;
                height: 24px;
                border-radius: var(--radius-full);
                border: none;
                background: transparent;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                padding: 0;
                flex-shrink: 0;
            }
            .summary-refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; }
            .summary-refresh-icon {
                width: 18px;
                height: 18px;
                display: block;
                background: var(--crm-summary-title-gradient);
                -webkit-mask: var(--crm-summary-refresh-mask) center / contain no-repeat;
                mask: var(--crm-summary-refresh-mask) center / contain no-repeat;
            }
            .summary-refresh-icon.spinning {
                animation: summary-spin 0.9s linear infinite;
                transform-origin: center;
            }
            @keyframes summary-spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

            .summary-meta {
                color: var(--crm-summary-meta);
                font-size: 12px;
                line-height: 15px;
                margin-bottom: var(--space-4);
            }
            .summary-text {
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                margin: 0;
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
            }
            .summary-inline-entity {
                display: inline;
                border: 0;
                background: transparent;
                color: var(--crm-selected-text);
                font: inherit;
                padding: 0;
                cursor: pointer;
                text-decoration: none;
            }
            .summary-inline-entity:hover {
                text-decoration: underline;
                text-underline-offset: 0.12em;
            }
            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
                max-height: 176px;
                overflow-y: auto;
                overflow-x: hidden;
                padding-right: var(--space-1);
                flex: 0 0 auto;
                overscroll-behavior: contain;
            }
            .summary-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                padding: 7px 14px;
                background: var(--crm-summary-chip-blue-bg);
                color: var(--text-primary);
                border: none;
                font-weight: var(--font-medium);
                max-width: 100%;
            }
            .summary-chip.cyan { background: var(--crm-summary-chip-cyan-bg); }
            .summary-chip.orange { background: var(--crm-summary-chip-orange-bg); }
            .summary-chip.rose { background: var(--crm-summary-chip-rose-bg); }
            .summary-chip--clickable { cursor: pointer; font-family: inherit; }
            .summary-chip--clickable:hover { filter: brightness(1.12); }

            .empty {
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-xl);
                min-height: 200px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }

            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                max-width: 36rem;
                line-height: 1.45;
            }

            .summary-overlay { display: none; }

            .daily-notes-mobile-header-wrap {
                display: none;
            }

            .mobile-header-icon-btn {
                width: 32px;
                height: 32px;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                cursor: pointer;
                box-shadow: var(--glass-shadow-subtle);
                padding: 0;
            }
            .mobile-header-icon-btn:hover {
                background: var(--glass-solid-medium);
            }
            .mobile-header-icon-btn:disabled {
                opacity: 0.55;
                cursor: not-allowed;
            }
            .mobile-header-icon-btn.active {
                border-color: var(--accent);
                color: var(--accent);
            }
            .mobile-header-icon-btn.mobile-header-summary-btn {
                border: none;
                background: var(--crm-summary-title-gradient);
                color: var(--platform-btn-primary-text);
                box-shadow: 0 2px 8px rgba(153, 166, 249, 0.35);
            }
            .mobile-header-icon-btn.mobile-header-summary-btn:hover {
                filter: brightness(1.06);
            }
            .mobile-header-icon-btn.mobile-header-summary-btn platform-icon {
                color: var(--platform-btn-primary-text);
            }
            .mobile-toolbar-search-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }
            .mobile-header-search-box {
                flex: 1;
                min-width: 0;
                min-height: 40px;
            }
            .mobile-header-search-box .search-input {
                min-width: 0;
                flex: 1;
            }
            .crm-mobile-date-picker-anchor {
                position: fixed;
                top: max(var(--space-2), var(--platform-safe-top, 0px));
                right: 100px;
                width: 1px;
                height: 1px;
                min-width: 0 !important;
                padding: 0;
                margin: 0;
                overflow: hidden;
                clip-path: inset(50%);
                border: 0;
                pointer-events: none;
                opacity: 0;
                z-index: -1;
            }

            @media (max-width: 1279px) {
                .layout { grid-template-columns: 1fr; }
                .summary-panel { min-height: 240px; }
                .top-row { grid-template-columns: 1fr; }
            }

            @media (max-width: 767px) {
                :host { padding: 0; }
                .daily-notes-mobile-header-wrap { display: block; }
                .section-label, .top-row { display: none; }
                .layout {
                    padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
                    padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                    padding-bottom: max(var(--space-2), var(--platform-safe-bottom));
                    box-sizing: border-box;
                }
                .cards-scroll { padding-right: var(--space-1); }
                .cards-grid { grid-template-columns: 1fr; gap: var(--space-3); }
                .empty { padding: var(--space-4); }
                .summary-panel { display: none; }
                .summary-overlay {
                    position: fixed; inset: 0;
                    background: rgba(15, 23, 42, 0.55);
                    backdrop-filter: blur(6px);
                    z-index: 1300;
                    display: flex;
                    align-items: flex-end;
                    justify-content: center;
                    padding: var(--space-2);
                }
                .summary-overlay .summary-panel {
                    display: flex;
                    width: 100%;
                    max-height: 70vh;
                    background: var(--crm-surface);
                    border: 1px solid var(--crm-stroke);
                    border-radius: var(--radius-xl);
                }
                .summary-tags {
                    max-height: 156px;
                }
                .summary-chip {
                    padding: 6px 12px;
                }
            }

            .search-mode-toggle {
                display: flex;
                gap: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                flex-shrink: 0;
            }
            .search-mode-btn {
                padding: 4px 10px;
                font-size: var(--text-xs);
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .search-mode-btn:not(:last-child) { border-right: 1px solid var(--glass-border-subtle); }
            .search-mode-btn.active {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                font-weight: 500;
            }

            .card-score {
                display: flex;
                align-items: center;
                gap: 6px;
                height: 16px;
                position: relative;
                background: var(--glass-bg-subtle);
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 6px;
                cursor: help;
            }
            .score-bar {
                position: absolute; left: 0; top: 0; height: 100%;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                opacity: 0.25;
            }
            .score-label { position: relative; z-index: 1; font-size: 10px; font-weight: 600; padding-left: 6px; }
            .match-type-badge {
                position: relative; z-index: 1;
                font-size: 9px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin-left: auto;
                padding-right: 6px;
            }
        `,
    ];

    private _dailyNotesUi: CrmDailyNotesUiController;
    private _noteCompose: CrmNoteComposeController;
    private _notes: CursorListController;
    private _latestRange: OpController;
    private _search: OpController;
    private _dailySummary: OpController;
    private _periodSummary: OpController;
    private _dailySummaryStart: OpController;
    private _periodSummaryStart: OpController;
    private _analyze: OpController;
    private _cardsBulk: OpController;
    private _tasks: ResourceController;
    private _entityTypes: ResourceController;
    private _routeKeySel: SelectController<string | undefined>;
    private _mql: MediaQueryList | null;
    private _mqlListener: ((e: MediaQueryListEvent) => void) | null;
    private _debounceTimer: ReturnType<typeof setTimeout> | null;
    private _latestRangeBootstrapped: boolean;
    private _mediaRecorder: MediaRecorder | null = null;
    private _lastCardsResult: Record<string, any> | null = null;

    constructor() {
        super();
        this._dailyNotesUi = this.useSlice('crm/daily_notes_ui') as CrmDailyNotesUiController;
        this._noteCompose = this.useSlice('crm/note_compose') as CrmNoteComposeController;
        this._query = '';
        this._searchMode = 'hybrid';
        this._summaryOpen = false;
        this._noteEntitiesByNoteId = {};
        this._analyzeTasksByNoteId = {};
        this._searchResults = [];
        this._searchLoading = false;
        this._creatingNote = false;
        this._mobileHeaderSearch = false;
        this._isMobile = typeof window !== 'undefined' && window.innerWidth <= 767;

        this._notes = this.useCursorList('crm/notes_list');
        this._latestRange = this.useOp('crm/note_latest_range');
        this._search = this.useOp('crm/note_search');
        this._dailySummary = this.useOp('crm/daily_summary');
        this._periodSummary = this.useOp('crm/period_summary');
        this._dailySummaryStart = this.useOp('crm/task_daily_summary_start');
        this._periodSummaryStart = this.useOp('crm/task_period_summary_start');
        this._analyze = this.useOp('crm/note_analyze_start');
        this._cardsBulk = this.useOp('crm/entity_cards_bulk');
        this._tasks = this.useResource('crm/tasks');
        this._entityTypes = this.useResource(ENTITY_TYPES_RESOURCE, { autoload: false });

        this._routeKeySel = this.select((s: Record<string, any>) => s.router.routeKey);

        this._mql = null;
        this._mqlListener = null;
        this._debounceTimer = null;
        this._latestRangeBootstrapped = false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._mqlListener = (e: MediaQueryListEvent) => {
                this._isMobile = e.matches;
                if (!e.matches) {
                    this._mobileHeaderSearch = false;
                }
            };
            this._mql.addEventListener('change', this._mqlListener);
            this._isMobile = this._mql.matches;
        }

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._latestRangeBootstrapped = false;
            this._loadEntityTypesCatalog();
            this._bootstrapLatestNotesRange();
        });
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            if (this._routeKeySel.value !== 'notes') {
                return;
            }
            this._reloadNotes();
        });
        this.useEvent(CRM_NOTE_UPDATED, (event: PlatformEvent) => this._onNoteWsUpdate(event.payload as Record<string, any> | null));

        this.useEvent('crm/note_search/succeeded', (event: PlatformEvent) => {
            const causationId = event.meta && typeof event.meta.causation_id === 'string' ? event.meta.causation_id : null;
            if (causationId === null || causationId.length === 0) {
                throw new Error('crm/note_search/succeeded: causation_id required');
            }
            const expectedId = this._search.lastRequestId;
            if (typeof expectedId !== 'string' || expectedId.length === 0) {
                throw new Error('crm/note_search/succeeded: slice lastRequestId missing');
            }
            if (causationId !== expectedId) return;
            const result = event.payload && (event.payload as Record<string, any>).result;
            const items = result && Array.isArray(result.items) ? result.items : [];
            this._searchResults = items;
            this._searchLoading = false;
            this._loadCardsForVisibleNotes(items);
        });
        this.useEvent('crm/note_search/failed', (event: PlatformEvent) => {
            const causationId = event.meta && typeof event.meta.causation_id === 'string' ? event.meta.causation_id : null;
            if (causationId === null || causationId.length === 0) {
                throw new Error('crm/note_search/failed: causation_id required');
            }
            const expectedId = this._search.lastRequestId;
            if (typeof expectedId !== 'string' || expectedId.length === 0) {
                throw new Error('crm/note_search/failed: slice lastRequestId missing');
            }
            if (causationId !== expectedId) return;
            this._searchLoading = false;
        });

        this.useEvent(this._tasks.resource.events.LIST_LOADED, () => this._rebuildAnalyzeTaskMap());
        this.useEvent(CRM_TASK_UPDATED, () => this._rebuildAnalyzeTaskMap());

        this.useEvent('crm/notes_list/loaded', (event: PlatformEvent) => {
            const items = event.payload && Array.isArray((event.payload as Record<string, any>).items) ? (event.payload as Record<string, any>).items : [];
            if (this._query.trim().length === 0) {
                this._loadCardsForVisibleNotes(items);
            }
        });
        this.useEvent('crm/note_latest_range/succeeded', (event: PlatformEvent) => this._onLatestRangeLoaded(event));

        this._loadEntityTypesCatalog();
        this._bootstrapLatestNotesRange();
        this._loadAnalyzeTasks();
    }

    override disconnectedCallback(): void {
        if (this._mql && this._mqlListener) {
            this._mql.removeEventListener('change', this._mqlListener);
        }
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
        if (this._mediaRecorder && this._mediaRecorder.state === 'recording') {
            this._mediaRecorder.stop();
        }
        this._creatingNote = false;
        super.disconnectedCallback();
    }

    _currentNamespace() {
        return this._crmNamespaceSel.value;
    }

    _noteSubtypeFromLocationSearch() {
        if (typeof window === 'undefined') {
            return '';
        }
        const sp = new URLSearchParams(window.location.search);
        const et = sp.get('entity_type');
        const es = sp.get('entity_subtype');
        if (es === null || es.length === 0) {
            return '';
        }
        if (et !== null && et.length > 0 && et !== 'note') {
            return '';
        }
        return es;
    }

    _range(): { from: string; to: string } {
        const v = this._dailyNotesUi.value;
        if (!v) {
            throw new Error('CRMDailyNotesPage: daily_notes_ui slice value missing');
        }
        return v.range;
    }

    _isPeriod() { return this._range().from !== this._range().to; }

    _bootstrapLatestNotesRange() {
        const payload: Record<string, unknown> = { entity_type: 'note', limit: 50 };
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) payload.namespace = ns;
        const sub = this._noteSubtypeFromLocationSearch();
        if (sub.length > 0) {
            payload.entity_subtype = sub;
        }
        this._latestRange.run(payload);
    }

    _onLatestRangeLoaded(event: PlatformEvent): void {
        if (this._latestRangeBootstrapped) return;
        const causationId = event.meta && typeof event.meta.causation_id === 'string' ? event.meta.causation_id : null;
        if (causationId === null || causationId.length === 0) {
            throw new Error('crm/note_latest_range/succeeded: causation_id required');
        }
        const expectedId = this._latestRange.lastRequestId;
        if (typeof expectedId !== 'string' || expectedId.length === 0) {
            throw new Error('crm/note_latest_range/succeeded: slice lastRequestId missing');
        }
        if (causationId !== expectedId) return;
        const result = event.payload && (event.payload as Record<string, any>).result;
        const items = result && Array.isArray(result.items) ? result.items : [];
        const noteDates = items
            .map((item: Record<string, any>) => (item && typeof item.note_date === 'string' ? item.note_date : ''))
            .filter((value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value));
        const from = noteDates.length > 0
            ? noteDates.reduce((earliest: string, value: string) => (value < earliest ? value : earliest), noteDates[0]!)
            : _today();
        this._latestRangeBootstrapped = true;
        this._dailyNotesUi.setRange({ from, to: _tomorrow() });
        this._reloadNotes();
        this._reloadSummary();
    }

    _reloadNotes() {
        const filters: Record<string, unknown> = {
            date_from: this._range().from,
            date_to: this._range().to,
        };
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) filters.namespace = ns;
        const sub = this._noteSubtypeFromLocationSearch();
        if (sub.length > 0) {
            filters.entity_subtype = sub;
        }
        this._noteEntitiesByNoteId = {};
        this._notes.load(filters);
        this._loadAnalyzeTasks();
    }

    _loadAnalyzeTasks() {
        const payload: Record<string, unknown> = {
            limit: 200,
            offset: 0,
            task_type: 'note_analyze',
        };
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) {
            payload.namespace = ns;
        }
        this._tasks.load(payload);
    }

    _rebuildAnalyzeTaskMap(): void {
        const byNoteId: Record<string, Record<string, any>> = {};
        const items = this._tasks.items as Record<string, any>[];
        for (const task of items) {
            if (!ACTIVE_ANALYZE_TASK_STATUSES.has(task.status)) {
                continue;
            }
            const data = task && typeof task.data === 'object' && task.data !== null ? task.data : null;
            const noteId = data && typeof data.note_id === 'string' ? data.note_id : '';
            if (noteId.length === 0) {
                continue;
            }
            byNoteId[noteId] = task;
        }
        this._analyzeTasksByNoteId = byNoteId;
    }

    _reloadSummary(options?: { force_rebuild?: boolean }): void {
        const force_rebuild = options && options.force_rebuild === true;
        const ns = this._currentNamespace();
        const payload = this._isPeriod()
            ? { date_from: this._range().from, date_to: this._range().to, force_rebuild } as Record<string, unknown>
            : { date: this._range().from, force_rebuild } as Record<string, unknown>;
        if (typeof ns === 'string' && ns.length > 0) {
            payload.namespace = ns;
        }
        if (this._isPeriod()) {
            this._periodSummary.run(payload);
        } else {
            this._dailySummary.run(payload);
        }
    }

    _onNoteWsUpdate(payload: Record<string, any> | null): void {
        if (!payload || typeof payload !== 'object') return;
        if (typeof payload.note_id !== 'string' || payload.note_id.trim().length === 0) return;
        const ns = this._currentNamespace();
        const payloadNs = payload.namespace === null || payload.namespace === undefined
            ? null
            : (typeof payload.namespace === 'string' && payload.namespace.length > 0 ? payload.namespace : null);
        if (ns !== payloadNs) return;
        if (typeof payload.note_date !== 'string') return;
        const mf = payload.markdown_format;
        if (mf && (mf.phase === 'partial' || mf.phase === 'started')) {
            return;
        }
        if (payload.note_date < this._range().from || payload.note_date > this._range().to) return;
        // Лента notes_list мержится в extraReducer; summary — crm/daily_summary/updated;
        // analyze map — crm/task/updated / LIST_LOADED. Здесь только invalidate card cache.
        const next = { ...this._noteEntitiesByNoteId };
        delete next[payload.note_id.trim()];
        this._noteEntitiesByNoteId = next;
        this.requestUpdate();
    }

    _onSearchInput(event: Event) {
        this._query = (event.target as HTMLInputElement).value;
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        const trimmed = this._query.trim();
        if (trimmed.length === 0) {
            this._searchResults = [];
            this._searchLoading = false;
            return;
        }
        const minLen = this._isMobile ? 2 : 1;
        if (trimmed.length < minLen) {
            this._searchResults = [];
            this._searchLoading = false;
            return;
        }
        this._debounceTimer = setTimeout(() => this._runSearch(), 300);
    }

    _runSearch() {
        const q = this._query.trim();
        if (q.length === 0) return;
        this._searchLoading = true;
        const ns = this._currentNamespace();
        const payload: Record<string, unknown> = { query: q, entity_type: 'note', search_mode: this._searchMode, limit: 50 };
        if (typeof ns === 'string' && ns.length > 0) payload.namespace = ns;
        this._search.run(payload);
    }

    _onSearchModeChange(mode: string): void {
        this._searchMode = mode;
        if (this._query.trim().length > 0) this._runSearch();
    }

    _onDateRangeChange(event: CustomEvent) {
        const detail = event.detail;
        if (!detail || detail.selection !== 'range') {
            throw new Error('platform-date-picker must use selection=range');
        }
        const v = detail.value;
        if (!v || typeof v !== 'object'
            || typeof v.start !== 'string' || typeof v.end !== 'string'
            || !/^\d{4}-\d{2}-\d{2}$/.test(v.start)
            || !/^\d{4}-\d{2}-\d{2}$/.test(v.end)) {
            throw new Error('platform-date-picker returned invalid range value');
        }
        this._dailyNotesUi.setRange({ from: v.start, to: v.end });
        this._reloadNotes();
        this._reloadSummary();
    }

    _onCreateNote() {
        if (this._creatingNote) {
            return;
        }
        this._creatingNote = true;
        this.navigate('note', { itemId: 'new' });
    }

    /**
     * @param {CustomEvent<{ text: string, provider: string }>} event
     */
    _onVoiceTranscribed(event: CustomEvent) {
        const detail = event && event.detail;
        if (!detail || typeof detail.text !== 'string' || detail.text.trim().length === 0) {
            this.toast('toast.note.voice_empty', { type: 'warning' });
            return;
        }
        this._noteCompose.setDescription({ description: detail.text.trim() });
        this.navigate('note', { itemId: 'new' });
    }

    _onAnalyzeNote(note: Record<string, any>): void {
        if (!note || typeof note.entity_id !== 'string') {
            throw new Error('Note entity_id required for analysis');
        }
        if (this._hasAnalysisDraft(note) || this._hasAnalysisApplied(note)) {
            this.openModal('crm.ai_analysis', { noteId: note.entity_id });
            return;
        }
        if (this._isAnalyzingNote(note)) {
            this.openModal('crm.ai_analysis', { noteId: note.entity_id });
            return;
        }
        this._analyze.run({ note_id: note.entity_id });
        this.openModal('crm.ai_analysis', { noteId: note.entity_id });
    }

    _onRefreshSummary() {
        this._reloadSummary({ force_rebuild: true });
    }

    _loadCardsForVisibleNotes(notes: readonly Record<string, any>[]): void {
        const ids = notes
            .map((n: Record<string, any>) => n && typeof n.entity_id === 'string' ? n.entity_id.trim() : null)
            .filter((id): id is string => typeof id === 'string' && id.length > 0)
            .filter((id) => !Object.prototype.hasOwnProperty.call(this._noteEntitiesByNoteId, id));
        if (ids.length === 0) return;
        this._cardsBulk.run({ entity_ids: ids });
    }

    _onCardsBulkLoaded(payload: Record<string, any> | null): void {
        if (!payload || typeof payload !== 'object') return;
        const next = { ...this._noteEntitiesByNoteId };
        for (const [entityId, card] of Object.entries(payload)) {
            if (card && Array.isArray(card.related_entities)) {
                next[entityId] = card.related_entities;
            } else {
                next[entityId] = [];
            }
        }
        this._noteEntitiesByNoteId = next;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const cardsResult = this._cardsBulk.lastResult;
        if (cardsResult && cardsResult !== this._lastCardsResult) {
            this._lastCardsResult = cardsResult;
            this._onCardsBulkLoaded(cardsResult as Record<string, any> | null);
        }
    }

    _hasAnalysisDraft(note: Record<string, any>) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return false;
        const draft = attrs.ai_analysis_draft;
        return typeof draft === 'object' && draft !== null && typeof draft.draft_version === 'number';
    }

    _hasAnalysisApplied(note: Record<string, any>) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return false;
        return typeof attrs.ai_analysis_applied_at === 'string'
            && attrs.ai_analysis_applied_at.length > 0
            && !this._hasAnalysisDraft(note);
    }

    _noteNeedsAi(note: Record<string, any>) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return true;
        if (attrs.ai_analysis_applied_at) return false;
        if (attrs.ai_analysis_draft && typeof attrs.ai_analysis_draft === 'object') return false;
        return true;
    }

    _isAnalyzingNote(note: Record<string, any>) {
        if (!note || typeof note.entity_id !== 'string') {
            return false;
        }
        if (this._analyze.busy
            && this._analyze.lastResult
            && (this._analyze.lastResult as Record<string, any>).note_id === note.entity_id) {
            return true;
        }
        return this._analyzeTaskForNote(note.entity_id) !== null;
    }

    _analyzeTaskForNote(noteId: unknown): Record<string, any> | null {
        if (typeof noteId !== 'string' || noteId.length === 0) {
            return null;
        }
        const task = this._analyzeTasksByNoteId[noteId];
        return task === undefined ? null : task;
    }

    _filteredNotes(): readonly Record<string, any>[] {
        const q = this._query.trim();
        if (q.length === 0) {
            return this._notes.items as readonly Record<string, any>[];
        }
        if (this._isMobile && q.length < 2) {
            return this._notes.items as readonly Record<string, any>[];
        }
        return this._searchResults;
    }

    _summaryResult(): Record<string, any> | null {
        return (this._isPeriod() ? this._periodSummary.lastResult : this._dailySummary.lastResult) as Record<string, any> | null;
    }

    _summaryBusy() {
        if (this._isPeriod()) {
            return this._periodSummary.busy || this._periodSummaryStart.busy;
        }
        return this._dailySummary.busy || this._dailySummaryStart.busy;
    }

    _summaryEntities() {
        const r = this._summaryResult();
        if (!r || !Array.isArray(r.entities)) return [];
        return (r.entities as unknown[]).filter((e) => typeof e === 'string' && e.trim().length > 0);
    }

    _summaryEntityLinks() {
        const r = this._summaryResult();
        if (!r || !Array.isArray(r.entity_links)) return [];
        return (r.entity_links as Record<string, any>[]).filter((item) => (
            item
            && typeof item === 'object'
            && typeof item.entity_id === 'string'
            && item.entity_id.length > 0
            && typeof item.name === 'string'
            && item.name.length > 0
        ));
    }

    _summaryText() {
        const r = this._summaryResult();
        return r && typeof r.summary === 'string' ? r.summary : '';
    }

    _summaryGeneratedAt() {
        const r = this._summaryResult();
        if (!r) return '';
        const raw = typeof r.generated_at === 'string' && r.generated_at.length > 0 ? r.generated_at : null;
        if (!raw) return '';
        const date = new Date(raw);
        if (Number.isNaN(date.getTime())) return '';
        return _formatHHMM(date);
    }

    _summaryRevalidating() {
        const r = this._summaryResult();
        return r && r.revalidating === true;
    }

    _summaryPanelTitle() {
        if (this._isPeriod()) {
            return this.t('daily_notes_page.summary_panel_title_period');
        }
        return this.t('daily_notes_page.summary_panel_title_daily');
    }

    _summaryMetaLine() {
        if (this._summaryBusy()) return this.t('daily_notes_page.summary_generating');
        if (this._summaryRevalidating()) {
            const at = this._summaryGeneratedAt();
            return at
                ? this.t('daily_notes_page.summary_revalidating_last', { time: at })
                : this.t('daily_notes_page.summary_revalidating');
        }
        const at = this._summaryGeneratedAt();
        return at
            ? this.t('daily_notes_page.summary_generated_at', { time: at })
            : this.t('daily_notes_page.summary_none');
    }

    _buildEntityLookupMap() {
        const map = new Map<string, Record<string, any>>();
        for (const entity of this._summaryEntityLinks()) {
            const key = normalizeSummaryEntityLabelKey(entity.name);
            if (!key || map.has(key)) continue;
            map.set(key, entity);
        }
        const noteMap = buildSummaryEntityLookupFromNoteBuckets(this._noteEntitiesByNoteId);
        for (const [key, entity] of noteMap.entries()) {
            if (!map.has(key)) map.set(key, entity);
        }
        return map;
    }

    _entityTypeItems(): Record<string, any>[] {
        const ctrl = this._entityTypes;
        if (!ctrl || ctrl.items === undefined || !Array.isArray(ctrl.items)) {
            return [];
        }
        return ctrl.items as Record<string, any>[];
    }

    _loadEntityTypesCatalog() {
        const ns = this._currentNamespace();
        const payload: Record<string, unknown> = { limit: 200, offset: 0 };
        if (typeof ns === 'string' && ns.length > 0) {
            payload.namespace = ns;
        }
        this._entityTypes.load(payload);
    }

    _getEntityTagIcon(entity: Record<string, any>): string {
        return entityDisplayIconName(entity, this._entityTypeItems());
    }

    _getNoteSubtypeIcon(note: Record<string, any>) {
        const sub = typeof note && note.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        if (sub.length === 0) return 'doc-detail';
        const icon = (NOTE_SUBTYPE_ICONS as Record<string, string>)[sub];
        return icon === undefined ? 'doc-detail' : icon;
    }

    _noteHasAnalysisError(note: Record<string, any>) {
        const attrs = note && note.attributes;
        return !!(
            attrs
            && typeof attrs === 'object'
            && typeof attrs.ai_analysis_last_error === 'string'
            && attrs.ai_analysis_last_error.trim().length > 0
        );
    }

    _notePreview(note: Record<string, any>) {
        const attrs = note && note.attributes;
        if (attrs && typeof attrs === 'object'
            && typeof attrs.ai_summary === 'string' && attrs.ai_summary.trim().length > 0) {
            return this._truncate(attrs.ai_summary, 260);
        }
        if (attrs && typeof attrs === 'object'
            && typeof attrs.ai_summary_snippet === 'string' && attrs.ai_summary_snippet.trim().length > 0) {
            return this._truncate(attrs.ai_summary_snippet, 260);
        }
        if (attrs && typeof attrs === 'object'
            && attrs.ai_analysis_draft && typeof attrs.ai_analysis_draft === 'object'
            && attrs.ai_analysis_draft.note && typeof attrs.ai_analysis_draft.note === 'object'
            && typeof attrs.ai_analysis_draft.note.description === 'string'
            && attrs.ai_analysis_draft.note.description.trim().length > 0) {
            return this._truncate(
                stripOuterMarkdownCodeFence(attrs.ai_analysis_draft.note.description),
                260,
            );
        }
        const emptyLabel = this.t('note_content.no_description');
        const descRaw = typeof note.description === 'string' && note.description.trim().length > 0
            ? note.description
            : null;
        if (descRaw === null) {
            return emptyLabel;
        }
        return this._truncate(stripOuterMarkdownCodeFence(descRaw), 220);
    }

    _truncate(text: unknown, maxLength: number): string {
        const s = typeof text === 'string' ? text.trim() : '';
        if (s.length <= maxLength) return s;
        return `${s.slice(0, maxLength).trimEnd()}...`;
    }

    _renderNoteCardPreview(note: Record<string, any>) {
        if (this._noteHasAnalysisError(note)) {
            const attrs = note.attributes;
            const raw = attrs.ai_analysis_last_error;
            const detail = this._truncate(typeof raw === 'string' ? raw.trim() : '', 220);
            return html`
                <div class="note-preview-error">
                    <span class="note-preview-error-title">${this.t('daily_notes_page.note_preview_analysis_failed_title')}</span>
                    <p class="note-preview-error-detail">${detail}</p>
                </div>
            `;
        }
        return html`<p class="note-text">${this._notePreview(note)}</p>`;
    }

    _formatTime(dateString: unknown): string {
        const d = new Date(dateString as string);
        if (Number.isNaN(d.getTime())) return '';
        return _formatHHMM(d);
    }

    _openNote(note: Record<string, any>) {
        if (!note || typeof note.entity_id !== 'string' || note.entity_id.length === 0) {
            throw new Error('CRMDailyNotesPage._openNote: note.entity_id required');
        }
        this.navigate('note', { itemId: note.entity_id });
    }

    _openEntity(entity: Record<string, any> | null, event?: Event): void {
        if (event) event.stopPropagation();
        if (!entity || typeof entity.entity_id !== 'string' || entity.entity_id.length === 0) {
            throw new Error('CRMDailyNotesPage._openEntity: entity.entity_id required');
        }
        this.navigate('entity', { itemId: entity.entity_id });
    }

    _openEntityId(entityId: unknown, event?: Event): void {
        if (event) event.stopPropagation();
        if (typeof entityId !== 'string' || entityId.length === 0) {
            throw new Error('CRMDailyNotesPage._openEntityId: entityId required');
        }
        this.navigate('entity', { itemId: entityId });
    }

    _renderSummaryText(summaryText: unknown): unknown {
        if (typeof summaryText !== 'string' || summaryText.length === 0) return '';
        const parts: unknown[] = [];
        let lastIndex = 0;
        const re = new RegExp(SUMMARY_ENTITY_TOKEN_RE.source, 'gi');
        let match: RegExpExecArray | null;
        while ((match = re.exec(summaryText)) !== null) {
            const [full, rawLabel, entityId] = match as unknown as [string, string, string];
            if (match.index > lastIndex) {
                parts.push(summaryText.slice(lastIndex, match.index));
            }
            const label = rawLabel.startsWith('@') ? rawLabel : `@${rawLabel}`;
            parts.push(html`
                <button
                    class="summary-inline-entity"
                    type="button"
                    @click=${(e: any) => this._openEntityId(entityId, e)}
                >${label}</button>
            `);
            lastIndex = match.index + full.length;
        }
        if (lastIndex < summaryText.length) {
            parts.push(summaryText.slice(lastIndex));
        }
        return parts;
    }

    _renderSummary() {
        const tags = this._summaryEntities();
        const lookup = this._buildEntityLookupMap();
        const summaryText = this._summaryText();
        const busy = this._summaryBusy();
        return html`
            <div class="summary-header">
                <h3 class="summary-title">
                    <span class="summary-title-icon" aria-hidden="true"></span>
                    <span class="summary-title-text">${this._summaryPanelTitle()}</span>
                </h3>
                <button
                    class="summary-refresh-btn"
                    type="button"
                    title=${this.t('daily_notes_page.summary_rebuild_tooltip')}
                    ?disabled=${busy}
                    @click=${this._onRefreshSummary}
                >
                    <span
                        class="summary-refresh-icon ${busy ? 'spinning' : ''}"
                        aria-hidden="true"
                    ></span>
                </button>
            </div>
            <div class="summary-meta">${this._summaryMetaLine()}</div>
            <p class="summary-text">${this._renderSummaryText(summaryText)}</p>
            <div class="summary-tags">
                ${tags.map((tag, i) => {
                    const tone = SUMMARY_CHIP_TONES[i % SUMMARY_CHIP_TONES.length];
                    const resolved = resolveSummaryChipEntity(tag, lookup);
                    const chipIcon = resolved
                        ? entityDisplayIconName(resolved, this._entityTypeItems())
                        : summaryChipUnresolvedIconName();
                    if (resolved) {
                        return html`
                            <button
                                class="summary-chip summary-chip--clickable ${tone}"
                                type="button"
                                title=${this.t('daily_notes_page.summary_entity_open')}
                                @click=${(e: any) => this._openEntity(resolved, e)}
                            >
                                <platform-icon name=${chipIcon} size="14"></platform-icon>${tag}
                            </button>
                        `;
                    }
                    return html`
                        <span class="summary-chip ${tone}">
                            <platform-icon name=${chipIcon} size="14"></platform-icon>${tag}
                        </span>
                    `;
                })}
            </div>
        `;
    }

    _renderNoteCard(note: Record<string, any>) {
        const related = Array.isArray(this._noteEntitiesByNoteId[note.entity_id])
            ? this._noteEntitiesByNoteId[note.entity_id]
            : [];
        const isAnalyzing = this._isAnalyzingNote(note);
        const analyzeTask = this._analyzeTaskForNote(note.entity_id);
        const progressPctRaw = analyzeTask && typeof analyzeTask.progress_pct === 'number'
            ? analyzeTask.progress_pct
            : 0;
        const progressPct = Math.max(0, Math.min(100, progressPctRaw));
        const progressStage = analyzeTask && typeof analyzeTask.stage === 'string' && analyzeTask.stage.length > 0
            ? analyzeTask.stage
            : this.t('daily_notes_page.analysis_stage_fallback');
        const draft = this._hasAnalysisDraft(note);
        const applied = this._hasAnalysisApplied(note);
        const needsAi = this._noteNeedsAi(note);
        const analysisFailed = !isAnalyzing && this._noteHasAnalysisError(note);
        const analyzeBtnModifier = analysisFailed
            ? 'analysis-failed'
            : draft
                ? 'has-draft'
                : applied
                    ? 'has-applied'
                    : needsAi
                        ? 'needs-ai'
                        : '';
        const analyzeTitle = analysisFailed
            ? this.t('daily_notes_page.analysis_tooltip_after_error')
            : draft
                ? this.t('daily_notes_page.analysis_open_draft')
                : applied
                    ? this.t('daily_notes_page.analysis_view_applied')
                    : this.t('daily_notes_page.analysis_run');
        const authorId = typeof note.user_id === 'string' && note.user_id.length > 0 ? note.user_id : '';
        const updated = typeof note.updated_at === 'string' && note.updated_at.length > 0 ? note.updated_at : note.created_at;
        const time = typeof updated === 'string' && updated.length > 0 ? this._formatTime(updated) : '';
        return html`
            <article class="note-card" @click=${() => this._openNote(note)}>
                <div class="note-tags">
                    <span class="note-type-badge">
                        <platform-icon name=${this._getNoteSubtypeIcon(note)} size="14"></platform-icon>
                    </span>
                    ${(related as Record<string, any>[]).map((entity: Record<string, any>, i: number) => html`
                        <button
                            class="note-tag ${ENTITY_TAG_TONES[i % ENTITY_TAG_TONES.length]}"
                            type="button"
                            @click=${(e: any) => this._openEntity(entity, e)}
                        >
                            <platform-icon name=${this._getEntityTagIcon(entity)} size="12"></platform-icon>
                            ${typeof entity.name === 'string' && entity.name.length > 0 ? entity.name : 'Entity'}
                        </button>
                    `)}
                </div>
                ${typeof note.score === 'number' ? html`
                    <div class="card-score">
                        <div class="score-bar" style="width: ${Math.round(note.score * 100)}%"></div>
                        <span class="score-label">${(note.score * 100).toFixed(0)}%</span>
                        <span class="match-type-badge">${this._searchMode}</span>
                    </div>
                ` : ''}
                <h3 class="note-title">${note.name}</h3>
                ${this._renderNoteCardPreview(note)}
                ${isAnalyzing ? html`
                    <div class="note-analysis-progress">
                        <div class="note-analysis-progress-head">
                            <span class="note-analysis-progress-stage">${progressStage}</span>
                            <span class="note-analysis-progress-pct">${progressPct}%</span>
                        </div>
                        <div class="note-analysis-progress-line">
                            <span style="width:${progressPct}%;"></span>
                        </div>
                    </div>
                ` : ''}
                <div class="note-footer">
                    ${authorId.length > 0
                        ? html`<platform-user-chip user-id=${authorId} size="sm" @click=${(e: any) => e.stopPropagation()}></platform-user-chip>`
                        : html`<span></span>`}
                    <div class="note-footer-right">
                        <span class="published-at">${time}</span>
                        <button
                            class="analyze-btn ${isAnalyzing ? 'analyzing' : ''} ${analyzeBtnModifier}"
                            type="button"
                            ?disabled=${isAnalyzing}
                            @click=${(e: any) => { e.stopPropagation(); this._onAnalyzeNote(note); }}
                            title=${analyzeTitle}
                        >
                            <platform-icon name="ai" size="14" ?colored=${!analysisFailed}></platform-icon>
                        </button>
                    </div>
                </div>
            </article>
        `;
    }

    _renderSearchBoxInner(includeSearchModeToggle = true) {
        const toolbarInputStyle = includeSearchModeToggle
            ? undefined
            : 'flex:1;min-width:0;width:100%;box-sizing:border-box';
        return html`
            <platform-icon name="search" size="14"></platform-icon>
            <input
                class="search-input"
                type="text"
                data-canon="search-as-you-type"
                style=${toolbarInputStyle}
                placeholder=${this.t('search.placeholder')}
                .value=${this._query}
                @input=${this._onSearchInput}
            />
            ${includeSearchModeToggle && this._query.trim().length > 0 ? html`
                <div class="search-mode-toggle">
                    ${SEARCH_MODES.map((mode) => html`
                        <button
                            type="button"
                            class="search-mode-btn ${this._searchMode === mode ? 'active' : ''}"
                            @click=${(e: any) => { e.preventDefault(); this._onSearchModeChange(mode); }}
                        >${mode}</button>
                    `)}
                </div>
            ` : ''}
        `;
    }

    async _openMobileDateRange() {
        await this.updateComplete;
        const el = this.renderRoot.querySelector('platform-date-picker.crm-mobile-date-picker-anchor');
        if (!el) {
            throw new Error('Mobile date picker is not mounted');
        }
        (el as unknown as { requestOpen(): void }).requestOpen();
    }

    _toggleMobileHeaderSearch() {
        this._mobileHeaderSearch = !this._mobileHeaderSearch;
    }

    _closeMobileHeaderSearch() {
        this._mobileHeaderSearch = false;
    }

    _renderMobilePageHeader() {
        return html`
            <div class="daily-notes-mobile-header-wrap">
                <page-header
                    title=${this.t('daily_notes_page.section_title')}
                    subtitle=""
                    .mobileToolbarMode=${this._mobileHeaderSearch ? 'search' : 'title'}
                >
                    <div slot="toolbar-search" class="mobile-toolbar-search-row">
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${this._closeMobileHeaderSearch}
                            title=${this.t('daily_notes_page.mobile_header_close_search')}
                        >
                            <platform-icon name="close" size="16"></platform-icon>
                        </button>
                        <label
                            class="search-box mobile-header-search-box"
                            style="display:flex;align-items:center;gap:var(--space-2);flex:1;min-width:0;width:100%;box-sizing:border-box"
                        >
                            ${this._renderSearchBoxInner(false)}
                        </label>
                    </div>
                    <div slot="actions">
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${openCrmLaraAssistant}
                            title=${this.t('lara.assistant')}
                            aria-label=${this.t('lara.assistant')}
                        >
                            <platform-icon name="sparkle" size="18"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn mobile-header-summary-btn"
                            @click=${() => { this._summaryOpen = true; }}
                            title=${this.t('daily_notes_page.summary_fab_open')}
                        >
                            <platform-icon name="refresh" size="18"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            @click=${this._openMobileDateRange}
                            title=${this.t('daily_notes_page.mobile_header_date_range')}
                        >
                            <platform-icon name="calendar" size="18"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn"
                            ?disabled=${this._creatingNote}
                            @click=${this._onCreateNote}
                            title=${this.t('daily_notes_page.add_note')}
                        >
                            ${this._creatingNote
                                ? html`<glass-spinner size="xs"></glass-spinner>`
                                : html`<platform-icon name="plus" size="18"></platform-icon>`}
                        </button>
                        <button
                            type="button"
                            class="mobile-header-icon-btn ${this._mobileHeaderSearch ? 'active' : ''}"
                            @click=${this._toggleMobileHeaderSearch}
                            title=${this.t('daily_notes_page.mobile_header_search')}
                        >
                            <platform-icon name="search" size="18"></platform-icon>
                        </button>
                    </div>
                </page-header>
                <platform-date-picker
                    class="crm-mobile-date-picker-anchor"
                    selection="range"
                    .value=${{ start: this._range().from, end: this._range().to }}
                    @change=${this._onDateRangeChange}
                ></platform-date-picker>
            </div>
        `;
    }

    override render(): TemplateResult {
        const filteredNotes = this._filteredNotes();
        const loading = this._notes.loading || this._searchLoading;
        return html`
            ${this._isMobile ? this._renderMobilePageHeader() : html`
            <div class="section-label">${this.t('daily_notes_page.section_title')}</div>
            <div class="top-row">
                <h1 class="title">
                    ${this.t('daily_notes_page.section_title')}
                    <button class="title-settings" type="button" @click=${() => this.navigate('settings')}>
                        <platform-icon name="settings" size="18"></platform-icon>
                    </button>
                </h1>
                <label class="search-box">
                    ${this._renderSearchBoxInner()}
                </label>
                <div class="toolbar-actions">
                    <platform-date-picker
                        class="date-input"
                        labeled
                        selection="range"
                        .value=${{ start: this._range().from, end: this._range().to }}
                        @change=${this._onDateRangeChange}
                    ></platform-date-picker>
                    <div class="toolbar-voice" title=${this.t('daily_notes_page.voice_tooltip')}>
                        <platform-voice-dictation
                            @transcribed=${this._onVoiceTranscribed}
                        ></platform-voice-dictation>
                    </div>
                    <button class="cta-btn" type="button" ?disabled=${this._creatingNote} @click=${this._onCreateNote}>
                        <span class="cta-btn-content">
                            ${this._creatingNote
                                ? html`<glass-spinner size="xs"></glass-spinner>`
                                : ''}
                            ${this._creatingNote
                                ? this.t('daily_notes_page.add_note_creating')
                                : this.t('daily_notes_page.add_note')}
                        </span>
                    </button>
                </div>
            </div>
            `}

            <div class="layout">
                <section class="main-column">
                    <div class="cards-scroll">
                        ${loading && filteredNotes.length === 0 ? html`
                            <div class="empty"><glass-spinner size="sm"></glass-spinner></div>
                        ` : filteredNotes.length === 0 ? html`
                            <div class="empty">
                                <div>${this.t('daily_notes_page.empty_period')}</div>
                                <div class="empty-hint">${this.t('daily_notes_page.empty_period_hints')}</div>
                            </div>
                        ` : html`
                            <div class="cards-grid">
                                ${filteredNotes.map((note) => this._renderNoteCard(note))}
                            </div>
                        `}
                    </div>
                </section>
                <aside class="summary-panel">
                    ${this._renderSummary()}
                </aside>
            </div>

            ${this._isMobile && this._summaryOpen ? html`
                <div class="summary-overlay" @click=${(e: any) => { if (e.target === e.currentTarget) this._summaryOpen = false; }}>
                    <aside class="summary-panel">
                        ${this._renderSummary()}
                    </aside>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('crm-daily-notes-page', CRMDailyNotesPage);
