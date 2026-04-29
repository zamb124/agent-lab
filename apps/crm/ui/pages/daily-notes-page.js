/**
 * DailyNotesPage — главный экран CRM («ежедневник»).
 *
 * Источники данных (только helpers, никаких прямых импортов resource-объектов):
 *   - useCursorList('crm/notes_list')   — лента заметок за выбранный диапазон дат
 *   - useOp('crm/note_search')          — текстовый/семантический поиск по заметкам
 *   - useOp('crm/daily_summary')        — AI-сводка одного дня
 *   - useOp('crm/period_summary')       — AI-сводка диапазона
 *   - useOp('crm/task_daily_summary_start') / 'crm/task_period_summary_start' — пересчёт сводки
 *   - useOp('crm/note_voice_input')     — STT (запись голоса → текст)
 *   - useOp('crm/note_analyze_start')   — старт AI-анализа заметки
 *   - useOp('crm/entity_cards_bulk')    — batch-загрузка карточек связанных entity
 *
 * Realtime: подписка на WS-события `crm/note/updated` и `crm/daily_summary/updated`,
 * которые публикует backend через `core/ui_events/dispatcher.py`. Изменение
 * namespace приходит как `ui/namespace/changed` (CoreEvents.UI_NAMESPACE_CHANGED) —
 * page перезапрашивает ленту и сводку.
 *
 * Открытие заметки: страница навигирует на роут `note` (`/crm/notes/:itemId`),
 * редактирование живёт на `note-page`, отдельной модалки нет. Создание новой
 * заметки и распознавание голоса передают `itemId='new'`/`itemId='draft-<ts>'`,
 * `note-page` отвечает за edit-режим.
 *
 * Открытие связанной entity (chip / related): пока entity-page не реализован,
 * страница показывает информационный toast и не пытается открыть несуществующую
 * модалку.
 */

import { html, css } from 'lit';
import { CRMNamespacePage } from '../base/crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import {
    getUserMediaCompat,
    hasGetUserMediaApi,
    pickVoiceMimeType,
} from '@platform/lib/utils/voice-recording.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/layout/page-header.js';

function _formatIsoDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _today() {
    return _formatIsoDate(new Date());
}

function _formatHHMM(date) {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

function _normalizeChipKey(label) {
    if (typeof label !== 'string') return null;
    let s = label.trim();
    if (!s) return null;
    if (s.startsWith('@')) s = s.slice(1).trim();
    s = s.replace(/^["'([{]+|["')\]}.,;:!?]+$/g, '').trim();
    return s.length === 0 ? null : s.toLowerCase();
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
const ENTITY_TYPE_ICONS = {
    member: 'user-shield',
    contact: 'user',
    company: 'building',
    namespace: 'layers',
    organization: 'database',
};
const SEARCH_MODES = ['text', 'semantic', 'hybrid'];
const ACTIVE_ANALYZE_TASK_STATUSES = new Set(['pending', 'running']);
const ANALYZE_TASKS_POLL_MS = 2500;

export class CRMDailyNotesPage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static properties = {
        _query: { state: true },
        _searchMode: { state: true },
        _isMobile: { state: true },
        _summaryOpen: { state: true },
        _voiceState: { state: true },
        _noteEntitiesByNoteId: { state: true },
        _analyzeTasksByNoteId: { state: true },
        _searchResults: { state: true },
        _searchLoading: { state: true },
        _creatingNote: { state: true },
        _mobileHeaderSearch: { state: true },
    };

    static styles = [
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
                grid-template-columns: 1fr 350px;
                gap: var(--space-4);
                width: 100%;
                max-width: 100%;
                min-width: 0;
                flex: 1;
                min-height: 0;
                overflow: hidden;
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
                border: 1px solid var(--crm-stroke);
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

            .search-voice-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-full);
                flex-shrink: 0;
            }
            .search-voice-btn:hover { background: var(--glass-tint-medium); color: var(--text-primary); }
            .search-voice-btn.recording {
                background: var(--color-danger, #ef4444);
                color: white;
                animation: searchVoicePulse 1.4s ease-in-out infinite;
            }
            .search-voice-btn:disabled { opacity: 0.5; cursor: wait; }
            @keyframes searchVoicePulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.55; }
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
                color: var(--text-inverse);
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

            .voice-btn {
                min-height: 44px;
                width: 44px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
                background: var(--crm-surface);
                color: var(--text-secondary);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }
            .voice-btn.recording {
                background: rgba(239, 68, 68, 0.12);
                border-color: #ef4444;
                color: #ef4444;
                animation: voice-pulse 1.5s ease-in-out infinite;
            }
            .voice-btn.processing { opacity: 0.6; cursor: wait; }
            @keyframes voice-pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.08); }
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
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
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
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }
            .note-card:hover {
                border-color: var(--crm-stroke-strong);
                background: var(--crm-surface-elevated);
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
            .analyze-btn.analyzing { animation: analyze-busy 1.2s ease-in-out infinite; cursor: wait; }
            .analyze-btn:disabled { opacity: 0.72; cursor: not-allowed; }
            @keyframes analyze-busy { 0%,100% { opacity: 1; } 50% { opacity: 0.55; } }
            @keyframes ai-pulse {
                0%,100% { box-shadow: 0 0 6px rgba(139,92,246,0.2); }
                50% { box-shadow: 0 0 12px rgba(139,92,246,0.4); }
            }

            .summary-panel {
                background: var(--crm-summary-bg);
                border-radius: var(--radius-xl);
                border: 1px solid var(--crm-summary-stroke);
                padding: var(--space-4);
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
                align-items: flex-start;
                gap: var(--space-2);
                margin: 0;
            }
            .summary-title-text {
                flex: 1 1 12rem;
                min-width: 0;
                font-size: var(--text-xl);
                font-weight: 700;
                line-height: 1.35;
                background: var(--crm-summary-title-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .summary-title-icon {
                width: 36px;
                height: 36px;
                border-radius: var(--radius-full);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-summary-title-gradient);
            }
            .summary-title-icon platform-icon { color: var(--text-inverse); }
            .summary-refresh-btn {
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: none;
                background: var(--crm-summary-title-gradient);
                color: var(--text-inverse);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                margin-top: 2px;
            }
            .summary-refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; }
            .summary-refresh-icon.spinning {
                animation: summary-spin 0.9s linear infinite;
                transform-origin: center;
            }
            @keyframes summary-spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

            .summary-meta {
                color: var(--crm-summary-meta);
                font-size: var(--text-base);
                margin-bottom: var(--space-4);
            }
            .summary-text {
                color: var(--text-primary);
                font-size: var(--text-xl);
                line-height: 1.32;
                margin: 0;
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
            }
            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
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
                color: var(--text-inverse);
                box-shadow: 0 2px 8px rgba(153, 166, 249, 0.35);
            }
            .mobile-header-icon-btn.mobile-header-summary-btn:hover {
                filter: brightness(1.06);
            }
            .mobile-header-icon-btn.mobile-header-summary-btn platform-icon {
                color: var(--text-inverse);
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

    constructor() {
        super();
        this._dailyNotesUi = this.useSlice('crm/daily_notes_ui');
        this._query = '';
        this._searchMode = 'hybrid';
        this._summaryOpen = false;
        this._voiceState = 'idle';
        this._voiceMode = 'note';
        this._noteEntitiesByNoteId = {};
        this._analyzeTasksByNoteId = {};
        this._searchResults = [];
        this._searchLoading = false;
        this._creatingNote = false;
        this._mobileHeaderSearch = false;
        this._isMobile = typeof window !== 'undefined' && window.innerWidth <= 767;

        this._notes = this.useCursorList('crm/notes_list');
        this._search = this.useOp('crm/note_search');
        this._dailySummary = this.useOp('crm/daily_summary');
        this._periodSummary = this.useOp('crm/period_summary');
        this._dailySummaryStart = this.useOp('crm/task_daily_summary_start');
        this._periodSummaryStart = this.useOp('crm/task_period_summary_start');
        this._voice = this.useOp('crm/note_voice_input');
        this._analyze = this.useOp('crm/note_analyze_start');
        this._cardsBulk = this.useOp('crm/entity_cards_bulk');
        this._tasks = this.useResource('crm/tasks');

        this._routeKeySel = this.select((s) => s.router.routeKey);

        this._mql = null;
        this._mqlListener = null;
        this._debounceTimer = null;
        this._mediaRecorder = null;
        this._audioChunks = [];
        this._lastSearchRequestId = null;
        this._analyzeTasksPollTimer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._mqlListener = (e) => {
                this._isMobile = e.matches;
                if (!e.matches) {
                    this._mobileHeaderSearch = false;
                }
            };
            this._mql.addEventListener('change', this._mqlListener);
            this._isMobile = this._mql.matches;
        }

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._reloadNotes();
            this._reloadSummary();
        });
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => {
            if (this._routeKeySel.value !== 'notes') {
                return;
            }
            this._reloadNotes();
        });
        this.useEvent('crm/note/updated', (event) => this._onNoteWsUpdate(event.payload));
        this.useEvent('crm/daily_summary/updated', (event) => this._onSummaryWsUpdate(event.payload, false));
        this.useEvent('crm/period_summary/updated', (event) => this._onSummaryWsUpdate(event.payload, true));

        this.useEvent('crm/note_search/succeeded', (event) => {
            if (event.meta && event.meta.causation_id !== this._lastSearchRequestId) return;
            const result = event.payload && event.payload.result;
            const items = result && Array.isArray(result.items) ? result.items : [];
            this._searchResults = items;
            this._searchLoading = false;
            this._loadCardsForVisibleNotes(items);
        });
        this.useEvent('crm/note_search/failed', () => { this._searchLoading = false; });

        this.useEvent('crm/note_voice_input/succeeded', (event) => this._onVoiceTranscribed(event.payload.result));
        this.useEvent(this._tasks.resource.events.LIST_LOADED, () => {
            this._rebuildAnalyzeTaskMap();
            this._syncAnalyzeTasksPolling();
        });
        this.useEvent(this._analyze.op.events.SUCCEEDED, () => {
            this._loadAnalyzeTasks();
            this._syncAnalyzeTasksPolling();
        });
        this.useEvent(this._analyze.op.events.FAILED, () => this._syncAnalyzeTasksPolling());

        this.useEvent('crm/notes_list/loaded', (event) => {
            const items = event.payload && Array.isArray(event.payload.items) ? event.payload.items : [];
            if (this._query.trim().length === 0) {
                this._loadCardsForVisibleNotes(items);
            }
        });

        this._reloadNotes();
        this._reloadSummary();
        this._loadAnalyzeTasks();
    }

    disconnectedCallback() {
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
        this._stopAnalyzeTasksPolling();
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

    _isPeriod() { return this._dailyNotesUi.value.range.from !== this._dailyNotesUi.value.range.to; }

    _reloadNotes() {
        const filters = {
            date_from: this._dailyNotesUi.value.range.from,
            date_to: this._dailyNotesUi.value.range.to,
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
        const payload = {
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

    _rebuildAnalyzeTaskMap() {
        const byNoteId = {};
        const items = this._tasks.items;
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

    _hasActiveAnalyzeTasks() {
        return Object.keys(this._analyzeTasksByNoteId).length > 0 || this._analyze.busy;
    }

    _syncAnalyzeTasksPolling() {
        if (this._hasActiveAnalyzeTasks()) {
            this._startAnalyzeTasksPolling();
            return;
        }
        this._stopAnalyzeTasksPolling();
    }

    _startAnalyzeTasksPolling() {
        if (this._analyzeTasksPollTimer !== null) {
            return;
        }
        this._analyzeTasksPollTimer = window.setInterval(() => {
            this._loadAnalyzeTasks();
        }, ANALYZE_TASKS_POLL_MS);
    }

    _stopAnalyzeTasksPolling() {
        if (this._analyzeTasksPollTimer === null) {
            return;
        }
        window.clearInterval(this._analyzeTasksPollTimer);
        this._analyzeTasksPollTimer = null;
    }

    _reloadSummary(options) {
        const force_rebuild = options && options.force_rebuild === true;
        const ns = this._currentNamespace();
        const payload = this._isPeriod()
            ? { date_from: this._dailyNotesUi.value.range.from, date_to: this._dailyNotesUi.value.range.to, namespace: ns, force_rebuild }
            : { date: this._dailyNotesUi.value.range.from, namespace: ns, force_rebuild };
        if (this._isPeriod()) {
            this._periodSummary.run(payload);
        } else {
            this._dailySummary.run(payload);
        }
    }

    _onSummaryWsUpdate(payload, periodEvent) {
        if (!payload || typeof payload !== 'object') return;
        const ns = this._currentNamespace();
        const payloadNs = payload.namespace === null || payload.namespace === undefined
            ? null
            : (typeof payload.namespace === 'string' && payload.namespace.length > 0 ? payload.namespace : null);
        if (ns !== payloadNs) return;
        const st = payload.state;
        if (!st || typeof st !== 'object') return;
        if (periodEvent === true) {
            if (!this._isPeriod()) return;
            if (payload.date_from !== this._dailyNotesUi.value.range.from || payload.date_to !== this._dailyNotesUi.value.range.to) return;
            this._periodSummary.applyWsPatch({
                summary: typeof st.summary === 'string' ? st.summary : '',
                entities: Array.isArray(st.entities) ? st.entities : [],
                revalidating: false,
                generated_at: typeof st.generated_at === 'string' ? st.generated_at : new Date().toISOString(),
            });
            return;
        }
        if (this._isPeriod()) return;
        if (payload.date !== this._dailyNotesUi.value.range.from) return;
        this._dailySummary.applyWsPatch({
            summary: typeof st.summary === 'string' ? st.summary : '',
            entities: Array.isArray(st.entities) ? st.entities : [],
            revalidating: false,
            generated_at: typeof st.generated_at === 'string' ? st.generated_at : new Date().toISOString(),
        });
    }

    _onNoteWsUpdate(payload) {
        if (!payload || typeof payload !== 'object') return;
        if (typeof payload.note_id !== 'string' || payload.note_id.trim().length === 0) return;
        const ns = this._currentNamespace();
        const payloadNs = payload.namespace === null || payload.namespace === undefined
            ? null
            : (typeof payload.namespace === 'string' && payload.namespace.length > 0 ? payload.namespace : null);
        if (ns !== payloadNs) return;
        if (typeof payload.note_date !== 'string') return;
        if (payload.note_date < this._dailyNotesUi.value.range.from || payload.note_date > this._dailyNotesUi.value.range.to) return;
        const next = { ...this._noteEntitiesByNoteId };
        delete next[payload.note_id.trim()];
        this._noteEntitiesByNoteId = next;
        this._reloadNotes();
        this._reloadSummary();
        this._loadAnalyzeTasks();
    }

    _onSearchInput(event) {
        this._query = event.target.value;
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
        const payload = { q, search_mode: this._searchMode, limit: 50 };
        if (typeof ns === 'string' && ns.length > 0) payload.namespace = ns;
        const event = this._search.run(payload);
        this._lastSearchRequestId = event && typeof event.id === 'string' ? event.id : null;
    }

    _onSearchModeChange(mode) {
        this._searchMode = mode;
        if (this._query.trim().length > 0) this._runSearch();
    }

    _onDateRangeChange(event) {
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

    async _onVoiceToggle() {
        await this._startVoice('note', 'voice-input.webm');
    }

    async _onVoiceSearchToggle() {
        await this._startVoice('search', 'voice-search.webm');
    }

    async _startVoice(mode, fileName) {
        if (this._voiceState === 'recording') {
            this._stopVoice();
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
        this._voiceMode = mode;
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
            this._voice.run({ audio: blob, file_name: fileName });
        };
        this._mediaRecorder.start();
        this._voiceState = 'recording';
        this.toast('toast.note.voice_started', { type: 'info' });
    }

    _stopVoice() {
        if (this._mediaRecorder && this._mediaRecorder.state === 'recording') {
            this._mediaRecorder.stop();
        }
    }

    _onVoiceTranscribed(result) {
        const mode = this._voiceMode;
        this._voiceState = 'idle';
        this._voiceMode = 'note';
        this._mediaRecorder = null;
        this._audioChunks = [];
        if (!result || typeof result.text !== 'string' || result.text.trim().length === 0) {
            this.toast('toast.note.voice_empty', { type: 'warning' });
            return;
        }
        if (mode === 'search') {
            this._query = result.text.trim();
            this._runSearch();
            return;
        }
        this.navigate('note', { itemId: 'new' });
    }

    _onAnalyzeNote(note) {
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
        this._loadAnalyzeTasks();
        this._syncAnalyzeTasksPolling();
        this.openModal('crm.ai_analysis', { noteId: note.entity_id });
    }

    _onRefreshSummary() {
        this._reloadSummary({ force_rebuild: true });
    }

    _loadCardsForVisibleNotes(notes) {
        const ids = notes
            .map((n) => n && typeof n.entity_id === 'string' ? n.entity_id.trim() : null)
            .filter((id) => typeof id === 'string' && id.length > 0)
            .filter((id) => !Object.prototype.hasOwnProperty.call(this._noteEntitiesByNoteId, id));
        if (ids.length === 0) return;
        this._cardsBulk.run({ entity_ids: ids });
    }

    _onCardsBulkLoaded(payload) {
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

    updated(changedProps) {
        super.updated(changedProps);
        const cardsResult = this._cardsBulk.lastResult;
        if (cardsResult && cardsResult !== this._lastCardsResult) {
            this._lastCardsResult = cardsResult;
            this._onCardsBulkLoaded(cardsResult);
        }
    }

    _hasAnalysisDraft(note) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return false;
        const draft = attrs.ai_analysis_draft;
        return typeof draft === 'object' && draft !== null && typeof draft.draft_version === 'number';
    }

    _hasAnalysisApplied(note) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return false;
        return typeof attrs.ai_analysis_applied_at === 'string'
            && attrs.ai_analysis_applied_at.length > 0
            && !this._hasAnalysisDraft(note);
    }

    _noteNeedsAi(note) {
        const attrs = note && note.attributes;
        if (!attrs || typeof attrs !== 'object') return true;
        if (attrs.ai_analysis_applied_at) return false;
        if (attrs.ai_analysis_draft && typeof attrs.ai_analysis_draft === 'object') return false;
        return true;
    }

    _isAnalyzingNote(note) {
        if (!note || typeof note.entity_id !== 'string') {
            return false;
        }
        if (this._analyze.busy
            && this._analyze.lastResult
            && this._analyze.lastResult.note_id === note.entity_id) {
            return true;
        }
        return this._analyzeTaskForNote(note.entity_id) !== null;
    }

    _analyzeTaskForNote(noteId) {
        if (typeof noteId !== 'string' || noteId.length === 0) {
            return null;
        }
        const task = this._analyzeTasksByNoteId[noteId];
        return task === undefined ? null : task;
    }

    _filteredNotes() {
        const q = this._query.trim();
        if (q.length === 0) {
            return this._notes.items;
        }
        if (this._isMobile && q.length < 2) {
            return this._notes.items;
        }
        return this._searchResults;
    }

    _summaryResult() {
        return this._isPeriod() ? this._periodSummary.lastResult : this._dailySummary.lastResult;
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
        return r.entities.filter((e) => typeof e === 'string' && e.trim().length > 0);
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
            return this.t('daily_notes_page.summary_panel_title_period', { from: this._dailyNotesUi.value.range.from, to: this._dailyNotesUi.value.range.to });
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
        const map = new Map();
        for (const list of Object.values(this._noteEntitiesByNoteId)) {
            if (!Array.isArray(list)) continue;
            for (const ent of list) {
                if (!ent || typeof ent !== 'object' || typeof ent.entity_id !== 'string') continue;
                if (ent.entity_type === 'note') continue;
                const rawName = typeof ent.name === 'string' ? ent.name : '';
                const key = _normalizeChipKey(rawName);
                if (!key || map.has(key)) continue;
                map.set(key, ent);
            }
        }
        return map;
    }

    _resolveChipEntity(label, lookup) {
        const key = _normalizeChipKey(label);
        if (!key) return null;
        const found = lookup.get(key);
        return found === undefined ? null : found;
    }

    _getEntityTagIcon(entity) {
        const t = typeof entity && entity.entity_type === 'string' ? entity.entity_type : '';
        const icon = ENTITY_TYPE_ICONS[t];
        return icon === undefined ? 'folder' : icon;
    }

    _getNoteSubtypeIcon(note) {
        const sub = typeof note && note.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        if (sub.length === 0) return 'doc-detail';
        const icon = NOTE_SUBTYPE_ICONS[sub];
        return icon === undefined ? 'doc-detail' : icon;
    }

    _notePreview(note) {
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
            return this._truncate(attrs.ai_analysis_draft.note.description, 260);
        }
        const desc = typeof note.description === 'string' && note.description.trim().length > 0
            ? note.description
            : this.t('note_content.no_description');
        return this._truncate(desc, 220);
    }

    _truncate(text, maxLength) {
        const s = typeof text === 'string' ? text.trim() : '';
        if (s.length <= maxLength) return s;
        return `${s.slice(0, maxLength).trimEnd()}...`;
    }

    _formatTime(dateString) {
        const d = new Date(dateString);
        if (Number.isNaN(d.getTime())) return '';
        return _formatHHMM(d);
    }

    _openNote(note) {
        if (!note || typeof note.entity_id !== 'string' || note.entity_id.length === 0) {
            throw new Error('CRMDailyNotesPage._openNote: note.entity_id required');
        }
        this.navigate('note', { itemId: note.entity_id });
    }

    _openEntity(entity, event) {
        if (event) event.stopPropagation();
        if (!entity || typeof entity.entity_id !== 'string' || entity.entity_id.length === 0) {
            throw new Error('CRMDailyNotesPage._openEntity: entity.entity_id required');
        }
        this.navigate('entity', { itemId: entity.entity_id });
    }

    _renderSummary() {
        const tags = this._summaryEntities();
        const lookup = this._buildEntityLookupMap();
        const summaryText = this._summaryText();
        const busy = this._summaryBusy();
        return html`
            <div class="summary-header">
                <h3 class="summary-title">
                    <span class="summary-title-icon">
                        <platform-icon name="ai" size="20" colored></platform-icon>
                    </span>
                    <span class="summary-title-text">${this._summaryPanelTitle()}</span>
                </h3>
                <button
                    class="summary-refresh-btn"
                    type="button"
                    title=${this.t('daily_notes_page.summary_rebuild_tooltip')}
                    ?disabled=${busy}
                    @click=${this._onRefreshSummary}
                >
                    <platform-icon
                        class="summary-refresh-icon ${busy ? 'spinning' : ''}"
                        name="refresh"
                        size="18"
                    ></platform-icon>
                </button>
            </div>
            <div class="summary-meta">${this._summaryMetaLine()}</div>
            <p class="summary-text">${summaryText}</p>
            <div class="summary-tags">
                ${tags.map((tag, i) => {
                    const tone = SUMMARY_CHIP_TONES[i % SUMMARY_CHIP_TONES.length];
                    const resolved = this._resolveChipEntity(tag, lookup);
                    if (resolved) {
                        return html`
                            <button
                                class="summary-chip summary-chip--clickable ${tone}"
                                type="button"
                                title=${this.t('daily_notes_page.summary_entity_open')}
                                @click=${(e) => this._openEntity(resolved, e)}
                            >
                                <platform-icon name="folder" size="14"></platform-icon>${tag}
                            </button>
                        `;
                    }
                    return html`
                        <span class="summary-chip ${tone}">
                            <platform-icon name="folder" size="14"></platform-icon>${tag}
                        </span>
                    `;
                })}
            </div>
        `;
    }

    _renderNoteCard(note) {
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
        const authorId = typeof note.user_id === 'string' && note.user_id.length > 0 ? note.user_id : '';
        const updated = typeof note.updated_at === 'string' && note.updated_at.length > 0 ? note.updated_at : note.created_at;
        const time = typeof updated === 'string' && updated.length > 0 ? this._formatTime(updated) : '';
        return html`
            <article class="note-card" @click=${() => this._openNote(note)}>
                <div class="note-tags">
                    <span class="note-type-badge">
                        <platform-icon name=${this._getNoteSubtypeIcon(note)} size="14"></platform-icon>
                    </span>
                    ${related.map((entity, i) => html`
                        <button
                            class="note-tag ${ENTITY_TAG_TONES[i % ENTITY_TAG_TONES.length]}"
                            type="button"
                            @click=${(e) => this._openEntity(entity, e)}
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
                <p class="note-text">${this._notePreview(note)}</p>
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
                        ? html`<platform-user-chip user-id=${authorId} size="sm" @click=${(e) => e.stopPropagation()}></platform-user-chip>`
                        : html`<span></span>`}
                    <div class="note-footer-right">
                        <span class="published-at">${time}</span>
                        <button
                            class="analyze-btn ${isAnalyzing ? 'analyzing' : ''} ${draft ? 'has-draft' : applied ? 'has-applied' : needsAi ? 'needs-ai' : ''}"
                            type="button"
                            ?disabled=${isAnalyzing}
                            @click=${(e) => { e.stopPropagation(); this._onAnalyzeNote(note); }}
                            title=${draft ? this.t('daily_notes_page.analysis_open_draft')
                                : applied ? this.t('daily_notes_page.analysis_view_applied')
                                : this.t('daily_notes_page.analysis_run')}
                        >
                            <platform-icon name="ai" size="14" colored></platform-icon>
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
                style=${toolbarInputStyle}
                placeholder=${this.t('search.placeholder')}
                .value=${this._query}
                @input=${this._onSearchInput}
            />
            <button
                type="button"
                class="search-voice-btn ${this._voiceMode === 'search' && this._voiceState === 'recording' ? 'recording' : ''}"
                title=${this._voiceMode === 'search' && this._voiceState === 'recording'
                    ? this.t('daily_notes_page.voice_search_stop')
                    : this.t('daily_notes_page.voice_search_start')}
                ?disabled=${this._voiceState === 'processing'}
                @click=${(e) => { e.preventDefault(); this._onVoiceSearchToggle(); }}
            >
                <platform-icon
                    name=${this._voiceMode === 'search' && this._voiceState === 'recording' ? 'square' : 'microphone'}
                    size="14"
                ></platform-icon>
            </button>
            ${includeSearchModeToggle && this._query.trim().length > 0 ? html`
                <div class="search-mode-toggle">
                    ${SEARCH_MODES.map((mode) => html`
                        <button
                            type="button"
                            class="search-mode-btn ${this._searchMode === mode ? 'active' : ''}"
                            @click=${(e) => { e.preventDefault(); this._onSearchModeChange(mode); }}
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
        el.open = true;
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
                                ? html`<glass-spinner size="16"></glass-spinner>`
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
                    .value=${{ start: this._dailyNotesUi.value.range.from, end: this._dailyNotesUi.value.range.to }}
                    @change=${this._onDateRangeChange}
                ></platform-date-picker>
            </div>
        `;
    }

    render() {
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
                        .value=${{ start: this._dailyNotesUi.value.range.from, end: this._dailyNotesUi.value.range.to }}
                        @change=${this._onDateRangeChange}
                    ></platform-date-picker>
                    <button
                        class="voice-btn ${this._voiceState === 'recording' ? 'recording' : this._voiceState === 'processing' ? 'processing' : ''}"
                        type="button"
                        @click=${this._onVoiceToggle}
                        ?disabled=${this._voiceState === 'processing'}
                        title=${this.t('daily_notes_page.voice_tooltip')}
                    >
                        <platform-icon name="microphone" size="18"></platform-icon>
                    </button>
                    <button class="cta-btn" type="button" ?disabled=${this._creatingNote} @click=${this._onCreateNote}>
                        <span class="cta-btn-content">
                            ${this._creatingNote
                                ? html`<glass-spinner size="16"></glass-spinner>`
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
                            <div class="empty"><glass-spinner size="40"></glass-spinner></div>
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
                <div class="summary-overlay" @click=${(e) => { if (e.target === e.currentTarget) this._summaryOpen = false; }}>
                    <aside class="summary-panel">
                        ${this._renderSummary()}
                    </aside>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('crm-daily-notes-page', CRMDailyNotesPage);
