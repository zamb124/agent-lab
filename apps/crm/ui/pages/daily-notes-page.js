import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import { getUserMediaCompat, hasGetUserMediaApi, pickVoiceMimeType } from '@platform/lib/utils/voice-recording.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/glass-spinner.js';
import '../modals/entity-modal.js';
import '../modals/note-view-modal.js';
import '../modals/ai-analysis-modal.js';

export class DailyNotesPage extends PlatformElement {
    static properties = {
        _notes: { state: true },
        _query: { state: true },
        _dateFrom: { state: true },
        _dateTo: { state: true },
        _currentNamespace: { state: true },
        _noteEntitiesByNoteId: { state: true },
        _currentUser: { state: true },
        _summaryText: { state: true },
        _summaryEntities: { state: true },
        _summaryGeneratedAt: { state: true },
        _loadingSummary: { state: true },
        _summaryRevalidating: { state: true },
        _isMobile: { state: true },
        _summaryOpen: { state: true },
        _notesLeavingIds: { state: true },
        _namespaceHasAnyEntity: { state: true },
        _namespaceProbeValid: { state: true },
        _analyzingNoteId: { state: true },
        _voiceState: { state: true },
        _searchMode: { state: true },
        _searchResults: { state: true },
        _searchLoading: { state: true },
        _debounceTimer: { state: true },
    };

    static styles = [
        PlatformElement.styles,
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

            .main-column.busy .cards-scroll {
                filter: saturate(0.92);
                opacity: 0.6;
                pointer-events: none;
                transition: filter 0.2s ease, opacity 0.2s ease;
            }

            .list-overlay {
                position: absolute;
                inset: 0;
                z-index: 6;
                display: flex;
                align-items: center;
                justify-content: center;
                pointer-events: none;
                animation: list-overlay-in 0.2s ease;
            }

            @keyframes list-overlay-in {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            .page-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
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

            .date-input {
                min-width: 180px;
                --platform-date-picker-labeled-bg: var(--crm-surface-muted);
                --platform-date-picker-labeled-border: transparent;
                --platform-date-picker-labeled-height: 44px;
                --platform-date-picker-labeled-padding: 0 var(--space-3);
                --platform-date-picker-label-size: 11px;
                --platform-date-picker-value-size: 16px;
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

            .cta-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
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
            .voice-btn:hover {
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
            }
            .voice-btn.recording {
                background: var(--platform-danger-bg, #fef2f2);
                border-color: var(--platform-danger, #ef4444);
                color: var(--platform-danger, #ef4444);
                animation: voice-pulse 1.5s ease-in-out infinite;
            }
            .voice-btn.processing {
                opacity: 0.6;
                cursor: wait;
            }
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
                max-width: 100%;
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
                max-width: 100%;
                box-sizing: border-box;
                overflow: hidden;
                cursor: pointer;
                opacity: 1;
                transform: none;
                transition:
                    border-color var(--duration-fast),
                    background var(--duration-fast),
                    opacity 0.22s ease,
                    transform 0.22s ease;
            }

            .note-card.note-card-leaving {
                opacity: 0;
                transform: translateY(-10px) scale(0.98);
                pointer-events: none;
            }

            .note-card:hover {
                border-color: var(--crm-stroke-strong);
                background: var(--crm-surface-elevated);
            }

            .note-tags-row {
                position: relative;
                min-height: 24px;
                min-width: 0;
                max-width: 100%;
            }

            .note-tags-row::after {
                content: '';
                position: absolute;
                top: 0;
                right: 0;
                width: 56px;
                height: 24px;
                background: linear-gradient(90deg, rgba(0, 0, 0, 0) 0%, var(--crm-surface) 42%);
                pointer-events: none;
            }

            .note-tags {
                display: flex;
                flex-wrap: nowrap;
                gap: 12px;
                min-height: 24px;
                overflow-x: auto;
                overflow-y: hidden;
                padding-right: 52px;
                scrollbar-width: none;
                -ms-overflow-style: none;
            }

            .note-tags::-webkit-scrollbar {
                display: none;
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

            .note-tag:hover {
                filter: brightness(0.96);
            }

            .note-tag.primary {
                background: #99A6F9;
            }

            .note-tag.secondary {
                background: #FAD17A;
            }

            .note-tag.accent {
                background: #FF885C;
            }

            .note-title {
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                min-width: 0;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .note-text {
                margin: 0;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
                min-width: 0;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .note-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                min-height: 32px;
                min-width: 0;
                margin-top: auto;
            }

            .author {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                color: var(--text-primary);
                font-size: 12px;
                line-height: 15px;
            }

            .author-avatar {
                width: 32px;
                height: 32px;
                border-radius: 999px;
                overflow: hidden;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                background: var(--accent-gradient);
            }

            .author-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .author-avatar-fallback {
                color: var(--text-inverse);
                font-size: 12px;
                font-weight: 600;
                line-height: 1;
            }

            .note-footer-right {
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }

            .published-at {
                color: var(--text-tertiary);
                font-size: 12px;
                line-height: 15px;
            }

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

            .note-type-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border-radius: 8px;
                background: var(--crm-surface-elevated, rgba(0,0,0,0.05));
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

            .analyze-btn.needs-ai {
                border-color: rgba(139, 92, 246, 0.5);
                background: rgba(139, 92, 246, 0.14);
                color: #8b5cf6;
                box-shadow: 0 0 8px rgba(139, 92, 246, 0.25);
                animation: ai-pulse 2s ease-in-out infinite;
            }

            .analyze-btn.analyzing {
                animation: analyze-btn-busy 1.2s ease-in-out infinite;
                cursor: wait;
                pointer-events: none;
            }

            .analyze-btn:disabled {
                opacity: 0.72;
                cursor: not-allowed;
            }

            @keyframes analyze-btn-busy {
                0%, 100% {
                    opacity: 1;
                }
                50% {
                    opacity: 0.55;
                }
            }

            @keyframes ai-pulse {
                0%, 100% { box-shadow: 0 0 6px rgba(139, 92, 246, 0.2); }
                50% { box-shadow: 0 0 12px rgba(139, 92, 246, 0.4); }
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
                align-items: start;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .summary-title {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                gap: var(--space-2);
                margin: 0;
                min-width: 0;
            }

            .summary-title-text {
                flex: 1 1 12rem;
                min-width: 0;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: break-word;
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
                flex-shrink: 0;
                background: var(--crm-summary-title-gradient);
                box-shadow: var(--glass-shadow-subtle);
            }

            .summary-title-icon platform-icon {
                color: var(--text-inverse);
            }

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
                flex-shrink: 0;
                margin-top: 2px;
                box-shadow: var(--glass-shadow-subtle);
                transition: opacity var(--duration-fast), transform var(--duration-fast);
            }

            .summary-refresh-btn:hover {
                opacity: 0.85;
                transform: scale(1.06);
            }

            .summary-refresh-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                transform: none;
            }

            .summary-refresh-icon.spinning {
                animation: summary-ai-rebuild-spin 0.9s linear infinite;
                transform-origin: center;
            }

            @keyframes summary-ai-rebuild-spin {
                from {
                    transform: rotate(0deg);
                }
                to {
                    transform: rotate(360deg);
                }
            }

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

            .summary-chip.cyan {
                background: var(--crm-summary-chip-cyan-bg);
            }

            .summary-chip.orange {
                background: var(--crm-summary-chip-orange-bg);
            }

            .summary-chip.rose {
                background: var(--crm-summary-chip-rose-bg);
            }

            .summary-chip--clickable {
                cursor: pointer;
                font-family: inherit;
                text-align: left;
            }

            .summary-chip--clickable:hover {
                filter: brightness(1.12);
            }

            .summary-chip--clickable:focus-visible {
                outline: 2px solid var(--accent-tertiary);
                outline-offset: 2px;
            }

            .summary-chip--clickable:disabled {
                cursor: default;
                filter: none;
            }

            .empty {
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-xl);
                min-height: 200px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }

            .empty-import {
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-6) var(--space-4);
                text-align: center;
                max-width: 440px;
                margin: 0 auto;
                box-sizing: border-box;
            }

            .empty-import-text {
                color: var(--text-secondary);
                font-size: var(--text-base);
                line-height: 1.5;
                margin: 0;
            }

            .import-wizard-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                min-height: 40px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-sm);
                font-weight: 500;
                padding: 0 var(--space-5);
                cursor: pointer;
                font-family: inherit;
                transition: background var(--duration-fast);
            }

            .import-wizard-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            .import-wizard-btn:focus-visible {
                outline: 2px solid var(--accent-tertiary);
                outline-offset: 2px;
            }

            .summary-fab {
                display: none;
            }

            .summary-overlay {
                display: none;
            }

            @media (max-width: 1279px) {
                .layout {
                    grid-template-columns: 1fr;
                }
                .summary-panel {
                    min-height: 240px;
                    margin-top: 0;
                }
                .top-row {
                    grid-template-columns: 1fr;
                    align-items: stretch;
                }
                .summary-title-text {
                    font-size: var(--text-lg);
                }

                .summary-title-icon {
                    width: 32px;
                    height: 32px;
                }
                .summary-text {
                    font-size: var(--text-lg);
                }
                .toolbar-actions {
                    margin-left: 0;
                    justify-content: flex-start;
                }
                .date-input {
                    min-width: 0;
                    width: 100%;
                }
            }

            @media (max-width: 767px) {
                :host {
                    padding: var(--space-2) var(--space-3) 0;
                }

                .section-label {
                    display: none;
                }

                .title {
                    display: none;
                }

                .top-row {
                    display: flex;
                    flex-direction: column;
                    gap: var(--space-2);
                    margin-bottom: var(--space-3);
                }

                .title-settings {
                    display: none;
                }

                .search-box {
                    display: none;
                }

                .cta-btn {
                    display: none;
                }

                .toolbar-actions {
                    flex-direction: row;
                    gap: var(--space-2);
                }

                .date-input {
                    flex: 1;
                    min-width: 0;
                    width: 100%;
                }

                .cards-grid {
                    grid-template-columns: 1fr;
                    gap: var(--space-3);
                }

                .note-card {
                    min-height: 160px;
                    padding: 16px;
                }

                .summary-panel {
                    display: none;
                }

                .summary-fab {
                    display: flex;
                    position: fixed;
                    bottom: calc(var(--space-5) + env(safe-area-inset-bottom, 0px));
                    right: var(--space-4);
                    width: 52px;
                    height: 52px;
                    border-radius: 50%;
                    border: none;
                    background: var(--accent-gradient);
                    color: var(--text-inverse);
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    box-shadow: 0 4px 16px rgba(153, 166, 249, 0.4);
                    z-index: 1200;
                    transition: transform var(--duration-fast);
                }

                .summary-fab:hover {
                    transform: scale(1.08);
                }

                .summary-overlay {
                    position: fixed;
                    inset: 0;
                    background: rgba(15, 23, 42, 0.55);
                    backdrop-filter: blur(6px);
                    -webkit-backdrop-filter: blur(6px);
                    z-index: 1300;
                    display: flex;
                    align-items: flex-end;
                    justify-content: center;
                    padding: var(--space-3);
                    padding-bottom: calc(var(--space-3) + env(safe-area-inset-bottom, 0px));
                    isolation: isolate;
                }

                .summary-overlay .summary-panel {
                    display: flex;
                    position: relative;
                    z-index: 1;
                    width: 100%;
                    max-width: min(100%, 100vw - 2 * var(--space-3));
                    max-height: 70vh;
                    box-sizing: border-box;
                    background: var(--crm-surface);
                    border: 1px solid var(--crm-stroke);
                    border-radius: var(--radius-xl) var(--radius-xl) var(--radius-lg) var(--radius-lg);
                    box-shadow: var(--glass-shadow-strong, 0 12px 40px rgba(0, 0, 0, 0.25));
                    animation: summary-slide-up 0.2s ease-out;
                }

                @keyframes summary-slide-up {
                    from { transform: translateY(100%); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
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
                transition: all var(--duration-fast);
                white-space: nowrap;
            }
            .search-mode-btn:not(:last-child) {
                border-right: 1px solid var(--glass-border-subtle);
            }
            .search-mode-btn.active {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                font-weight: 500;
            }
            .search-mode-btn:hover:not(.active) {
                background: var(--glass-bg-subtle);
            }

            .card-score {
                display: flex;
                align-items: center;
                gap: 6px;
                height: 16px;
                position: relative;
                background: var(--glass-bg-subtle, rgba(255,255,255,0.06));
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 6px;
                cursor: help;
            }
            .score-bar {
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                opacity: 0.25;
                border-radius: 8px;
            }
            .score-label {
                position: relative;
                z-index: 1;
                font-size: 10px;
                font-weight: 600;
                color: var(--text-secondary);
                padding-left: 6px;
            }
            .match-type-badge {
                position: relative;
                z-index: 1;
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
        this._notes = [];
        this._query = '';
        const initialRange = CRMStore.getDailyNotesRange();
        this._dateFrom = initialRange.from;
        this._dateTo = initialRange.to;
        this._currentNamespace = null;
        this._noteEntitiesByNoteId = {};
        this._currentUser = null;
        this._summaryText = '';
        this._summaryEntities = [];
        this._summaryGeneratedAt = '';
        this._loadingSummary = false;
        this._summaryRevalidating = false;
        this._isMobile = false;
        this._summaryOpen = false;
        this._notesLeavingIds = [];
        this._namespaceHasAnyEntity = false;
        this._namespaceProbeValid = false;
        this._analyzingNoteId = null;
        this._voiceState = 'idle';
        this._searchMode = 'hybrid';
        this._searchResults = [];
        this._searchLoading = false;
        this._debounceTimer = null;
        this._mediaRecorder = null;
        this._audioChunks = [];
        this._unsubscribe = null;
        this._onPlatformNotification = this._onPlatformNotification.bind(this);
        this._onMobileSearch = this._onMobileSearch.bind(this);
        this._goToImportWizard = this._goToImportWizard.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        const range = CRMStore.getDailyNotesRange();
        this._dateFrom = range.from;
        this._dateTo = range.to;
        this._currentNamespace = CRMStore.state.namespaces.current;
        this._isMobile = CRMStore.state.ui.isMobile;
        const initialAid = CRMStore.state.ai.analyzingNoteId;
        this._analyzingNoteId = typeof initialAid === 'string' && initialAid.trim().length > 0 ? initialAid.trim() : null;
        window.addEventListener('crm-mobile-search', this._onMobileSearch);
        this._unsubscribe = CRMStore.subscribe((state) => {
            const { from, to } = CRMStore.getDailyNotesRange();
            this._dateFrom = from;
            this._dateTo = to;
            this._isMobile = state.ui.isMobile;
            const aid = state.ai.analyzingNoteId;
            const nextAnalyzingId = typeof aid === 'string' && aid.trim().length > 0 ? aid.trim() : null;
            if (nextAnalyzingId !== this._analyzingNoteId) {
                this._analyzingNoteId = nextAnalyzingId;
            }
            const previousNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
            this._currentNamespace = state.namespaces.current;
            const nextNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
            const namespaceChanged = previousNamespace !== nextNamespace;
            if (namespaceChanged) {
                this._namespaceProbeValid = false;
                this._reloadNotesForSelectedDate();
                this._loadDailySummary();
            } else {
                this._syncNotesLeavingWithStore(state);
            }
            this._loadVisibleNoteEntities();
        });
        window.addEventListener('platform-notification-received', this._onPlatformNotification);
        this._reloadNotesForSelectedDate();
        this._loadDailySummary();
        this._loadCurrentUser();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        window.removeEventListener('platform-notification-received', this._onPlatformNotification);
        window.removeEventListener('crm-mobile-search', this._onMobileSearch);
    }

    _onMobileSearch(event) {
        this._query = event.detail?.query || '';
        CRMStore.setNotesPageSearchQuery(this._query);
    }

    _getCurrentNamespaceName() {
        if (!this._currentNamespace) {
            return null;
        }
        if (typeof this._currentNamespace === 'string') {
            return this._currentNamespace;
        }
        if (typeof this._currentNamespace === 'object' && typeof this._currentNamespace.name === 'string') {
            return this._currentNamespace.name;
        }
        throw new Error('Invalid namespace in daily notes state');
    }

    async _loadDailySummary(options = {}) {
        const { forceRebuild = false, waitForWsUpdate = false } = options;
        const { from, to } = CRMStore.getDailyNotesRange();
        this._dateFrom = from;
        this._dateTo = to;
        this._loadingSummary = true;
        try {
            const crmApi = this.services.get('crmApi');
            const ns = this._getCurrentNamespaceName();
            const response = from !== to
                ? await crmApi.getPeriodSummary(from, to, {
                    forceRebuild,
                    namespace: ns,
                })
                : await crmApi.getDailySummary(from, {
                    forceRebuild,
                    namespace: ns,
                });
            this._applySummaryPayload(response);
            if (!waitForWsUpdate) {
                this._loadingSummary = false;
            }
        } catch (error) {
            this._loadingSummary = false;
            throw error;
        }
    }

    _applySummaryPayload(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error('Daily summary response must be object');
        }
        if (typeof payload.summary !== 'string') {
            throw new Error('Daily summary response.summary must be string');
        }
        const payloadEntities = payload.entities;
        if (payloadEntities !== undefined && !Array.isArray(payloadEntities)) {
            throw new Error('Daily summary response.entities must be array when present');
        }
        this._summaryText = payload.summary;
        this._summaryEntities = Array.isArray(payloadEntities)
            ? payloadEntities.filter((entityName) => typeof entityName === 'string' && entityName.trim().length > 0)
            : [];
        this._summaryRevalidating = payload.revalidating === true;

        if (typeof payload.generated_at === 'string' && payload.generated_at.trim().length > 0) {
            this._summaryGeneratedAt = this._formatSummaryGeneratedAt(new Date(payload.generated_at));
            return;
        }
        if (payload.summary.trim().length > 0) {
            this._summaryGeneratedAt = this._formatSummaryGeneratedAt(new Date());
            return;
        }
        this._summaryGeneratedAt = '';
    }

    _normalizeNamespaceName(namespace) {
        if (!namespace) {
            return 'all';
        }
        if (typeof namespace === 'string') {
            return namespace.trim() === '' ? 'all' : namespace;
        }
        throw new Error('Invalid summary notification namespace');
    }

    _onPlatformNotification(event) {
        const notification = event.detail;
        if (!notification || notification.service !== 'crm') {
            return;
        }
        if (notification.type === 'crm_daily_summary_updated') {
            const payload = notification.data;
            if (!payload || payload.event !== 'crm.daily_summary.updated') {
                return;
            }

            const selectedNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
            const payloadNamespace = this._normalizeNamespaceName(payload.namespace);
            if (payloadNamespace !== selectedNamespace) {
                return;
            }
            const st = payload.summary_state;
            if (st && st.period === true) {
                if (this._dateFrom === this._dateTo) {
                    return;
                }
                if (st.date_to !== this._dateTo || st.date_from < this._dateFrom) {
                    return;
                }
                this._loadingSummary = false;
                const genAt =
                    typeof st.generated_at === 'string' && st.generated_at.trim().length > 0
                        ? st.generated_at
                        : new Date().toISOString();
                this._applySummaryPayload({
                    summary: typeof st.summary === 'string' ? st.summary : '',
                    entities: Array.isArray(st.entities) ? st.entities : [],
                    revalidating: false,
                    generated_at: genAt,
                });
                return;
            }
            if (this._dateFrom !== this._dateTo || payload.date !== this._dateFrom) {
                return;
            }

            this._loadingSummary = false;
            this._applySummaryPayload(payload.summary_state);
            return;
        }
        if (notification.type === 'crm_note_updated') {
            void this._handleCrmNoteWsNotification(notification);
        }
    }

    async _handleCrmNoteWsNotification(notification) {
        const payload = notification.data;
        if (!payload || payload.event !== 'crm.note.updated') {
            return;
        }
        if (typeof payload.note_id !== 'string' || payload.note_id.trim().length === 0) {
            return;
        }
        const selectedNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
        const payloadNamespace = this._normalizeNamespaceName(payload.namespace);
        if (payloadNamespace !== selectedNamespace) {
            return;
        }
        if (payload.note_date == null || typeof payload.note_date !== 'string') {
            return;
        }
        if (payload.note_date < this._dateFrom || payload.note_date > this._dateTo) {
            return;
        }
        const noteId = payload.note_id.trim();
        if (payload.action === 'updated' || payload.action === 'created') {
            const nextCache = { ...this._noteEntitiesByNoteId };
            delete nextCache[noteId];
            this._noteEntitiesByNoteId = nextCache;
        }
        await this._reloadNotesForSelectedDate();
        await this._loadVisibleNoteEntities();
        void this._loadDailySummary();
        this.requestUpdate();
    }

    _formatSummaryGeneratedAt(date) {
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _formatTime(dateString) {
        const date = new Date(dateString);
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _getLimitedText(text, maxLength = 220) {
        if (typeof text !== 'string') {
            return '';
        }
        const normalized = text.trim();
        if (normalized.length <= maxLength) {
            return normalized;
        }
        return `${normalized.slice(0, maxLength).trimEnd()}...`;
    }

    _getNotePreviewText(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (attrs && typeof attrs === 'object' && typeof attrs.ai_summary === 'string' && attrs.ai_summary.trim().length > 0) {
            return this._getLimitedText(attrs.ai_summary, 260);
        }
        return this._getLimitedText(this._getTextValue(note.description, this.i18n.t('note_content.no_description')), 220);
    }

    _getTextValue(value, defaultValue) {
        if (typeof value === 'string' && value.trim().length > 0) {
            return value;
        }
        return defaultValue;
    }

    _isNoteAiAnalyzing(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const id = note.entity_id;
        if (typeof id !== 'string' || id.trim().length === 0) {
            return false;
        }
        return this._analyzingNoteId === id.trim();
    }

    _onSearchInput(event) {
        this._query = event.target.value;
        CRMStore.setNotesPageSearchQuery(this._query);
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        if (!this._query.trim()) {
            this._searchResults = [];
            this._loadVisibleNoteEntities();
            return;
        }
        this._debounceTimer = setTimeout(() => this._doSearch(), 300);
    }

    async _doSearch() {
        const crmApi = this.services.get('crmApi');
        this._searchLoading = true;
        const result = await crmApi.searchEntities(this._query.trim(), {
            entity_type: 'note',
            search_mode: this._searchMode,
            limit: 50,
        });
        this._searchResults = Array.isArray(result?.items) ? result.items : [];
        this._searchLoading = false;
    }

    _onSearchModeChange(mode) {
        this._searchMode = mode;
        if (this._query.trim()) this._doSearch();
    }

    async _onDateRangeChange(event) {
        const detail = event.detail;
        if (!detail || detail.selection !== 'range') {
            throw new Error('Expected platform-date-picker selection=range');
        }
        const v = detail.value;
        if (!v || typeof v !== 'object') {
            throw new Error('Range value must be an object');
        }
        const start = v.start;
        const end = v.end;
        if (typeof start !== 'string' || typeof end !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
            const wk = CRMStore.defaultDailyNotesRange();
            CRMStore.setDailyNotesRange({ from: wk.from, to: wk.to });
        } else {
            CRMStore.setDailyNotesRange({ from: start, to: end });
        }
        const range = CRMStore.getDailyNotesRange();
        this._dateFrom = range.from;
        this._dateTo = range.to;
        await this._reloadNotesForSelectedDate();
        await this._loadDailySummary();
        await this._loadVisibleNoteEntities();
    }

    _syncNotesLeavingWithStore(state) {
        const storeNotes = Array.isArray(state.entities.notes) ? state.entities.notes : [];
        const storeIds = new Set(storeNotes.map((n) => n.entity_id));
        const leaving = new Set(this._notesLeavingIds);
        let changed = false;
        for (const id of [...leaving]) {
            if (storeIds.has(id)) {
                leaving.delete(id);
                changed = true;
            }
        }
        for (const note of this._notes) {
            const id = note.entity_id;
            if (typeof id !== 'string' || id.trim().length === 0) {
                throw new Error('Note entity_id is required');
            }
            if (!storeIds.has(id) && !leaving.has(id)) {
                leaving.add(id);
                changed = true;
            }
        }
        if (changed) {
            this._notesLeavingIds = [...leaving];
        }
    }

    _onNoteCardLeaveTransitionEnd(noteId, event) {
        if (event.target !== event.currentTarget) {
            return;
        }
        if (event.propertyName !== 'opacity') {
            return;
        }
        this._notes = this._notes.filter((n) => n.entity_id !== noteId);
        this._notesLeavingIds = this._notesLeavingIds.filter((id) => id !== noteId);
    }

    async _reloadNotesForSelectedDate() {
        const crmApi = this.services.get('crmApi');
        this._noteEntitiesByNoteId = {};
        this._notesLeavingIds = [];
        const { from, to } = CRMStore.getDailyNotesRange();
        this._dateFrom = from;
        this._dateTo = to;
        const notes = await CRMStore.loadNotes(crmApi, {
            dateFrom: from,
            dateTo: to,
            limit: 300,
        });
        this._notes = Array.isArray(notes) ? notes : [];
        await this._loadVisibleNoteEntities();
        await this._probeNamespaceHasAnyEntity();
    }

    async _probeNamespaceHasAnyEntity() {
        const crmApi = this.services.get('crmApi');
        const raw = this._getCurrentNamespaceName();
        const namespace = typeof raw === 'string' && raw.trim().length > 0 ? raw.trim() : 'default';
        const response = await crmApi.getEntities({ namespace, limit: 1 });
        const currentRaw = this._getCurrentNamespaceName();
        const currentNs = typeof currentRaw === 'string' && currentRaw.trim().length > 0 ? currentRaw.trim() : 'default';
        if (currentNs !== namespace) {
            return;
        }
        this._namespaceHasAnyEntity = Array.isArray(response.items) && response.items.length > 0;
        this._namespaceProbeValid = true;
        this.requestUpdate();
    }

    _goToImportWizard() {
        const c = CRMStore.state.namespaces.current;
        const name = typeof c === 'string' && c.trim()
            ? c.trim()
            : (c && typeof c === 'object' && typeof c.name === 'string' && c.name.trim() ? c.name.trim() : 'default');
        CRMStore.setSettingsNamespaceSelection(name);
        CRMStore.setCurrentView('namespace_imports');
    }

    async _onCreateNote() {
        const focusDate = CRMStore.getDailyNotesFocusDate();
        const draftNote = {
            entity_id: `draft-${Date.now()}`,
            entity_type: 'note',
            entity_subtype: null,
            name: '',
            description: '',
            note_date: focusDate,
            attributes: {},
        };
        this._openNoteModal(draftNote, { editable: true, draftMode: true });
    }

    async _onVoiceToggle() {
        if (this._voiceState === 'recording') {
            this._stopVoiceRecording();
            return;
        }
        if (this._voiceState !== 'idle') return;

        const notify = this.services.get('notify');

        if (!window.isSecureContext) {
            notify.warning(this.i18n.t('voice.audio_https_only', {}, 'common'));
            return;
        }
        if (!hasGetUserMediaApi()) {
            notify.warning(this.i18n.t('voice.audio_no_recorder', {}, 'common'));
            return;
        }
        if (typeof MediaRecorder === 'undefined') {
            notify.warning(this.i18n.t('voice.audio_no_recorder', {}, 'common'));
            return;
        }

        let stream;
        try {
            stream = await getUserMediaCompat({ audio: true });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            notify.warning(msg || this.i18n.t('voice.audio_start_failed', {}, 'common'));
            return;
        }

        this._audioChunks = [];
        const mimeType = pickVoiceMimeType();
        this._mediaRecorder = mimeType
            ? new MediaRecorder(stream, { mimeType })
            : new MediaRecorder(stream);
        const resolvedMime = this._mediaRecorder.mimeType || mimeType || 'audio/mp4';

        this._mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                this._audioChunks.push(e.data);
            }
        };

        this._mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            this._voiceState = 'processing';
            const blob = new Blob(this._audioChunks, { type: resolvedMime });
            const crmApi = this.services.get('crmApi');
            try {
                const result = await crmApi.voiceInput(blob);
                this._voiceState = 'idle';
                this._mediaRecorder = null;
                this._audioChunks = [];

                if (!result.text || !result.text.trim()) {
                    notify.warning(this.i18n.t('voice_input.empty_result'));
                    return;
                }
                const focusDate = CRMStore.getDailyNotesFocusDate();
                const draftNote = {
                    entity_id: `draft-${Date.now()}`,
                    entity_type: 'note',
                    entity_subtype: null,
                    name: '',
                    description: result.text.trim(),
                    note_date: focusDate,
                    attributes: {},
                };
                this._openNoteModal(draftNote, { editable: true, draftMode: true });
            } catch (err) {
                this._voiceState = 'idle';
                this._mediaRecorder = null;
                this._audioChunks = [];
                const msg = err instanceof Error ? err.message : String(err);
                notify.error(msg || this.i18n.t('voice.audio_start_failed', {}, 'common'));
            }
        };

        this._mediaRecorder.start();
        this._voiceState = 'recording';
    }

    _stopVoiceRecording() {
        if (this._mediaRecorder && this._mediaRecorder.state === 'recording') {
            this._mediaRecorder.stop();
        }
    }

    async _onRefreshSummary() {
        await this._loadDailySummary({ forceRebuild: true, waitForWsUpdate: true });
    }

    async _onAnalyzeNote(note) {
        if (!note || typeof note.description !== 'string') {
            throw new Error('Note description is required for AI analysis');
        }
        if (this._hasNoteAnalysisDraft(note)) {
            this._openNoteAnalysisDraftModal(note);
            return;
        }
        if (this._hasNoteAnalysisApplied(note)) {
            this._openNoteModal(note);
            return;
        }
        const noteText = note.description.trim();
        if (!noteText) {
            throw new Error('Empty note cannot be analyzed');
        }
        CRMStore.setCurrentNote(note.entity_id);
        const analysisModal = document.createElement('ai-analysis-modal');
        analysisModal.loading = true;
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
        const crmApi = this.services.get('crmApi');
        try {
            const relatedEntities = this._getNoteEntities(note);
            const mentionedEntityIds = relatedEntities
                .map((entity) => entity?.entity_id)
                .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
            await CRMStore.analyzeNote(crmApi, note.entity_id, {
                mentionedEntityIds,
                extractEntityTypes: ['note', 'task', 'person', 'organization'],
                extractRelationshipTypes: ['mentions'],
                checkDuplicates: true,
            });
        } finally {
            analysisModal.loading = false;
        }
    }

    _hasNoteAnalysisDraft(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return false;
        }
        const draft = attrs.ai_analysis_draft;
        return typeof draft === 'object'
            && draft !== null
            && typeof draft.draft_version === 'number';
    }

    _hasNoteAnalysisApplied(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return false;
        }
        return typeof attrs.ai_analysis_applied_at === 'string'
            && attrs.ai_analysis_applied_at.length > 0
            && !this._hasNoteAnalysisDraft(note);
    }

    _noteNeedsAiProcessing(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return true;
        }
        if (attrs.ai_analysis_applied_at) {
            return false;
        }
        if (attrs.ai_analysis_draft && typeof attrs.ai_analysis_draft === 'object') {
            return false;
        }
        return true;
    }

    _openNoteAnalysisDraftModal(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        if (typeof note.entity_id !== 'string' || note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        CRMStore.openNoteAnalysisDraft(note.entity_id);
        const analysisModal = document.createElement('ai-analysis-modal');
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
    }

    _getFilteredNotes() {
        if (this._query.trim()) {
            return this._searchResults;
        }
        const leavingSet = new Set(this._notesLeavingIds);
        return this._notes.filter((note) => !leavingSet.has(note.entity_id));
    }

    _getSummaryChipTone(index) {
        const tones = ['blue', 'cyan', 'orange', 'rose'];
        return tones[index % tones.length];
    }

    _normalizeSummaryChipLookupKey(label) {
        if (typeof label !== 'string') {
            return null;
        }
        let s = label.trim();
        if (!s) {
            return null;
        }
        if (s.startsWith('@')) {
            s = s.slice(1).trim();
        }
        s = s.replace(/^["'([{]+|["')\]}.,;:!?]+$/g, '').trim();
        if (!s) {
            return null;
        }
        return s.toLowerCase();
    }

    _buildSummaryEntityLookupMap() {
        const map = new Map();
        const lists = Object.values(this._noteEntitiesByNoteId);
        for (let i = 0; i < lists.length; i += 1) {
            const related = lists[i];
            if (!Array.isArray(related)) {
                continue;
            }
            for (let j = 0; j < related.length; j += 1) {
                const ent = related[j];
                if (!ent || typeof ent !== 'object' || typeof ent.entity_id !== 'string' || !ent.entity_id.trim()) {
                    continue;
                }
                if (ent.entity_type === 'note') {
                    continue;
                }
                const rawName = typeof ent.name === 'string' ? ent.name : '';
                const key = this._normalizeSummaryChipLookupKey(rawName);
                if (!key || map.has(key)) {
                    continue;
                }
                map.set(key, ent);
            }
        }
        return map;
    }

    _resolveEntityForSummaryChip(displayLabel, lookupMap) {
        const key = this._normalizeSummaryChipLookupKey(displayLabel);
        if (!key) {
            return null;
        }
        return lookupMap.get(key) ?? null;
    }

    async _loadCurrentUser() {
        const user = await this.auth.get('/api/auth/me');
        if (!user || typeof user !== 'object') {
            throw new Error('Current user payload must be object');
        }
        this._currentUser = user;
    }

    async _loadVisibleNoteEntities() {
        const filteredNotes = this._getFilteredNotes();
        const noteIds = filteredNotes
            .map((note) => note.entity_id)
            .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
        const unresolvedNoteIds = noteIds.filter(
            (entityId) => !Object.prototype.hasOwnProperty.call(this._noteEntitiesByNoteId, entityId),
        );
        if (unresolvedNoteIds.length === 0) {
            return;
        }

        const crmApi = this.services.get('crmApi');
        const cardsMap = await crmApi.getEntityCardsBulk(unresolvedNoteIds);

        const next = { ...this._noteEntitiesByNoteId };
        for (const entityId of unresolvedNoteIds) {
            const card = cardsMap[entityId];
            if (!card) {
                next[entityId] = [];
                continue;
            }
            if (!Array.isArray(card.related_entities)) {
                throw new Error('Entity card must contain related_entities array');
            }
            next[entityId] = card.related_entities;
        }
        this._noteEntitiesByNoteId = next;
    }

    _getNoteEntities(note) {
        if (!note || typeof note.entity_id !== 'string') {
            throw new Error('Note entity_id is required');
        }
        const relatedEntities = this._noteEntitiesByNoteId[note.entity_id];
        if (!Array.isArray(relatedEntities)) {
            return [];
        }
        return relatedEntities;
    }

    _getEntityTagTone(index) {
        const tones = ['primary', 'secondary', 'accent'];
        return tones[index % tones.length];
    }

    _getEntityTagIcon(entity) {
        const entityType = typeof entity?.entity_type === 'string' ? entity.entity_type : '';
        const iconMap = {
            'member': 'user-shield',
            'contact': 'user',
            'company': 'building',
            'namespace': 'layers',
            'organization': 'database',
        };
        return iconMap[entityType] || 'folder';
    }

    _getNoteSubtypeLabel(note) {
        const subtype = typeof note?.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        if (subtype.length === 0) {
            return '';
        }
        return subtype
            .split('_')
            .filter((part) => part.length > 0)
            .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
            .join(' ');
    }

    _getNoteSubtypeIcon(note) {
        const subtype = typeof note?.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        const iconMap = {
            call: 'phone-call',
            meeting: 'calendar',
            email: 'mail',
            task: 'tasks',
            note: 'doc-detail',
        };
        if (subtype.length > 0) {
            return iconMap[subtype] ?? 'doc-detail';
        }
        return 'doc-detail';
    }

    _getAuthorName(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (attrs && typeof attrs === 'object' && typeof attrs.author_name === 'string' && attrs.author_name.trim().length > 0) {
            return attrs.author_name;
        }
        if (
            this._currentUser
            && typeof this._currentUser === 'object'
            && note.user_id === this._currentUser.user_id
            && typeof this._currentUser.name === 'string'
            && this._currentUser.name.trim().length > 0
        ) {
            return this._currentUser.name;
        }
        return this.i18n.t('entity_card.requester_fallback');
    }

    _getAuthorAvatarUrl(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.author_avatar_url === 'string' && attrs.author_avatar_url.trim().length > 0) {
            return attrs.author_avatar_url;
        }
        if (typeof attrs.avatar_url === 'string' && attrs.avatar_url.trim().length > 0) {
            return attrs.avatar_url;
        }
        if (
            this._currentUser
            && typeof this._currentUser === 'object'
            && note.user_id === this._currentUser.user_id
            && typeof this._currentUser.avatar_url === 'string'
            && this._currentUser.avatar_url.trim().length > 0
        ) {
            return this._currentUser.avatar_url;
        }
        return '';
    }

    _getInitials(name) {
        if (typeof name !== 'string' || name.trim().length === 0) {
            return '?';
        }
        const parts = name.trim().split(/\s+/);
        if (parts.length === 1) {
            return parts[0].slice(0, 1).toUpperCase();
        }
        return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
    }

    _openEntityModal(entity, event = null) {
        event?.stopPropagation();
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity object is required');
        }
        if (typeof entity.entity_id !== 'string' || entity.entity_id.trim().length === 0) {
            throw new Error('Entity ID is required');
        }

        CRMStore.setCurrentEntity(entity.entity_id);
        const modal = document.createElement('entity-modal');
        modal.entityId = entity.entity_id;
        modal.entity = entity;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openNoteModal(note, options = {}) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        if (typeof note.entity_id !== 'string' || note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        const modal = document.createElement('note-view-modal');
        modal.note = note;
        modal.startInEditMode = options.editable === true;
        modal.draftMode = options.draftMode === true;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('note-created', async () => {
            await this._reloadNotesForSelectedDate();
            await this._loadVisibleNoteEntities();
            await this._loadDailySummary();
        });
    }

    _summaryPanelTitle() {
        if (this._dateFrom !== this._dateTo) {
            return this.i18n.t('daily_notes_page.summary_panel_title_period', {
                from: this._dateFrom,
                to: this._dateTo,
            });
        }
        return this.i18n.t('daily_notes_page.summary_panel_title_daily');
    }

    _summaryMetaLine() {
        if (this._loadingSummary) {
            return this.i18n.t('daily_notes_page.summary_generating');
        }
        if (this._summaryRevalidating) {
            return this._summaryGeneratedAt
                ? this.i18n.t('daily_notes_page.summary_revalidating_last', { time: this._summaryGeneratedAt })
                : this.i18n.t('daily_notes_page.summary_revalidating');
        }
        return this._summaryGeneratedAt
            ? this.i18n.t('daily_notes_page.summary_generated_at', { time: this._summaryGeneratedAt })
            : this.i18n.t('daily_notes_page.summary_none');
    }

    _renderSummaryContent(summaryTags) {
        const summaryEntityLookup = this._buildSummaryEntityLookupMap();
        return html`
            <div class="summary-header">
                <h3 class="summary-title">
                    <span class="summary-title-icon">
                        <platform-icon name="ai" size="20" colored></platform-icon>
                    </span>
                    <span class="summary-title-text">${this._summaryPanelTitle()}</span>
                </h3>
                <button class="summary-refresh-btn" type="button" title=${this.i18n.t('daily_notes_page.summary_rebuild_tooltip')} @click=${this._onRefreshSummary} ?disabled=${this._loadingSummary}>
                    <platform-icon
                        class=${this._loadingSummary ? 'summary-refresh-icon spinning' : 'summary-refresh-icon'}
                        name="refresh"
                        size="18"
                    ></platform-icon>
                </button>
            </div>
            <div class="summary-meta">
                ${this._summaryMetaLine()}
            </div>
            <p class="summary-text">${this._summaryText}</p>
            <div class="summary-tags">
                ${summaryTags.map((tag, index) => {
                    const tone = this._getSummaryChipTone(index);
                    const resolved = this._resolveEntityForSummaryChip(tag, summaryEntityLookup);
                    if (resolved) {
                        return html`
                            <button
                                type="button"
                                class="summary-chip summary-chip--clickable ${tone}"
                                title=${this.i18n.t('daily_notes_page.summary_entity_open')}
                                @click=${(event) => this._openEntityModal(resolved, event)}
                            >
                                <platform-icon name="folder" size="14"></platform-icon>
                                ${tag}
                            </button>
                        `;
                    }
                    return html`
                        <span class="summary-chip ${tone}">
                            <platform-icon name="folder" size="14"></platform-icon>
                            ${tag}
                        </span>
                    `;
                })}
            </div>
        `;
    }

    render() {
        const filteredNotes = this._getFilteredNotes();
        const summaryTags = this._summaryEntities;

        return html`
            <div class="section-label">${this.i18n.t('daily_notes_page.section_title')}</div>
            <div class="top-row">
                <div class="title">
                    ${this.i18n.t('daily_notes_page.section_title')}
                    <button class="title-settings" type="button" title=${this.i18n.t('daily_notes_page.settings_tooltip')}>
                        <platform-icon name="settings" size="18"></platform-icon>
                    </button>
                </div>
                <label class="search-box">
                    <platform-icon name="search" size="14"></platform-icon>
                    <input
                        class="search-input"
                        type="text"
                        placeholder=${this.i18n.t('search.placeholder')}
                        .value=${this._query}
                        @input=${this._onSearchInput}
                    />
                    ${this._query.trim() ? html`
                        <div class="search-mode-toggle" @click=${(e) => e.preventDefault()}>
                            ${['text', 'semantic', 'hybrid'].map(mode => html`
                                <button
                                    type="button"
                                    class="search-mode-btn ${this._searchMode === mode ? 'active' : ''}"
                                    @click=${(e) => { e.preventDefault(); this._onSearchModeChange(mode); }}
                                >${this.i18n.t(`entities.search_modes.${mode}`)}</button>
                            `)}
                        </div>
                    ` : ''}
                </label>
                <div class="toolbar-actions">
                    <platform-date-picker
                        class="date-input"
                        mode="date"
                        selection="range"
                        value-format="iso"
                        label=${this.i18n.t('daily_notes_page.period_label')}
                        .value=${{ start: this._dateFrom, end: this._dateTo }}
                        @change=${this._onDateRangeChange}
                    ></platform-date-picker>
                    <button
                        class="voice-btn ${this._voiceState}"
                        type="button"
                        title=${this.i18n.t(`voice_input.btn_${this._voiceState}`)}
                        ?disabled=${this._voiceState === 'processing'}
                        @click=${this._onVoiceToggle}
                    >
                        <platform-icon name=${this._voiceState === 'recording' ? 'stop' : 'microphone'} size="18"></platform-icon>
                    </button>
                    <button class="cta-btn" type="button" @click=${this._onCreateNote}>${this.i18n.t('daily_notes_page.add_note')}</button>
                </div>
            </div>

            <div class="layout">
                <section class="main-column ${this._searchLoading ? 'busy' : ''}">
                    ${this._searchLoading ? html`
                        <div class="list-overlay">
                            <glass-spinner size="lg"></glass-spinner>
                        </div>
                    ` : ''}
                    <div class="cards-scroll">
                        ${filteredNotes.length === 0 ? html`
                            <div class="empty ${this._namespaceProbeValid && !this._namespaceHasAnyEntity ? 'empty-import' : ''}">
                                ${this._namespaceProbeValid && !this._namespaceHasAnyEntity ? html`
                                    <p class="empty-import-text">${this.i18n.t('import_wizard_cta.empty_notes_hint')}</p>
                                    <button class="import-wizard-btn" type="button" @click=${this._goToImportWizard}>
                                        <platform-icon name="import" size="18"></platform-icon>
                                        ${this.i18n.t('import_wizard_cta.open_wizard')}
                                    </button>
                                ` : html`
                                    <span>${this.i18n.t('daily_notes_page.empty_period')}</span>
                                `}
                            </div>
                        ` : html`
                            <div class="cards-grid">
                                ${filteredNotes.map((note) => html`
                                    <article
                                        class="note-card ${this._notesLeavingIds.includes(note.entity_id) ? 'note-card-leaving' : ''}"
                                        @click=${() => this._openNoteModal(note)}
                                        @transitionend=${(e) => this._onNoteCardLeaveTransitionEnd(note.entity_id, e)}
                                    >
                                        ${(() => {
                                            const relatedEntities = this._getNoteEntities(note);
                                            return html`
                                                <div class="note-tags-row">
                                                    <div class="note-tags">
                                                        <span
                                                            class="note-type-badge"
                                                            title=${this._getNoteSubtypeLabel(note) || this.i18n.t('daily_notes_page.note_type_default')}
                                                        >
                                                            <platform-icon name=${this._getNoteSubtypeIcon(note)} size="14"></platform-icon>
                                                        </span>
                                                        ${relatedEntities.map((entity, index) => html`
                                                            <button
                                                                class="note-tag ${this._getEntityTagTone(index)}"
                                                                type="button"
                                                                title=${this.i18n.t('ai_analysis_modal.open_entity_title')}
                                                                @click=${(event) => this._openEntityModal(entity, event)}
                                                            >
                                                                <platform-icon name=${this._getEntityTagIcon(entity)} size="12"></platform-icon>
                                                                ${this._getTextValue(entity.name, 'Entity')}
                                                            </button>
                                                        `)}
                                                    </div>
                                                </div>
                                            `;
                                        })()}
                                        ${note.score != null ? html`
                                            <div class="card-score" title="${(() => {
                                                const modeTitle = {
                                                    semantic: this.i18n.t('search.score_title_semantic'),
                                                    text: this.i18n.t('search.score_title_text'),
                                                    hybrid: this.i18n.t('search.score_title_hybrid'),
                                                }[this._searchMode] ?? '';
                                                if (this._searchMode === 'hybrid' && note.match_type) {
                                                    const foundBy = {
                                                        text: this.i18n.t('search.found_by_text'),
                                                        semantic: this.i18n.t('search.found_by_semantic'),
                                                        hybrid: this.i18n.t('search.found_by_both'),
                                                    }[note.match_type] ?? '';
                                                    return foundBy ? `${modeTitle}\n${foundBy}` : modeTitle;
                                                }
                                                return modeTitle;
                                            })()}">
                                                <div class="score-bar" style="width: ${Math.round(note.score * 100)}%"></div>
                                                <span class="score-label">${(note.score * 100).toFixed(0)}%</span>
                                                <span class="match-type-badge">${this._searchMode}</span>
                                            </div>
                                        ` : ''}
                                        <h3 class="note-title">${note.name}</h3>
                                        <p class="note-text">${this._getNotePreviewText(note)}</p>
                                        <div class="note-footer">
                                            ${(() => {
                                                const authorName = this._getAuthorName(note);
                                                const authorAvatarUrl = this._getAuthorAvatarUrl(note);
                                                return html`
                                                    <span class="author">
                                                        <span class="author-avatar">
                                                            ${authorAvatarUrl
                                                                ? html`<img src=${authorAvatarUrl} alt=${authorName} />`
                                                                : html`<span class="author-avatar-fallback">${this._getInitials(authorName)}</span>`}
                                                        </span>
                                                        ${authorName}
                                                    </span>
                                                `;
                                            })()}
                                            <div class="note-footer-right">
                                                <span class="published-at">${this.i18n.t('daily_notes_page.published_at', { time: this._formatTime(this._getTextValue(note.updated_at, this._getTextValue(note.created_at, new Date().toISOString()))) })}</span>
                                                <button
                                                    class="analyze-btn ${this._isNoteAiAnalyzing(note) ? 'analyzing' : ''} ${this._hasNoteAnalysisDraft(note) ? 'has-draft' : this._hasNoteAnalysisApplied(note) ? 'has-applied' : this._noteNeedsAiProcessing(note) ? 'needs-ai' : ''}"
                                                    type="button"
                                                    ?disabled=${this._isNoteAiAnalyzing(note)}
                                                    @click=${(event) => { event.stopPropagation(); this._onAnalyzeNote(note); }}
                                                    title=${this._isNoteAiAnalyzing(note)
                                                        ? this.i18n.t('daily_notes_page.analysis_in_progress')
                                                        : (this._hasNoteAnalysisDraft(note)
                                                            ? this.i18n.t('daily_notes_page.analysis_open_draft')
                                                            : (this._hasNoteAnalysisApplied(note)
                                                                ? this.i18n.t('daily_notes_page.analysis_view_applied')
                                                                : this.i18n.t('daily_notes_page.analysis_run')))}
                                                >
                                                    <platform-icon name="ai" size="14" colored></platform-icon>
                                                </button>
                                            </div>
                                        </div>
                                    </article>
                                `)}
                            </div>
                        `}
                    </div>
                </section>

                <aside class="summary-panel">
                    ${this._renderSummaryContent(summaryTags)}
                </aside>
            </div>

            ${this._isMobile ? html`
                <button class="summary-fab" type="button" @click=${() => { this._summaryOpen = true; }} title=${this.i18n.t('daily_notes_page.summary_fab_open')}>
                    <platform-icon name="ai" size="24" colored></platform-icon>
                </button>
            ` : ''}

            ${this._isMobile && this._summaryOpen ? html`
                <div class="summary-overlay" @click=${(e) => { if (e.target === e.currentTarget) this._summaryOpen = false; }}>
                    <aside class="summary-panel">
                        ${this._renderSummaryContent(summaryTags)}
                    </aside>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('daily-notes-page', DailyNotesPage);
