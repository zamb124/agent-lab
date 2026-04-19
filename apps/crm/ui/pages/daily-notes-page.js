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
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import {
    getUserMediaCompat,
    hasGetUserMediaApi,
    pickVoiceMimeType,
} from '@platform/lib/utils/voice-recording.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/glass-spinner.js';

const DAILY_NOTES_RANGE_KEY = 'crm:daily-notes-range';

const DEFAULT_RANGE_DAYS = 7;

function _formatIsoDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _today() {
    return _formatIsoDate(new Date());
}

function _defaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - (DEFAULT_RANGE_DAYS - 1));
    return { from: _formatIsoDate(from), to: _formatIsoDate(to) };
}

function _readPersistedRange() {
    if (typeof window === 'undefined' || !window.localStorage) {
        return _defaultRange();
    }
    const raw = window.localStorage.getItem(DAILY_NOTES_RANGE_KEY);
    if (!raw) {
        return _defaultRange();
    }
    let parsed = null;
    try {
        parsed = JSON.parse(raw);
    } catch {
        return _defaultRange();
    }
    if (!parsed || typeof parsed !== 'object'
        || typeof parsed.from !== 'string' || typeof parsed.to !== 'string'
        || !/^\d{4}-\d{2}-\d{2}$/.test(parsed.from)
        || !/^\d{4}-\d{2}-\d{2}$/.test(parsed.to)) {
        return _defaultRange();
    }
    return { from: parsed.from, to: parsed.to };
}

function _persistRange(range) {
    if (typeof window === 'undefined' || !window.localStorage) return;
    window.localStorage.setItem(DAILY_NOTES_RANGE_KEY, JSON.stringify(range));
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

function _initials(name) {
    if (typeof name !== 'string' || name.trim().length === 0) return '?';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
    return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
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

export class CRMDailyNotesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _query: { state: true },
        _searchMode: { state: true },
        _dateFrom: { state: true },
        _dateTo: { state: true },
        _isMobile: { state: true },
        _summaryOpen: { state: true },
        _voiceState: { state: true },
        _noteEntitiesByNoteId: { state: true },
        _searchResults: { state: true },
        _searchLoading: { state: true },
    };

    static styles = [
        PlatformPage.styles,
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

            .note-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-top: auto;
            }

            .author {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                color: var(--text-primary);
                font-size: 12px;
            }
            .author-avatar {
                width: 32px;
                height: 32px;
                border-radius: 999px;
                overflow: hidden;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-gradient);
                flex-shrink: 0;
            }
            .author-avatar img { width: 100%; height: 100%; object-fit: cover; }
            .author-avatar-fallback { color: var(--text-inverse); font-size: 12px; font-weight: 600; }

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
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }

            .summary-fab { display: none; }
            .summary-overlay { display: none; }

            @media (max-width: 1279px) {
                .layout { grid-template-columns: 1fr; }
                .summary-panel { min-height: 240px; }
                .top-row { grid-template-columns: 1fr; }
            }

            @media (max-width: 767px) {
                :host { padding: var(--space-2) var(--space-3) 0; }
                .section-label, .title, .title-settings { display: none; }
                .top-row { display: flex; flex-direction: column; gap: var(--space-2); margin-bottom: var(--space-3); }
                .search-box, .cta-btn { display: none; }
                .toolbar-actions { flex-direction: row; gap: var(--space-2); }
                .date-input { flex: 1; min-width: 0; width: 100%; }
                .cards-grid { grid-template-columns: 1fr; gap: var(--space-3); }
                .summary-panel { display: none; }
                .summary-fab {
                    display: flex;
                    position: fixed;
                    bottom: calc(var(--space-5) + env(safe-area-inset-bottom, 0px));
                    right: var(--space-4);
                    width: 52px; height: 52px;
                    border-radius: 50%;
                    border: none;
                    background: var(--accent-gradient);
                    color: var(--text-inverse);
                    align-items: center; justify-content: center;
                    cursor: pointer;
                    z-index: 1200;
                    box-shadow: 0 4px 16px rgba(153, 166, 249, 0.4);
                }
                .summary-overlay {
                    position: fixed; inset: 0;
                    background: rgba(15, 23, 42, 0.55);
                    backdrop-filter: blur(6px);
                    z-index: 1300;
                    display: flex;
                    align-items: flex-end;
                    justify-content: center;
                    padding: var(--space-3);
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
        const range = _readPersistedRange();
        this._dateFrom = range.from;
        this._dateTo = range.to;
        this._query = '';
        this._searchMode = 'hybrid';
        this._summaryOpen = false;
        this._voiceState = 'idle';
        this._voiceMode = 'note';
        this._noteEntitiesByNoteId = {};
        this._searchResults = [];
        this._searchLoading = false;
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

        this._authSel = this.select((s) => s.auth.user);
        this._namespaceSelectionSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return 'all';
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const selection = map[cid];
            if (selection === 'all' || selection === undefined) return 'all';
            return selection;
        });

        this._mql = null;
        this._mqlListener = null;
        this._debounceTimer = null;
        this._mediaRecorder = null;
        this._audioChunks = [];
        this._lastSearchRequestId = null;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._mqlListener = (e) => { this._isMobile = e.matches; };
            this._mql.addEventListener('change', this._mqlListener);
            this._isMobile = this._mql.matches;
        }

        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._reloadNotes();
            this._reloadSummary();
        });
        this.useEvent('crm/note/updated', (event) => this._onNoteWsUpdate(event.payload));
        this.useEvent('crm/daily_summary/updated', (event) => this._onSummaryWsUpdate(event.payload));

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

        this.useEvent('crm/notes_list/loaded', (event) => {
            const items = event.payload && Array.isArray(event.payload.items) ? event.payload.items : [];
            if (this._query.trim().length === 0) {
                this._loadCardsForVisibleNotes(items);
            }
        });

        this._reloadNotes();
        this._reloadSummary();
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
        super.disconnectedCallback();
    }

    _currentNamespace() {
        const selection = this._namespaceSelectionSel.value;
        return selection === 'all' ? null : selection;
    }

    _isPeriod() { return this._dateFrom !== this._dateTo; }

    _reloadNotes() {
        const filters = {
            date_from: this._dateFrom,
            date_to: this._dateTo,
        };
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) filters.namespace = ns;
        this._noteEntitiesByNoteId = {};
        this._notes.load(filters);
    }

    _reloadSummary(options) {
        const force_rebuild = options && options.force_rebuild === true;
        const ns = this._currentNamespace();
        const payload = this._isPeriod()
            ? { date_from: this._dateFrom, date_to: this._dateTo, namespace: ns, force_rebuild }
            : { date: this._dateFrom, namespace: ns, force_rebuild };
        if (this._isPeriod()) {
            this._periodSummary.run(payload);
        } else {
            this._dailySummary.run(payload);
        }
    }

    _onSummaryWsUpdate(payload) {
        if (!payload || typeof payload !== 'object') return;
        const ns = this._currentNamespace();
        const payloadNs = payload.namespace === null || payload.namespace === undefined
            ? null
            : (typeof payload.namespace === 'string' && payload.namespace.length > 0 ? payload.namespace : null);
        if (ns !== payloadNs) return;
        const st = payload.summary_state;
        if (!st || typeof st !== 'object') return;
        const isPeriod = st.period === true;
        if (isPeriod) {
            if (!this._isPeriod()) return;
            if (st.date_to !== this._dateTo || st.date_from < this._dateFrom) return;
            this._periodSummary.applyWsPatch({
                summary: typeof st.summary === 'string' ? st.summary : '',
                entities: Array.isArray(st.entities) ? st.entities : [],
                revalidating: false,
                generated_at: typeof st.generated_at === 'string' ? st.generated_at : new Date().toISOString(),
            });
            return;
        }
        if (this._isPeriod()) return;
        if (payload.date !== this._dateFrom) return;
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
        if (payload.note_date < this._dateFrom || payload.note_date > this._dateTo) return;
        const next = { ...this._noteEntitiesByNoteId };
        delete next[payload.note_id.trim()];
        this._noteEntitiesByNoteId = next;
        this._reloadNotes();
        this._reloadSummary();
    }

    _onSearchInput(event) {
        this._query = event.target.value;
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        if (this._query.trim().length === 0) {
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
            const fallback = _defaultRange();
            this._dateFrom = fallback.from;
            this._dateTo = fallback.to;
        } else {
            this._dateFrom = v.start;
            this._dateTo = v.end;
        }
        _persistRange({ from: this._dateFrom, to: this._dateTo });
        this._reloadNotes();
        this._reloadSummary();
    }

    _onCreateNote() {
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
        const ns = this._currentNamespace();
        const payload = { note_id: note.entity_id };
        if (typeof ns === 'string' && ns.length > 0) payload.namespace = ns;
        this._analyze.run(payload);
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
        return this._analyze.busy
            && this._analyze.lastResult
            && this._analyze.lastResult.note_id === note.entity_id;
    }

    _filteredNotes() {
        if (this._query.trim().length > 0) return this._searchResults;
        return this._notes.items;
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
            return this.t('daily_notes_page.summary_panel_title_period', { from: this._dateFrom, to: this._dateTo });
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

    _getAuthorName(note) {
        const attrs = note && note.attributes;
        if (attrs && typeof attrs.author_name === 'string' && attrs.author_name.trim().length > 0) {
            return attrs.author_name;
        }
        const user = this._authSel.value;
        if (user && note.user_id === user.user_id && typeof user.name === 'string' && user.name.trim().length > 0) {
            return user.name;
        }
        return this.t('entity_card.requester_fallback');
    }

    _getAuthorAvatar(note) {
        const attrs = note && note.attributes;
        if (attrs) {
            if (typeof attrs.author_avatar_url === 'string' && attrs.author_avatar_url.trim().length > 0) {
                return attrs.author_avatar_url;
            }
            if (typeof attrs.avatar_url === 'string' && attrs.avatar_url.trim().length > 0) {
                return attrs.avatar_url;
            }
        }
        const user = this._authSel.value;
        if (user && note.user_id === user.user_id && typeof user.avatar_url === 'string' && user.avatar_url.trim().length > 0) {
            return user.avatar_url;
        }
        return '';
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
        const draft = this._hasAnalysisDraft(note);
        const applied = this._hasAnalysisApplied(note);
        const needsAi = this._noteNeedsAi(note);
        const author = this._getAuthorName(note);
        const avatar = this._getAuthorAvatar(note);
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
                <div class="note-footer">
                    <span class="author">
                        <span class="author-avatar">
                            ${avatar.length > 0
                                ? html`<img src=${avatar} alt=${author} />`
                                : html`<span class="author-avatar-fallback">${_initials(author)}</span>`}
                        </span>
                        ${author}
                    </span>
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

    render() {
        const filteredNotes = this._filteredNotes();
        const loading = this._notes.loading || this._searchLoading;
        return html`
            <div class="section-label">${this.t('daily_notes_page.section_title')}</div>
            <div class="top-row">
                <h1 class="title">
                    ${this.t('daily_notes_page.section_title')}
                    <button class="title-settings" type="button" @click=${() => this.navigate('settings')}>
                        <platform-icon name="settings" size="18"></platform-icon>
                    </button>
                </h1>
                <label class="search-box">
                    <platform-icon name="search" size="14"></platform-icon>
                    <input
                        class="search-input"
                        type="text"
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
                    ${this._query.trim().length > 0 ? html`
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
                </label>
                <div class="toolbar-actions">
                    <platform-date-picker
                        class="date-input"
                        labeled
                        selection="range"
                        .value=${{ start: this._dateFrom, end: this._dateTo }}
                        @date-change=${this._onDateRangeChange}
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
                    <button class="cta-btn" type="button" @click=${this._onCreateNote}>
                        ${this.t('daily_notes_page.add_note')}
                    </button>
                </div>
            </div>

            <div class="layout">
                <section class="main-column">
                    <div class="cards-scroll">
                        ${loading && filteredNotes.length === 0 ? html`
                            <div class="empty"><glass-spinner size="40"></glass-spinner></div>
                        ` : filteredNotes.length === 0 ? html`
                            <div class="empty">${this.t('daily_notes_page.empty_period')}</div>
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

            ${this._isMobile ? html`
                <button
                    class="summary-fab"
                    type="button"
                    @click=${() => { this._summaryOpen = true; }}
                    title=${this.t('daily_notes_page.summary_fab_open')}
                >
                    <platform-icon name="ai" size="24" colored></platform-icon>
                </button>
            ` : ''}

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
