import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { flowsChatMarkdownToHtml } from '@platform/lib/flows-chat/markdown.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import {
    fileListToPublicSearchFiles,
    filesToPublicSearchA2aParts,
    takePendingPublicSearchFiles,
} from '../utils/public-search-files.js';
import '@platform/lib/components/platform-icon.js';

const SEARCH_MODES = Object.freeze([
    { key: 'quick', icon: 'search', label: 'search_page.mode_quick' },
    { key: 'deep', icon: 'layers', label: 'search_page.mode_deep' },
    { key: 'research', icon: 'sparkle', label: 'search_page.mode_research' },
]);

export class PublicSearchPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        _query: { state: true },
        _mode: { state: true },
        _selectedFiles: { state: true },
        _preparingFiles: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: var(--app-vh, 100vh);
                color: #f5f5f3;
                background:
                    linear-gradient(180deg, rgba(12, 12, 12, 0.62) 0%, #0b0b0b 46%, #111 100%),
                    url('/static/frontend/assets/images/main_img.png') center 18% / min(980px, 74vw) auto no-repeat,
                    #0f0f0f;
                font-family: 'Fira Sans', system-ui, sans-serif;
            }

            .page {
                min-height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
            }

            .topbar {
                height: 72px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 clamp(18px, 4vw, 56px);
                box-sizing: border-box;
                background: rgba(15, 15, 15, 0.72);
                backdrop-filter: blur(22px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
                position: sticky;
                top: 0;
                z-index: 20;
            }

            .brand,
            .back-link {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                border: 0;
                background: transparent;
                color: #f5f5f3;
                font: inherit;
                cursor: pointer;
                padding: 0;
            }

            .brand-mark {
                width: 34px;
                height: 34px;
                border-radius: 50%;
                display: grid;
                place-items: center;
                background: #5768fe;
                color: #fff;
                font-weight: 700;
                letter-spacing: 0;
            }

            .brand-name {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                line-height: 1;
                letter-spacing: 0;
            }

            .back-link {
                min-height: 40px;
                padding: 0 14px;
                border-radius: 999px;
                color: rgba(245, 245, 243, 0.74);
                background: rgba(255, 255, 255, 0.06);
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
            }

            .back-link:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #fff;
                transform: translateY(-1px);
            }

            .search-head {
                padding: clamp(34px, 7vw, 86px) clamp(18px, 4vw, 56px) 22px;
                display: grid;
                justify-items: center;
                gap: 18px;
            }

            .search-title {
                margin: 0;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 500;
                font-size: clamp(42px, 9vw, 112px);
                line-height: 0.96;
                letter-spacing: 0;
                text-align: center;
                color: rgba(245, 245, 243, 0.95);
            }

            .search-shell {
                width: min(920px, calc(100vw - 32px));
                border-radius: 30px;
                background: rgba(31, 31, 31, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.10);
                box-shadow: 0 26px 80px rgba(0, 0, 0, 0.42);
                backdrop-filter: blur(28px);
                padding: 10px;
                box-sizing: border-box;
                animation: searchEnter 340ms ease both;
            }

            .search-line {
                min-height: 58px;
                display: grid;
                grid-template-columns: 44px minmax(0, 1fr) 44px;
                align-items: center;
                gap: 4px;
            }

            .search-icon {
                display: grid;
                place-items: center;
                color: rgba(245, 245, 243, 0.66);
            }

            input[type='search'] {
                min-width: 0;
                height: 54px;
                border: 0;
                outline: none;
                background: transparent;
                color: #fff;
                font: 500 20px/1.25 'Fira Sans', system-ui, sans-serif;
                letter-spacing: 0;
            }

            input[type='search']::placeholder {
                color: rgba(245, 245, 243, 0.48);
            }

            .send-button,
            .icon-tool {
                width: 44px;
                height: 44px;
                border: 0;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: #fff;
                background: rgba(87, 104, 254, 0.95);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .send-button:hover,
            .icon-tool:hover {
                background: #6877ff;
                transform: translateY(-1px);
            }

            .send-button:disabled {
                cursor: default;
                opacity: 0.42;
                transform: none;
            }

            .tool-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                padding: 4px 2px 0;
            }

            .mode-group,
            .side-tools {
                display: flex;
                align-items: center;
                gap: 8px;
                min-width: 0;
            }

            .mode-chip {
                height: 36px;
                border: 0;
                border-radius: 999px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 0 13px;
                color: rgba(245, 245, 243, 0.72);
                background: rgba(255, 255, 255, 0.06);
                font: 500 14px/1 'Fira Sans', system-ui, sans-serif;
                cursor: pointer;
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
                white-space: nowrap;
            }

            .mode-chip:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #fff;
                transform: translateY(-1px);
            }

            .mode-chip[aria-pressed='true'] {
                color: #fff;
                background: rgba(87, 104, 254, 0.34);
                box-shadow: inset 0 0 0 1px rgba(137, 149, 255, 0.36);
            }

            .icon-tool {
                width: 36px;
                height: 36px;
                color: rgba(245, 245, 243, 0.76);
                background: rgba(255, 255, 255, 0.07);
            }

            .icon-tool[disabled] {
                cursor: default;
                opacity: 0.46;
                transform: none;
            }

            .file-input {
                display: none;
            }

            .file-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 10px 2px 0;
            }

            .file-chip {
                min-width: 0;
                max-width: 100%;
                height: 34px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 0 7px 0 10px;
                border-radius: 999px;
                color: rgba(245, 245, 243, 0.86);
                background: rgba(255, 255, 255, 0.075);
                border: 1px solid rgba(255, 255, 255, 0.08);
                box-sizing: border-box;
            }

            .file-label {
                min-width: 0;
                display: inline-flex;
                align-items: baseline;
                gap: 6px;
            }

            .file-name {
                min-width: 0;
                max-width: 230px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font: 500 13px/1 'Fira Sans', system-ui, sans-serif;
            }

            .file-size {
                flex-shrink: 0;
                color: rgba(245, 245, 243, 0.48);
                font-size: 12px;
                line-height: 1;
            }

            .file-remove {
                width: 24px;
                height: 24px;
                border: 0;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: rgba(245, 245, 243, 0.58);
                background: transparent;
                cursor: pointer;
                transition: color 160ms ease, background 160ms ease;
            }

            .file-remove:hover {
                color: #fff;
                background: rgba(255, 255, 255, 0.10);
            }

            .results-wrap {
                width: min(1180px, calc(100vw - 32px));
                margin: 0 auto;
                padding: 26px 0 72px;
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(320px, 390px);
                gap: 18px;
                align-items: start;
            }

            .primary-column {
                display: grid;
                gap: 18px;
                align-items: start;
            }

            .answer-panel,
            .sources-panel,
            .suggest-panel,
            .provider-panel {
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(22, 22, 22, 0.82);
                backdrop-filter: blur(20px);
                border-radius: var(--radius-2xl, 24px);
                box-sizing: border-box;
                overflow: hidden;
            }

            .answer-panel {
                padding: 24px;
                min-height: 168px;
                animation: resultIn 300ms ease both;
            }

            .panel-label {
                display: flex;
                align-items: center;
                gap: 8px;
                margin: 0 0 14px;
                color: rgba(245, 245, 243, 0.58);
                font-size: 13px;
                line-height: 1;
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .answer-text {
                margin: 0;
                overflow-wrap: anywhere;
                color: rgba(255, 255, 255, 0.92);
                font-size: 18px;
                line-height: 1.62;
            }

            .answer-text > :first-child,
            .source-ai-markdown > :first-child {
                margin-top: 0;
            }

            .answer-text > :last-child,
            .source-ai-markdown > :last-child {
                margin-bottom: 0;
            }

            .answer-text p,
            .source-ai-markdown p {
                margin: 0 0 14px;
            }

            .answer-text h1,
            .answer-text h2,
            .answer-text h3,
            .answer-text h4,
            .source-ai-markdown h1,
            .source-ai-markdown h2,
            .source-ai-markdown h3,
            .source-ai-markdown h4 {
                margin: 18px 0 10px;
                color: #fff;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 600;
                line-height: 1.18;
                letter-spacing: 0;
            }

            .answer-text h1,
            .answer-text h2 {
                font-size: 24px;
            }

            .answer-text h3,
            .answer-text h4,
            .source-ai-markdown h1,
            .source-ai-markdown h2,
            .source-ai-markdown h3,
            .source-ai-markdown h4 {
                font-size: 18px;
            }

            .answer-text ul,
            .answer-text ol,
            .source-ai-markdown ul,
            .source-ai-markdown ol {
                margin: 0 0 14px;
                padding-left: 22px;
            }

            .answer-text li,
            .source-ai-markdown li {
                margin: 6px 0;
            }

            .answer-text table,
            .source-ai-markdown table {
                width: 100%;
                margin: 14px 0;
                border-collapse: collapse;
                font-size: 15px;
                line-height: 1.42;
                display: block;
                overflow-x: auto;
            }

            .answer-text th,
            .answer-text td,
            .source-ai-markdown th,
            .source-ai-markdown td {
                padding: 9px 10px;
                border: 1px solid rgba(255, 255, 255, 0.10);
                vertical-align: top;
            }

            .answer-text th,
            .source-ai-markdown th {
                color: #fff;
                background: rgba(255, 255, 255, 0.06);
                font-weight: 600;
            }

            .answer-text a,
            .source-ai-markdown a {
                color: #9aa3ff;
                text-decoration: none;
            }

            .answer-text a:hover,
            .source-ai-markdown a:hover {
                text-decoration: underline;
            }

            .answer-text code,
            .source-ai-markdown code {
                border-radius: var(--radius-sm, 8px);
                padding: 2px 6px;
                background: rgba(255, 255, 255, 0.08);
                font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
                font-size: 0.88em;
            }

            .answer-text[data-error='true'] {
                color: #ffb8b8;
            }

            .answer-placeholder {
                min-height: 74px;
                display: grid;
                align-items: center;
                color: rgba(245, 245, 243, 0.48);
                font-size: 16px;
                line-height: 1.5;
            }

            .stream-dot {
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: #8f9bff;
                box-shadow: 0 0 0 0 rgba(143, 155, 255, 0.42);
                animation: streamPulse 1.1s ease infinite;
            }

            .source-list {
                display: grid;
                gap: 10px;
                margin-top: 12px;
            }

            .source-card {
                display: grid;
                gap: 9px;
                padding: 16px;
                border-radius: var(--radius-xl, 20px);
                color: inherit;
                text-decoration: none;
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.07);
                transition: transform 180ms ease, background 180ms ease, border-color 180ms ease;
                animation: resultIn 320ms ease both;
            }

            .source-card:hover {
                transform: translateY(-2px);
                background: rgba(255, 255, 255, 0.075);
                border-color: rgba(137, 149, 255, 0.34);
            }

            .source-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
            }

            .source-main {
                min-width: 0;
                display: grid;
                gap: 9px;
            }

            .source-ai-button {
                flex-shrink: 0;
                min-height: 32px;
                border: 0;
                border-radius: var(--radius-full, 999px);
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 0 11px;
                color: #fff;
                background: rgba(137, 149, 255, 0.20);
                box-shadow: inset 0 0 0 1px rgba(137, 149, 255, 0.22);
                font: 600 13px/1 'Fira Sans', system-ui, sans-serif;
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .source-ai-button:hover {
                background: rgba(137, 149, 255, 0.30);
                transform: translateY(-1px);
            }

            .source-ai-button:disabled {
                cursor: default;
                opacity: 0.54;
                transform: none;
            }

            .source-ai-panel {
                margin-top: 2px;
                padding: 13px 14px;
                border-radius: var(--radius-lg, 16px);
                border: 1px solid rgba(137, 149, 255, 0.18);
                background: rgba(87, 104, 254, 0.10);
                color: rgba(245, 245, 243, 0.84);
                animation: resultIn 220ms ease both;
            }

            .source-ai-label {
                display: inline-flex;
                align-items: center;
                gap: 7px;
                margin: 0 0 9px;
                color: rgba(245, 245, 243, 0.62);
                font-size: 12px;
                line-height: 1;
                text-transform: uppercase;
            }

            .source-ai-markdown {
                overflow-wrap: anywhere;
                font-size: 14px;
                line-height: 1.52;
            }

            .source-title {
                margin: 0;
                color: #fff;
                font-size: 17px;
                line-height: 1.32;
                overflow-wrap: anywhere;
            }

            a.source-title {
                text-decoration: none;
            }

            a.source-title:hover {
                color: #c6ccff;
                text-decoration: underline;
            }

            .source-url {
                margin: 0;
                color: #9aa3ff;
                font-size: 13px;
                line-height: 1.35;
                overflow-wrap: anywhere;
            }

            .source-url a {
                color: inherit;
                text-decoration: none;
            }

            .source-url a:hover {
                text-decoration: underline;
            }

            .source-snippet,
            .source-insight {
                margin: 0;
                color: rgba(245, 245, 243, 0.68);
                font-size: 14px;
                line-height: 1.48;
            }

            .source-insight {
                padding-top: 8px;
                border-top: 1px solid rgba(255, 255, 255, 0.07);
                color: rgba(245, 245, 243, 0.78);
            }

            .source-meta {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .provider-badge,
            .rank-badge {
                min-height: 24px;
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 0 9px;
                background: rgba(255, 255, 255, 0.07);
                color: rgba(245, 245, 243, 0.72);
                font-size: 12px;
                line-height: 1;
            }

            .side-column {
                display: grid;
                gap: 12px;
                position: sticky;
                top: 92px;
            }

            .provider-panel,
            .suggest-panel,
            .sources-panel {
                padding: 16px;
            }

            .provider-list,
            .suggest-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }

            .provider-chip,
            .suggest-chip {
                min-height: 32px;
                border: 0;
                border-radius: 999px;
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 0 11px;
                color: rgba(245, 245, 243, 0.78);
                background: rgba(255, 255, 255, 0.06);
                font: 500 13px/1 'Fira Sans', system-ui, sans-serif;
            }

            .suggest-chip {
                cursor: pointer;
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
                text-align: left;
            }

            .suggest-chip:hover {
                color: #fff;
                background: rgba(87, 104, 254, 0.26);
                transform: translateY(-1px);
            }

            .suggest-chip:disabled {
                cursor: default;
                opacity: 0.54;
                transform: none;
            }

            .provider-state {
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: #f5b64d;
            }

            .provider-chip[data-ok='true'] .provider-state {
                background: #5fd493;
            }

            .empty-shell {
                width: min(780px, calc(100vw - 32px));
                margin: 0 auto;
                padding: 26px 0 70px;
                display: grid;
                place-items: center;
                color: rgba(245, 245, 243, 0.56);
                font-size: 16px;
            }

            .skeleton {
                height: 86px;
                border-radius: var(--radius-xl, 20px);
                background: linear-gradient(90deg, rgba(255,255,255,0.05), rgba(255,255,255,0.12), rgba(255,255,255,0.05));
                background-size: 220% 100%;
                animation: skeleton 1.2s ease infinite;
            }

            @keyframes searchEnter {
                from { opacity: 0; transform: translateY(18px) scale(0.985); }
                to { opacity: 1; transform: translateY(0) scale(1); }
            }

            @keyframes resultIn {
                from { opacity: 0; transform: translateY(12px); }
                to { opacity: 1; transform: translateY(0); }
            }

            @keyframes streamPulse {
                0% { box-shadow: 0 0 0 0 rgba(143, 155, 255, 0.42); }
                100% { box-shadow: 0 0 0 13px rgba(143, 155, 255, 0); }
            }

            @keyframes skeleton {
                0% { background-position: 120% 0; }
                100% { background-position: -120% 0; }
            }

            @media (max-width: 980px) {
                .results-wrap {
                    grid-template-columns: 1fr;
                }

                .side-column {
                    position: static;
                    order: -1;
                }
            }

            @media (max-width: 640px) {
                .topbar {
                    height: 64px;
                    padding: 0 14px;
                }

                .brand-name {
                    font-size: 20px;
                }

                .back-label {
                    display: none;
                }

                .search-head {
                    padding: 28px 14px 16px;
                }

                .search-shell {
                    border-radius: 24px;
                    padding: 8px;
                }

                .search-line {
                    grid-template-columns: 38px minmax(0, 1fr) 42px;
                }

                input[type='search'] {
                    height: 48px;
                    font-size: 17px;
                }

                .tool-row {
                    align-items: stretch;
                    flex-direction: column;
                }

                .mode-group {
                    overflow-x: auto;
                    padding-bottom: 2px;
                }

                .side-tools {
                    justify-content: flex-start;
                }

                .file-name {
                    max-width: 180px;
                }

                .results-wrap {
                    width: calc(100vw - 20px);
                    padding-bottom: 42px;
                }

                .answer-panel {
                    padding: 18px;
                }

                .answer-text {
                    font-size: 16px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._search = this.useOp('frontend/public_search_run');
        this._sourceDescribe = this.useOp('frontend/public_search_source_describe');
        this._route = this.select((state) => state.router);
        this._query = '';
        this._mode = 'quick';
        this._selectedFiles = [];
        this._preparingFiles = false;
        this._lastRouteSig = '';
        this._runSeq = 0;
    }

    connectedCallback() {
        super.connectedCallback();
        const pendingFiles = takePendingPublicSearchFiles();
        if (pendingFiles.length > 0) {
            this._selectedFiles = pendingFiles;
        }
        this._syncFromRoute();
    }

    updated() {
        this._syncFromRoute();
    }

    _syncFromRoute() {
        const route = this._route.value;
        if (!route || route.routeKey !== 'search') {
            return;
        }
        const search = typeof route.search === 'string' ? route.search : '';
        const params = new URLSearchParams(search);
        const rawQuery = params.get('q');
        const query = typeof rawQuery === 'string' ? rawQuery.trim() : '';
        const rawMode = params.get('mode');
        const mode = typeof rawMode === 'string' && this._isMode(rawMode) ? rawMode : 'quick';
        const sig = `${query}\n${mode}`;
        if (sig === this._lastRouteSig) {
            return;
        }
        this._lastRouteSig = sig;
        this._query = query;
        this._mode = mode;
        if (query !== '') {
            void this._runSearch(query, mode);
        } else {
            this._search.reset(null);
        }
    }

    _isMode(value) {
        return value === 'quick' || value === 'deep' || value === 'research';
    }

    _handleInput(event) {
        const target = event.target;
        if (!target || typeof target.value !== 'string') {
            return;
        }
        this._query = target.value;
    }

    _setMode(mode) {
        if (!this._isMode(mode)) {
            throw new Error(`Invalid search mode: ${mode}`);
        }
        this._mode = mode;
    }

    _submit(event) {
        event.preventDefault();
        if (this._search.busy || this._preparingFiles) {
            return;
        }
        const query = this._query.trim();
        if (query === '') {
            if (this._selectedFiles.length > 0) {
                this.toast('search_page.file_query_required', { type: 'warning' });
            }
            return;
        }
        const mode = this._mode;
        const search = `?q=${encodeURIComponent(query)}&mode=${encodeURIComponent(mode)}`;
        const sig = `${query}\n${mode}`;
        if (sig === this._lastRouteSig) {
            void this._runSearch(query, mode);
            return;
        }
        this.navigate('search', {}, { search });
    }

    async _runSearch(query, mode) {
        if (this._search.busy || this._preparingFiles) {
            return;
        }
        this._runSeq += 1;
        const runId = `public_search_${Date.now().toString(36)}_${this._runSeq.toString(36)}`;
        this._preparingFiles = true;
        try {
            const files = await filesToPublicSearchA2aParts(this._selectedFiles);
            this._preparingFiles = false;
            void this._search.run({ run_id: runId, query, mode, files });
        } catch (error) {
            this._preparingFiles = false;
            this.toast('search_page.file_upload_error', {
                type: 'error',
                vars: { message: this._fileErrorMessage(error) },
            });
        }
    }

    _goHome() {
        this.navigate('landing');
    }

    _fileErrorMessage(error) {
        if (error instanceof Error && typeof error.message === 'string' && error.message !== '') {
            return error.message;
        }
        return String(error);
    }

    _openFilePicker() {
        const input = this.renderRoot.querySelector('[data-role="public-search-files"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('PublicSearchPage: file input not found');
        }
        input.click();
    }

    _handleFilesSelected(event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('PublicSearchPage: file input event target required');
        }
        try {
            const files = fileListToPublicSearchFiles(target.files);
            if (files.length > 0) {
                this._selectedFiles = [...this._selectedFiles, ...files];
            }
        } catch (error) {
            this.toast('search_page.file_upload_error', {
                type: 'error',
                vars: { message: this._fileErrorMessage(error) },
            });
        }
        target.value = '';
    }

    _removeFile(index) {
        if (!Number.isInteger(index) || index < 0 || index >= this._selectedFiles.length) {
            throw new Error('PublicSearchPage._removeFile: index out of range');
        }
        this._selectedFiles = this._selectedFiles.filter((_, itemIndex) => itemIndex !== index);
    }

    _displayUrl(result) {
        return result.display_url !== '' ? result.display_url : result.url;
    }

    _markdownTemplate(text, streaming) {
        return unsafeHTML(flowsChatMarkdownToHtml(text, { streaming }));
    }

    _insightForUrl(stream, url) {
        for (const insight of stream.result_insights) {
            if (insight.url === url) {
                return insight;
            }
        }
        return null;
    }

    _suggest(text) {
        if (this._search.busy) {
            return;
        }
        this._query = text;
        const search = `?q=${encodeURIComponent(text)}&mode=${encodeURIComponent(this._mode)}`;
        this.navigate('search', {}, { search });
    }

    _describeSource(stream, result) {
        if (this._sourceDescribe.busy) {
            return;
        }
        this._runSeq += 1;
        const runId = `public_search_source_${Date.now().toString(36)}_${this._runSeq.toString(36)}`;
        void this._sourceDescribe.run({
            run_id: runId,
            query: stream.query,
            source: result,
        });
    }

    _renderModeChip(mode) {
        const active = this._mode === mode.key;
        return html`
            <button
                class="mode-chip"
                type="button"
                aria-pressed=${active ? 'true' : 'false'}
                @click=${() => this._setMode(mode.key)}
            >
                <platform-icon name=${mode.icon} size="15"></platform-icon>
                <span>${this.t(mode.label)}</span>
            </button>
        `;
    }

    _renderSelectedFile(file, index) {
        return html`
            <div class="file-chip" role="listitem">
                <platform-icon file-icon name=${resolveFileIconKey(file.name, file.type)} size="18"></platform-icon>
                <span class="file-label">
                    <span class="file-name" title=${file.name}>${file.name}</span>
                    <span class="file-size">${formatFileSize(file.size)}</span>
                </span>
                <button
                    class="file-remove"
                    type="button"
                    title=${this.t('search_page.remove_file')}
                    aria-label=${this.t('search_page.remove_file')}
                    @click=${() => this._removeFile(index)}
                >
                    <platform-icon name="close" size="14"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderSelectedFiles() {
        if (this._selectedFiles.length === 0) {
            return nothing;
        }
        return html`
            <div class="file-list" role="list" aria-label=${this.t('search_page.selected_files')}>
                ${this._selectedFiles.map((file, index) => this._renderSelectedFile(file, index))}
            </div>
        `;
    }

    _renderComposer() {
        const busy = this._search.busy || this._preparingFiles;
        return html`
            <form class="search-shell" @submit=${this._submit}>
                <div class="search-line">
                    <span class="search-icon"><platform-icon name="search" size="22"></platform-icon></span>
                    <input
                        type="search"
                        autocomplete="off"
                        spellcheck="true"
                        .value=${this._query}
                        placeholder=${this.t('search_page.placeholder')}
                        aria-label=${this.t('search_page.input_aria')}
                        @input=${this._handleInput}
                    />
                    <button class="send-button" type="submit" ?disabled=${busy} aria-label=${this.t('search_page.submit')}>
                        <platform-icon name="send" size="18"></platform-icon>
                    </button>
                </div>
                <div class="tool-row">
                    <div class="mode-group" role="group" aria-label=${this.t('search_page.mode_group')}>
                        ${SEARCH_MODES.map((mode) => this._renderModeChip(mode))}
                    </div>
                    <div class="side-tools" aria-label=${this.t('search_page.tools_group')}>
                        <input
                            class="file-input"
                            data-role="public-search-files"
                            type="file"
                            multiple
                            @change=${this._handleFilesSelected}
                        />
                        <button
                            class="icon-tool"
                            type="button"
                            title=${this.t('search_page.files_tool')}
                            aria-label=${this.t('search_page.files_tool')}
                            ?disabled=${busy}
                            @click=${this._openFilePicker}
                        >
                            <platform-icon name="paperclip" size="17"></platform-icon>
                        </button>
                    </div>
                </div>
                ${this._renderSelectedFiles()}
            </form>
        `;
    }

    _renderAnswer(stream) {
        const error = this._search.error;
        if (typeof error === 'string' && error !== '') {
            return html`
                <section class="answer-panel">
                    <p class="panel-label">
                        <platform-icon name="notification-error" size="14"></platform-icon>
                        <span>${this.t('search_page.answer_label')}</span>
                    </p>
                    <p class="answer-text" data-error="true">${error}</p>
                </section>
            `;
        }
        const hasAnswer = stream.answer.trim() !== '';
        return html`
            <section class="answer-panel">
                <p class="panel-label">
                    ${stream.completed ? html`<platform-icon name="check" size="14"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>${this.t('search_page.answer_label')}</span>
                </p>
                ${hasAnswer
                    ? html`<div class="answer-text">${this._markdownTemplate(stream.answer, !stream.completed)}</div>`
                    : html`<div class="answer-placeholder">${this.t('search_page.answer_pending')}</div>`}
            </section>
        `;
    }

    _renderSourceAiDescription(result) {
        const descriptions = this._sourceDescribe.state.descriptions;
        const activeUrl = this._sourceDescribe.state.active_url;
        const description = descriptions[result.url];
        const isActive = activeUrl === result.url;
        if (isActive && typeof this._sourceDescribe.error === 'string' && this._sourceDescribe.error !== '') {
            return html`
                <div class="source-ai-panel">
                    <p class="source-ai-label">
                        <platform-icon name="notification-error" size="13"></platform-icon>
                        <span>AI</span>
                    </p>
                    <div class="source-ai-markdown">${this._sourceDescribe.error}</div>
                </div>
            `;
        }
        if (!description) {
            return nothing;
        }
        const hasAnswer = description.answer.trim() !== '';
        if (!hasAnswer && description.completed !== true && this._sourceDescribe.busy) {
            return html`
                <div class="source-ai-panel">
                    <p class="source-ai-label"><span class="stream-dot"></span><span>AI</span></p>
                    <div class="source-ai-markdown">${description.activity}</div>
                </div>
            `;
        }
        if (!hasAnswer) {
            return nothing;
        }
        return html`
            <div class="source-ai-panel">
                <p class="source-ai-label">
                    ${description.completed ? html`<platform-icon name="check" size="13"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>AI</span>
                </p>
                <div class="source-ai-markdown">
                    ${this._markdownTemplate(description.answer, !description.completed)}
                </div>
            </div>
        `;
    }

    _renderSource(stream, result, index) {
        const insight = this._insightForUrl(stream, result.url);
        const activeUrl = this._sourceDescribe.state.active_url;
        const describing = this._sourceDescribe.busy && activeUrl === result.url;
        return html`
            <article
                class="source-card"
                style=${`animation-delay: ${Math.min(index * 34, 260)}ms`}
            >
                <div class="source-header">
                    <div class="source-main">
                        <div class="source-meta">
                            <span class="rank-badge">#${result.rank}</span>
                            <span class="provider-badge">${result.provider}</span>
                        </div>
                        <a class="source-title" href=${result.url} target="_blank" rel="noopener noreferrer">${result.title}</a>
                    </div>
                    <button
                        class="source-ai-button"
                        type="button"
                        ?disabled=${this._sourceDescribe.busy}
                        title="AI"
                        aria-label="AI"
                        @click=${() => this._describeSource(stream, result)}
                    >
                        ${describing ? html`<span class="stream-dot"></span>` : html`<platform-icon name="sparkle" size="14"></platform-icon>`}
                        <span>AI</span>
                    </button>
                </div>
                <p class="source-url">
                    <a href=${result.url} target="_blank" rel="noopener noreferrer">${this._displayUrl(result)}</a>
                </p>
                <p class="source-snippet">${result.snippet}</p>
                ${insight !== null ? html`<p class="source-insight">${insight.relevance_hint}</p>` : html``}
                ${this._renderSourceAiDescription(result)}
            </article>
        `;
    }

    _renderSources(stream) {
        if (stream.results.length === 0 && this._search.busy) {
            return html`
                <section class="sources-panel">
                    <p class="panel-label"><span class="stream-dot"></span><span>${this.t('search_page.sources_label')}</span></p>
                    <div class="source-list">
                        <div class="skeleton"></div>
                        <div class="skeleton"></div>
                        <div class="skeleton"></div>
                    </div>
                </section>
            `;
        }
        if (stream.results.length === 0) {
            return html``;
        }
        return html`
            <section class="sources-panel">
                <p class="panel-label"><platform-icon name="link" size="14"></platform-icon><span>${this.t('search_page.sources_label')}</span></p>
                <div class="source-list">
                    ${stream.results.map((result, index) => this._renderSource(stream, result, index))}
                </div>
            </section>
        `;
    }

    _renderProviders(stream) {
        const providers = Object.entries(stream.providers);
        if (providers.length === 0) {
            return html``;
        }
        return html`
            <section class="provider-panel">
                <p class="panel-label"><platform-icon name="server" size="14"></platform-icon><span>${this.t('search_page.providers_label')}</span></p>
                <div class="provider-list">
                    ${providers.map(([name, status]) => html`
                        <span class="provider-chip" data-ok=${status.ok ? 'true' : 'false'}>
                            <span class="provider-state"></span>
                            <span>${name}</span>
                        </span>
                    `)}
                </div>
            </section>
        `;
    }

    _renderSuggestions(stream) {
        const suggestions = [...stream.followups, ...stream.suggestions];
        if (suggestions.length === 0) {
            return html``;
        }
        return html`
            <section class="suggest-panel">
                <p class="panel-label"><platform-icon name="sparkle" size="14"></platform-icon><span>${this.t('search_page.suggestions_label')}</span></p>
                <div class="suggest-list">
                    ${suggestions.map((item) => html`
                        <button class="suggest-chip" type="button" ?disabled=${this._search.busy} @click=${() => this._suggest(item.text)}>
                            ${item.text}
                        </button>
                    `)}
                </div>
            </section>
        `;
    }

    _renderBody(stream) {
        const active = stream.phase !== 'idle' || this._search.busy || stream.results.length > 0;
        if (!active) {
            return html`<div class="empty-shell">${this.t('search_page.empty_hint')}</div>`;
        }
        return html`
            <main class="results-wrap">
                <div class="primary-column">
                    ${this._renderAnswer(stream)}
                    ${this._renderSources(stream)}
                </div>
                <aside class="side-column">
                    ${this._renderProviders(stream)}
                    ${this._renderSuggestions(stream)}
                </aside>
            </main>
        `;
    }

    render() {
        const stream = this._search.state.stream;
        return html`
            <div class="page">
                <header class="topbar">
                    <button class="brand" type="button" @click=${this._goHome} aria-label=${this.t('search_page.home')}>
                        <span class="brand-mark">H</span>
                        <span class="brand-name">Humanitec</span>
                    </button>
                    <button class="back-link" type="button" @click=${this._goHome}>
                        <platform-icon name="arrow-left" size="16"></platform-icon>
                        <span class="back-label">${this.t('search_page.back')}</span>
                    </button>
                </header>
                <section class="search-head">
                    <h1 class="search-title">${this.t('search_page.title')}</h1>
                    ${this._renderComposer()}
                </section>
                ${this._renderBody(stream)}
            </div>
        `;
    }
}

customElements.define('public-search-page', PublicSearchPage);
