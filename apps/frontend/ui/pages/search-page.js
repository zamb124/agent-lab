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
import { takePublicSearchLandingTransition } from '../utils/public-search-transition.js';
import { redirectToLogin } from '@platform/lib/utils/auth-redirect.js';
import '@platform/lib/components/platform-icon.js';

const SEARCH_MODES = Object.freeze([
    { key: 'quick', icon: 'search', label: 'search_page.mode_quick' },
    { key: 'deep', icon: 'layers', label: 'search_page.mode_deep' },
    { key: 'research', icon: 'sparkle', label: 'search_page.mode_research' },
]);
const SEARCH_CHROME_HIDE_DELTA_PX = 50;
const SEARCH_CHROME_SHOW_DELTA_PX = 14;
const SEARCH_CHROME_TOP_VISIBLE_PX = 24;

export class PublicSearchPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        _query: { state: true },
        _mode: { state: true },
        _selectedFiles: { state: true },
        _preparingFiles: { state: true },
        _searchChromeHidden: { state: true },
        _entryAnimation: { state: true },
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
                position: relative;
            }

            .topbar {
                height: 60px;
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
            .back-link,
            .locale-option,
            .theme-toggle {
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

            .top-actions {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                min-width: 0;
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

            .locale-switch {
                min-height: 36px;
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 3px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }

            .locale-option {
                min-width: 34px;
                min-height: 28px;
                justify-content: center;
                border-radius: 999px;
                color: rgba(245, 245, 243, 0.58);
                font-size: 13px;
                line-height: 1;
                transition: background 180ms ease, color 180ms ease;
            }

            .locale-option[aria-pressed='true'] {
                color: #fff;
                background: rgba(87, 104, 254, 0.36);
            }

            .theme-toggle {
                width: 38px;
                height: 38px;
                justify-content: center;
                border-radius: 50%;
                color: rgba(245, 245, 243, 0.74);
                background: rgba(255, 255, 255, 0.06);
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
            }

            .theme-toggle:hover,
            .locale-option:hover {
                color: #fff;
                background: rgba(255, 255, 255, 0.12);
                transform: translateY(-1px);
            }

            .search-head {
                padding: clamp(34px, 7vw, 86px) clamp(18px, 4vw, 56px) 22px;
                display: grid;
                justify-items: center;
                gap: 18px;
            }

            .search-head.is-active {
                position: sticky;
                top: 60px;
                z-index: 16;
                padding: 12px clamp(18px, 4vw, 56px);
                background: transparent;
                border-bottom: 0;
                backdrop-filter: none;
                pointer-events: none;
            }

            .search-title {
                margin: 0;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 500;
                font-size: 92px;
                line-height: 0.96;
                letter-spacing: 0;
                text-align: center;
                color: rgba(245, 245, 243, 0.95);
            }

            .search-head.is-active .search-title {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0 0 0 0);
                white-space: nowrap;
                border: 0;
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
                opacity: 1;
                transform: translateY(0) scale(1);
                transition:
                    opacity 360ms ease,
                    transform 440ms cubic-bezier(0.16, 1, 0.3, 1),
                    filter 420ms ease,
                    box-shadow 360ms ease;
                will-change: opacity, transform, filter;
            }

            .search-head:not(.is-active) .search-shell {
                animation: searchEnter 340ms ease both;
            }

            .search-head.is-active .search-shell {
                width: min(980px, calc(100vw - 32px));
                border-radius: 24px;
                padding: 8px;
                box-shadow: 0 18px 54px rgba(0, 0, 0, 0.36);
                pointer-events: auto;
            }

            .page[data-entry='landing'] .topbar {
                animation: topbarEnter 430ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
            }

            .page[data-entry='landing'] .search-head.is-active .search-shell {
                animation: searchLandingHandoff 680ms cubic-bezier(0.18, 0.86, 0.24, 1) both;
            }

            .page[data-entry='landing'] .results-wrap {
                animation: resultsLandingEnter 720ms cubic-bezier(0.18, 0.86, 0.24, 1) 120ms both;
            }

            .search-head.is-active.is-chrome-hidden .search-shell,
            .page[data-entry='landing'] .search-head.is-active.is-chrome-hidden .search-shell {
                opacity: 0;
                transform: translateY(-14px) scale(0.992);
                filter: blur(4px);
                pointer-events: none;
                animation: none;
            }

            .search-line {
                min-height: 58px;
                display: grid;
                grid-template-columns: 44px minmax(0, 1fr) 44px;
                align-items: center;
                gap: 4px;
            }

            .search-head.is-active .search-line {
                min-height: 46px;
                grid-template-columns: 38px minmax(0, 1fr) 40px;
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

            .search-head.is-active input[type='search'] {
                height: 42px;
                font-size: 18px;
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

            .search-head.is-active .send-button {
                width: 40px;
                height: 40px;
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

            .search-head.is-active .tool-row {
                justify-content: flex-start;
                padding: 7px 0 0 1px;
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

            .search-head.is-active .mode-chip {
                height: 31px;
                gap: 6px;
                padding: 0 11px;
                font-size: 13px;
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

            .search-head.is-active .icon-tool {
                width: 31px;
                height: 31px;
            }

            .icon-tool[disabled] {
                cursor: default;
                opacity: 0.46;
                transform: none;
            }

            .file-input {
                position: absolute;
                width: 1px;
                height: 1px;
                opacity: 0;
                overflow: hidden;
                clip: rect(0 0 0 0);
                clip-path: inset(50%);
                pointer-events: none;
            }

            .file-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding: 10px 2px 0;
            }

            .search-head.is-active .file-list {
                padding-top: 8px;
                padding-left: 1px;
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
                width: min(1280px, calc(100vw - 32px));
                margin: 0 auto;
                padding: 16px 0 72px;
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
                gap: 14px;
                align-items: start;
            }

            .primary-column {
                display: grid;
                gap: 14px;
                align-items: start;
            }

            .answer-panel,
            .sources-panel,
            .suggest-panel,
            .provider-panel {
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(22, 22, 22, 0.82);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                box-sizing: border-box;
                overflow: hidden;
            }

            .answer-panel {
                padding: 18px;
                min-height: 116px;
                animation: resultIn 300ms ease both;
            }

            .answer-panel[data-state='error'] {
                border-color: rgba(255, 132, 132, 0.20);
                background:
                    linear-gradient(135deg, rgba(255, 132, 132, 0.10), rgba(22, 22, 22, 0.82) 48%),
                    rgba(22, 22, 22, 0.82);
            }

            .panel-label {
                display: flex;
                align-items: center;
                gap: 8px;
                margin: 0 0 10px;
                color: rgba(245, 245, 243, 0.58);
                font-size: 12px;
                line-height: 1;
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .panel-count {
                min-height: 20px;
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 0 7px;
                color: rgba(245, 245, 243, 0.68);
                background: rgba(255, 255, 255, 0.07);
                font-size: 12px;
                line-height: 1;
                text-transform: none;
            }

            .answer-text {
                margin: 0;
                overflow-wrap: anywhere;
                color: rgba(255, 255, 255, 0.92);
                font-size: 16px;
                line-height: 1.56;
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
                font-size: 21px;
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

            .answer-error {
                display: grid;
                gap: 12px;
                color: rgba(245, 245, 243, 0.84);
            }

            .answer-error-main {
                display: grid;
                grid-template-columns: 34px minmax(0, 1fr);
                gap: 12px;
                align-items: start;
            }

            .answer-error-icon {
                width: 34px;
                height: 34px;
                display: grid;
                place-items: center;
                border-radius: 50%;
                color: #ffb8b8;
                background: rgba(255, 132, 132, 0.12);
                box-shadow: inset 0 0 0 1px rgba(255, 132, 132, 0.20);
            }

            .answer-error-copy {
                min-width: 0;
                display: grid;
                gap: 6px;
            }

            .answer-error-title {
                margin: 0;
                color: rgba(255, 255, 255, 0.94);
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 22px;
                font-weight: 600;
                line-height: 1.18;
                letter-spacing: 0;
            }

            .answer-error-text {
                margin: 0;
                color: rgba(245, 245, 243, 0.66);
                font-size: 15px;
                line-height: 1.48;
            }

            .answer-error-action {
                width: fit-content;
                min-height: 34px;
                border: 0;
                border-radius: 999px;
                padding: 0 14px;
                color: #fff;
                background: rgba(137, 149, 255, 0.28);
                box-shadow: inset 0 0 0 1px rgba(137, 149, 255, 0.28);
                font: 600 13px/1 'Fira Sans', system-ui, sans-serif;
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease;
            }

            .answer-error-action:hover {
                transform: translateY(-1px);
                background: rgba(137, 149, 255, 0.38);
            }

            .answer-error-details {
                margin: 2px 0 0 46px;
                color: rgba(245, 245, 243, 0.52);
                font-size: 13px;
                line-height: 1.45;
            }

            .answer-error-details summary {
                width: fit-content;
                cursor: pointer;
            }

            .answer-error-code {
                margin: 8px 0 0;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                color: rgba(245, 245, 243, 0.62);
                font: 12px/1.45 var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
            }

            .answer-placeholder {
                min-height: 54px;
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
                gap: 8px;
                margin-top: 10px;
            }

            .source-card {
                display: grid;
                gap: 7px;
                padding: 12px;
                border-radius: 16px;
                color: inherit;
                text-decoration: none;
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.07);
                transition: transform 180ms ease, background 180ms ease, border-color 180ms ease;
                animation: resultIn 320ms ease both;
            }

            .source-card-inner {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: 12px;
                align-items: start;
            }

            .source-content {
                min-width: 0;
                display: grid;
                gap: 6px;
            }

            .source-site-row {
                display: flex;
                align-items: center;
                gap: 8px;
                min-width: 0;
                color: rgba(245, 245, 243, 0.72);
                font-size: 12px;
                line-height: 1.2;
            }

            .source-favicon {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                flex-shrink: 0;
                object-fit: cover;
                background: rgba(255, 255, 255, 0.08);
            }

            .source-site-name {
                flex-shrink: 0;
                max-width: 42%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: rgba(245, 245, 243, 0.86);
            }

            .source-site-sep {
                flex-shrink: 0;
                opacity: 0.55;
            }

            .source-display-url {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: rgba(154, 163, 255, 0.92);
            }

            .source-thumb {
                width: 72px;
                height: 72px;
                border-radius: 12px;
                object-fit: cover;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }

            .source-results-meta {
                margin: 2px 0 0;
                color: rgba(245, 245, 243, 0.52);
                font-size: 12px;
                line-height: 1.3;
            }

            .source-scroll-sentinel {
                width: 100%;
                height: 1px;
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
                gap: 6px;
            }

            .source-ai-button {
                flex-shrink: 0;
                min-height: 30px;
                border: 0;
                border-radius: var(--radius-full, 999px);
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 0 10px;
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
                padding: 12px;
                border-radius: 14px;
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
                font-size: 18px;
                line-height: 1.28;
                overflow-wrap: anywhere;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
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
                font-size: 12px;
                line-height: 1.3;
                overflow-wrap: anywhere;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
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
                font-size: 13px;
                line-height: 1.42;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .source-insight {
                padding-top: 6px;
                border-top: 1px solid rgba(255, 255, 255, 0.07);
                color: rgba(245, 245, 243, 0.78);
                -webkit-line-clamp: 1;
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
                gap: 10px;
                position: sticky;
                top: 148px;
            }

            .provider-panel,
            .suggest-panel,
            .sources-panel {
                padding: 14px;
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

            .provider-count {
                color: rgba(245, 245, 243, 0.48);
            }

            .suggest-chip {
                cursor: pointer;
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
                text-align: left;
                line-height: 1.16;
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

            @keyframes searchLandingHandoff {
                0% {
                    opacity: 0;
                    transform: translateY(42vh) scale(1.045);
                    filter: blur(10px);
                    box-shadow: 0 38px 120px rgba(0, 0, 0, 0.54);
                }
                58% {
                    opacity: 1;
                    transform: translateY(-8px) scale(1.005);
                    filter: blur(0);
                }
                100% {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                    filter: blur(0);
                }
            }

            @keyframes resultsLandingEnter {
                from {
                    opacity: 0;
                    transform: translateY(34px);
                    filter: blur(8px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                    filter: blur(0);
                }
            }

            @keyframes topbarEnter {
                from {
                    opacity: 0;
                    transform: translateY(-14px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
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

            :host-context([data-theme="light"]) {
                color: #12131a;
                background:
                    linear-gradient(180deg, rgba(247, 248, 252, 0.88) 0%, #f7f8fc 42%, #eef1fa 100%),
                    url('/static/frontend/assets/images/main_img.png') center 18% / min(980px, 74vw) auto no-repeat,
                    #f7f8fc;
            }

            :host-context([data-theme="light"]) .topbar {
                background: rgba(247, 248, 252, 0.78);
                border-color: rgba(16, 20, 34, 0.10);
            }

            :host-context([data-theme="light"]) .brand,
            :host-context([data-theme="light"]) .search-title {
                color: rgba(18, 19, 26, 0.94);
            }

            :host-context([data-theme="light"]) .back-link,
            :host-context([data-theme="light"]) .theme-toggle,
            :host-context([data-theme="light"]) .locale-switch {
                color: rgba(30, 34, 48, 0.70);
                background: rgba(255, 255, 255, 0.72);
                border-color: rgba(16, 20, 34, 0.10);
            }

            :host-context([data-theme="light"]) .back-link:hover,
            :host-context([data-theme="light"]) .theme-toggle:hover,
            :host-context([data-theme="light"]) .locale-option:hover {
                color: #12131a;
                background: rgba(255, 255, 255, 0.92);
            }

            :host-context([data-theme="light"]) .locale-option {
                color: rgba(30, 34, 48, 0.58);
            }

            :host-context([data-theme="light"]) .locale-option[aria-pressed='true'] {
                color: #fff;
                background: rgba(87, 104, 254, 0.84);
            }

            :host-context([data-theme="light"]) .search-shell {
                background: rgba(255, 255, 255, 0.86);
                border-color: rgba(16, 20, 34, 0.12);
                box-shadow: 0 24px 70px rgba(35, 43, 82, 0.14);
            }

            :host-context([data-theme="light"]) .search-head.is-active .search-shell {
                box-shadow: 0 18px 54px rgba(35, 43, 82, 0.14);
            }

            :host-context([data-theme="light"]) .search-icon,
            :host-context([data-theme="light"]) .icon-tool {
                color: rgba(30, 34, 48, 0.56);
            }

            :host-context([data-theme="light"]) input[type='search'] {
                color: #12131a;
            }

            :host-context([data-theme="light"]) input[type='search']::placeholder {
                color: rgba(30, 34, 48, 0.46);
            }

            :host-context([data-theme="light"]) .mode-chip,
            :host-context([data-theme="light"]) .provider-chip,
            :host-context([data-theme="light"]) .suggest-chip,
            :host-context([data-theme="light"]) .rank-badge,
            :host-context([data-theme="light"]) .provider-badge,
            :host-context([data-theme="light"]) .panel-count,
            :host-context([data-theme="light"]) .file-chip {
                color: rgba(30, 34, 48, 0.72);
                background: rgba(16, 20, 34, 0.06);
                border-color: rgba(16, 20, 34, 0.08);
            }

            :host-context([data-theme="light"]) .mode-chip:hover,
            :host-context([data-theme="light"]) .suggest-chip:hover {
                color: #12131a;
                background: rgba(87, 104, 254, 0.14);
            }

            :host-context([data-theme="light"]) .mode-chip[aria-pressed='true'] {
                color: #fff;
                background: rgba(87, 104, 254, 0.86);
                box-shadow: inset 0 0 0 1px rgba(87, 104, 254, 0.24);
            }

            :host-context([data-theme="light"]) .answer-panel,
            :host-context([data-theme="light"]) .sources-panel,
            :host-context([data-theme="light"]) .suggest-panel,
            :host-context([data-theme="light"]) .provider-panel {
                background: rgba(255, 255, 255, 0.78);
                border-color: rgba(16, 20, 34, 0.10);
            }

            :host-context([data-theme="light"]) .answer-panel[data-state='error'] {
                border-color: rgba(210, 67, 67, 0.18);
                background:
                    linear-gradient(135deg, rgba(210, 67, 67, 0.08), rgba(255, 255, 255, 0.80) 48%),
                    rgba(255, 255, 255, 0.78);
            }

            :host-context([data-theme="light"]) .answer-error-icon {
                color: #b33a3a;
                background: rgba(210, 67, 67, 0.10);
                box-shadow: inset 0 0 0 1px rgba(210, 67, 67, 0.16);
            }

            :host-context([data-theme="light"]) .answer-error-title {
                color: rgba(18, 19, 26, 0.94);
            }

            :host-context([data-theme="light"]) .answer-error-text {
                color: rgba(30, 34, 48, 0.66);
            }

            :host-context([data-theme="light"]) .answer-error-action {
                color: #fff;
                background: rgba(87, 104, 254, 0.86);
                box-shadow: inset 0 0 0 1px rgba(87, 104, 254, 0.24);
            }

            :host-context([data-theme="light"]) .answer-error-action:hover {
                background: rgba(74, 90, 232, 0.92);
            }

            :host-context([data-theme="light"]) .answer-error-details,
            :host-context([data-theme="light"]) .answer-error-code {
                color: rgba(30, 34, 48, 0.54);
            }

            :host-context([data-theme="light"]) .source-card {
                background: rgba(255, 255, 255, 0.72);
                border-color: rgba(16, 20, 34, 0.10);
            }

            :host-context([data-theme="light"]) .source-card:hover {
                background: rgba(255, 255, 255, 0.92);
                border-color: rgba(87, 104, 254, 0.30);
            }

            :host-context([data-theme="light"]) .panel-label,
            :host-context([data-theme="light"]) .answer-placeholder,
            :host-context([data-theme="light"]) .provider-count {
                color: rgba(30, 34, 48, 0.54);
            }

            :host-context([data-theme="light"]) .answer-text,
            :host-context([data-theme="light"]) .source-title,
            :host-context([data-theme="light"]) .source-ai-markdown {
                color: rgba(18, 19, 26, 0.92);
            }

            :host-context([data-theme="light"]) .source-snippet,
            :host-context([data-theme="light"]) .source-insight {
                color: rgba(30, 34, 48, 0.70);
            }

            :host-context([data-theme="light"]) .source-url,
            :host-context([data-theme="light"]) .answer-text a,
            :host-context([data-theme="light"]) .source-ai-markdown a,
            :host-context([data-theme="light"]) a.source-title {
                color: #4E5DE8;
            }

            :host-context([data-theme="light"]) .source-ai-button {
                color: #3f49d7;
                background: rgba(87, 104, 254, 0.16);
                box-shadow:
                    inset 0 0 0 1px rgba(87, 104, 254, 0.26),
                    0 8px 20px rgba(87, 104, 254, 0.10);
            }

            :host-context([data-theme="light"]) .source-ai-button:hover {
                color: #fff;
                background: rgba(87, 104, 254, 0.86);
                box-shadow:
                    inset 0 0 0 1px rgba(87, 104, 254, 0.30),
                    0 10px 24px rgba(87, 104, 254, 0.18);
            }

            :host-context([data-theme="light"]) .source-ai-button:disabled {
                color: rgba(63, 73, 215, 0.78);
                background: rgba(87, 104, 254, 0.14);
                box-shadow: inset 0 0 0 1px rgba(87, 104, 254, 0.22);
                opacity: 0.86;
            }

            :host-context([data-theme="light"]) .source-ai-panel {
                color: rgba(18, 19, 26, 0.84);
                background: rgba(87, 104, 254, 0.10);
                border-color: rgba(87, 104, 254, 0.22);
            }

            :host-context([data-theme="light"]) .source-site-row {
                color: rgba(30, 34, 48, 0.62);
            }

            :host-context([data-theme="light"]) .source-site-name {
                color: rgba(18, 19, 26, 0.88);
            }

            :host-context([data-theme="light"]) .source-display-url {
                color: #4E5DE8;
            }

            :host-context([data-theme="light"]) .source-results-meta {
                color: rgba(30, 34, 48, 0.54);
            }

            :host-context([data-theme="light"]) .source-favicon,
            :host-context([data-theme="light"]) .source-thumb {
                background: rgba(16, 20, 34, 0.06);
                border-color: rgba(16, 20, 34, 0.10);
            }

            @media (max-width: 980px) {
                .search-title {
                    font-size: 72px;
                }

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

                .top-actions {
                    gap: 6px;
                }

                .locale-switch {
                    min-height: 34px;
                }

                .locale-option {
                    min-width: 30px;
                    min-height: 26px;
                    padding: 0 7px;
                }

                .theme-toggle,
                .back-link {
                    width: 36px;
                    height: 36px;
                    min-height: 36px;
                    padding: 0;
                    justify-content: center;
                }

                .search-head.is-active {
                    top: 64px;
                    padding: 10px 10px;
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

                .search-title {
                    font-size: 48px;
                }

                .search-shell {
                    border-radius: 24px;
                    padding: 8px;
                }

                .search-head.is-active .search-shell {
                    border-radius: 20px;
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

                .search-head.is-active .tool-row {
                    align-items: center;
                    flex-direction: row;
                    overflow-x: auto;
                    padding-top: 8px;
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
                    padding-top: 10px;
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
        this._serpMore = this.useOp('frontend/public_search_serp_more');
        this._sourceDescribe = this.useOp('frontend/public_search_source_describe');
        this._route = this.select((state) => state.router);
        this._localeSel = this.select((state) => state.i18n.locale);
        this._themeSel = this.select((state) => state.theme.mode);
        this._query = '';
        this._mode = 'quick';
        this._selectedFiles = [];
        this._preparingFiles = false;
        this._searchChromeHidden = false;
        this._entryAnimation = 'direct';
        this._lastRouteSig = '';
        this._runSeq = 0;
        this._lastScrollY = 0;
        this._scrollAnchorY = 0;
        this._scrollDirection = 'still';
        this.        _scrollFrame = 0;
        this._serpObserver = null;
        this._serpObservedSentinel = null;
        this._serpLoadBlocked = false;
        this._lastSerpCacheKey = '';
        this._handleWindowScroll = this._handleWindowScroll.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._lastScrollY = window.scrollY;
        this._scrollAnchorY = this._lastScrollY;
        window.addEventListener('scroll', this._handleWindowScroll, { passive: true });
        const pendingFiles = takePendingPublicSearchFiles();
        if (pendingFiles.length > 0) {
            this._selectedFiles = pendingFiles;
        }
        this._syncFromRoute();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('scroll', this._handleWindowScroll);
        if (this._scrollFrame !== 0) {
            window.cancelAnimationFrame(this._scrollFrame);
            this._scrollFrame = 0;
        }
        if (this._serpObserver !== null) {
            this._serpObserver.disconnect();
            this._serpObserver = null;
            this._serpObservedSentinel = null;
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        this._syncFromRoute();
        const stream = this._search.state.stream;
        if (stream.serp_cache_key !== this._lastSerpCacheKey) {
            this._lastSerpCacheKey = stream.serp_cache_key;
            this._serpLoadBlocked = false;
        }
        this._ensureSerpSentinelObserver();
    }

    _handleWindowScroll() {
        if (this._scrollFrame !== 0) {
            return;
        }
        this._scrollFrame = window.requestAnimationFrame(() => {
            this._scrollFrame = 0;
            this._syncSearchChromeForScroll();
        });
    }

    _syncSearchChromeForScroll() {
        const stream = this._search.state.stream;
        const scrollY = Math.max(0, window.scrollY);
        if (!this._isStreamActive(stream) || scrollY <= SEARCH_CHROME_TOP_VISIBLE_PX) {
            this._lastScrollY = scrollY;
            this._scrollAnchorY = scrollY;
            this._scrollDirection = 'still';
            if (this._searchChromeHidden) {
                this._searchChromeHidden = false;
            }
            return;
        }

        const delta = scrollY - this._lastScrollY;
        if (delta === 0) {
            return;
        }
        const direction = delta > 0 ? 'down' : 'up';
        if (direction !== this._scrollDirection) {
            this._scrollDirection = direction;
            this._scrollAnchorY = this._lastScrollY;
        }

        const travel = Math.abs(scrollY - this._scrollAnchorY);
        if (direction === 'down' && travel >= SEARCH_CHROME_HIDE_DELTA_PX && !this._searchChromeHidden) {
            this._searchChromeHidden = true;
        }
        if (direction === 'up' && travel >= SEARCH_CHROME_SHOW_DELTA_PX && this._searchChromeHidden) {
            this._searchChromeHidden = false;
        }
        this._lastScrollY = scrollY;
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
        this._searchChromeHidden = false;
        this._lastScrollY = Math.max(0, window.scrollY);
        this._scrollAnchorY = this._lastScrollY;
        this._scrollDirection = 'still';
        if (query !== '') {
            this._entryAnimation = takePublicSearchLandingTransition(query, mode) ? 'landing' : 'direct';
            this._serpLoadBlocked = false;
            void this._runSearch(query, mode);
        } else {
            this._entryAnimation = 'direct';
            this._search.reset(null);
        }
    }

    _isMode(value) {
        return value === 'quick' || value === 'deep' || value === 'research';
    }

    _isStreamActive(stream) {
        return stream.phase !== 'idle' || this._search.busy || stream.results.length > 0;
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
        if (this._preparingFiles) {
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
        if (this._preparingFiles) {
            return;
        }
        this._searchChromeHidden = false;
        this._lastScrollY = Math.max(0, window.scrollY);
        this._scrollAnchorY = this._lastScrollY;
        this._scrollDirection = 'still';
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

    _setLocale(locale) {
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error(`PublicSearchPage._setLocale: invalid locale "${locale}"`);
        }
        if (this._localeSel.value === locale) {
            return;
        }
        this.setLocale(locale);
    }

    _toggleTheme() {
        const mode = this._themeSel.value;
        if (mode !== 'dark' && mode !== 'light') {
            throw new Error(`PublicSearchPage._toggleTheme: invalid theme "${mode}"`);
        }
        this.setTheme(mode === 'dark' ? 'light' : 'dark');
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
        if (this._preparingFiles) {
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
        const preparing = this._preparingFiles;
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
                    <button class="send-button" type="submit" ?disabled=${preparing} aria-label=${this.t('search_page.submit')}>
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
                            ?disabled=${preparing}
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

    _normalizeSearchErrorKind(kind) {
        if (
            kind === 'search_timeout'
            || kind === 'search_service_unavailable'
            || kind === 'search_stream_incomplete'
            || kind === 'search_quota_exhausted'
            || kind === 'search_failed'
        ) {
            return kind;
        }
        return 'search_failed';
    }

    _searchErrorTitleKey(kind) {
        const errorKind = this._normalizeSearchErrorKind(kind);
        if (errorKind === 'search_timeout') {
            return 'search_page.error_timeout_title';
        }
        if (errorKind === 'search_service_unavailable') {
            return 'search_page.error_service_title';
        }
        if (errorKind === 'search_stream_incomplete') {
            return 'search_page.error_stream_title';
        }
        if (errorKind === 'search_quota_exhausted') {
            return 'search_page.quota_exhausted_title';
        }
        return 'search_page.error_generic_title';
    }

    _searchErrorTextKey(kind) {
        const errorKind = this._normalizeSearchErrorKind(kind);
        if (errorKind === 'search_timeout') {
            return 'search_page.error_timeout_text';
        }
        if (errorKind === 'search_service_unavailable') {
            return 'search_page.error_service_text';
        }
        if (errorKind === 'search_stream_incomplete') {
            return 'search_page.error_stream_text';
        }
        if (errorKind === 'search_quota_exhausted') {
            return 'search_page.quota_exhausted_text';
        }
        return 'search_page.error_generic_text';
    }

    _searchErrorDetail() {
        const detail = this._search.state.error_detail;
        if (typeof detail !== 'string') {
            throw new Error('PublicSearchPage: search error_detail must be string');
        }
        return detail;
    }

    _retrySearch() {
        if (this._preparingFiles) {
            return;
        }
        const query = this._query.trim();
        if (query === '') {
            return;
        }
        void this._runSearch(query, this._mode);
    }

    _loginFromQuota() {
        redirectToLogin();
    }

    _renderSearchError() {
        const kind = this._normalizeSearchErrorKind(this._search.state.error_kind);
        const detail = this._searchErrorDetail();
        const isQuotaExhausted = kind === 'search_quota_exhausted';
        return html`
            <section class="answer-panel" data-state="error">
                <p class="panel-label">
                    <platform-icon name="notification-error" size="14"></platform-icon>
                    <span>${this.t('search_page.answer_label')}</span>
                </p>
                <div class="answer-error">
                    <div class="answer-error-main">
                        <span class="answer-error-icon">
                            <platform-icon name="notification-warning" size="18"></platform-icon>
                        </span>
                        <div class="answer-error-copy">
                            <h2 class="answer-error-title">${this.t(this._searchErrorTitleKey(kind))}</h2>
                            <p class="answer-error-text">${this.t(this._searchErrorTextKey(kind))}</p>
                            ${isQuotaExhausted
                                ? html`
                                    <button class="answer-error-action" type="button" @click=${this._loginFromQuota}>
                                        ${this.t('search_page.quota_exhausted_login')}
                                    </button>
                                `
                                : html`
                                    <button class="answer-error-action" type="button" @click=${this._retrySearch}>
                                        ${this.t('search_page.error_retry')}
                                    </button>
                                `}
                        </div>
                    </div>
                    ${!isQuotaExhausted && detail !== ''
                        ? html`
                            <details class="answer-error-details">
                                <summary>${this.t('search_page.error_details')}</summary>
                                <pre class="answer-error-code">${detail}</pre>
                            </details>
                        `
                        : nothing}
                </div>
            </section>
        `;
    }

    _renderAnswer(stream) {
        const error = this._search.error;
        if (typeof error === 'string' && error !== '') {
            return this._renderSearchError();
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

    _onFaviconError(event) {
        const target = event.currentTarget;
        if (target instanceof HTMLImageElement) {
            target.remove();
        }
    }

    _ensureSerpSentinelObserver() {
        const stream = this._search.state.stream;
        const sentinel = this.renderRoot.querySelector('.source-scroll-sentinel');
        const shouldObserve = stream.has_more
            && stream.serp_cache_key !== ''
            && !this._serpLoadBlocked
            && !this._serpMore.busy;

        if (!(sentinel instanceof HTMLElement) || !shouldObserve) {
            if (this._serpObserver !== null && this._serpObservedSentinel !== null) {
                this._serpObserver.unobserve(this._serpObservedSentinel);
                this._serpObservedSentinel = null;
            }
            return;
        }

        if (this._serpObserver === null) {
            this._serpObserver = new IntersectionObserver((entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    this._loadMoreSerp();
                }
            }, { root: null, rootMargin: '240px 0px', threshold: 0 });
        }

        if (this._serpObservedSentinel === sentinel) {
            return;
        }

        if (this._serpObservedSentinel !== null) {
            this._serpObserver.unobserve(this._serpObservedSentinel);
        }
        this._serpObservedSentinel = sentinel;
        this._serpObserver.observe(sentinel);
    }

    async _loadMoreSerp() {
        const stream = this._search.state.stream;
        if (
            !stream.has_more
            || this._serpMore.busy
            || stream.serp_cache_key === ''
            || this._serpLoadBlocked
        ) {
            return;
        }
        const pageLimit = stream.page_limit > 0 ? stream.page_limit : 10;
        const result = await this._serpMore.run({
            serp_cache_key: stream.serp_cache_key,
            offset: stream.results.length,
            limit: pageLimit,
            mode: stream.mode,
        });
        if (result === null) {
            this._serpLoadBlocked = true;
            this.toast('search_page.load_more_error', { type: 'error' });
            this._ensureSerpSentinelObserver();
        }
    }

    _renderSource(stream, result, index) {
        const insight = this._insightForUrl(stream, result.url);
        const activeUrl = this._sourceDescribe.state.active_url;
        const describing = this._sourceDescribe.busy && activeUrl === result.url;
        const siteLabel = result.site_name !== '' ? result.site_name : result.display_url;
        const displayUrl = this._displayUrl(result);
        return html`
            <article
                class="source-card"
                style=${`animation-delay: ${Math.min(index * 34, 260)}ms`}
            >
                <div class="source-card-inner">
                    <div class="source-content">
                        <div class="source-site-row">
                            ${result.favicon_url !== '' ? html`
                                <img
                                    class="source-favicon"
                                    src=${result.favicon_url}
                                    alt=""
                                    loading="lazy"
                                    referrerpolicy="no-referrer"
                                    @error=${this._onFaviconError}
                                >
                            ` : html``}
                            <span class="source-site-name">${siteLabel}</span>
                            <span class="source-site-sep">·</span>
                            <span class="source-display-url">${displayUrl}</span>
                        </div>
                        <div class="source-header">
                            <div class="source-main">
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
                        <p class="source-snippet">${result.snippet}</p>
                        ${insight !== null ? html`<p class="source-insight">${insight.relevance_hint}</p>` : html``}
                        ${this._renderSourceAiDescription(result)}
                    </div>
                    ${result.preview_image_url !== '' ? html`
                        <img
                            class="source-thumb"
                            src=${result.preview_image_url}
                            alt=""
                            loading="lazy"
                            referrerpolicy="no-referrer"
                        >
                    ` : html``}
                </div>
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
                <p class="panel-label">
                    <platform-icon name="link" size="14"></platform-icon>
                    <span>${this.t('search_page.sources_label')}</span>
                    <span class="panel-count">${stream.results.length}</span>
                </p>
                ${stream.total_count > 0 ? html`
                    <p class="source-results-meta">
                        ${this.t('search_page.results_shown_of_total', {
                            shown: String(stream.results.length),
                            total: String(stream.total_count),
                        })}
                    </p>
                ` : html``}
                <div class="source-list">
                    ${stream.results.map((result, index) => this._renderSource(stream, result, index))}
                    ${stream.has_more && stream.serp_cache_key !== '' ? html`
                        <div class="source-scroll-sentinel" aria-hidden="true"></div>
                    ` : html``}
                    ${this._serpMore.busy ? html`
                        <div class="skeleton"></div>
                        <div class="skeleton"></div>
                    ` : html``}
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
                            <span class="provider-count">${status.results_count}</span>
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
                        <button class="suggest-chip" type="button" ?disabled=${this._preparingFiles} @click=${() => this._suggest(item.text)}>
                            ${item.text}
                        </button>
                    `)}
                </div>
            </section>
        `;
    }

    _renderBody(stream) {
        const active = this._isStreamActive(stream);
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
        const active = this._isStreamActive(stream);
        const locale = this._localeSel.value;
        const themeMode = this._themeSel.value;
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error(`PublicSearchPage.render: invalid locale "${locale}"`);
        }
        if (themeMode !== 'dark' && themeMode !== 'light') {
            throw new Error(`PublicSearchPage.render: invalid theme "${themeMode}"`);
        }
        const searchHeadClass = active
            ? `search-head is-active${this._searchChromeHidden ? ' is-chrome-hidden' : ''}`
            : 'search-head';
        return html`
            <div class="page" data-entry=${this._entryAnimation}>
                <header class="topbar">
                    <button class="brand" type="button" @click=${this._goHome} aria-label=${this.t('search_page.home')}>
                        <span class="brand-mark">H</span>
                        <span class="brand-name">Humanitec</span>
                    </button>
                    <div class="top-actions">
                        <div class="locale-switch" role="group" aria-label=${this.t('search_page.language_group')}>
                            <button
                                class="locale-option"
                                type="button"
                                aria-pressed=${locale === 'en' ? 'true' : 'false'}
                                @click=${() => this._setLocale('en')}
                            >en</button>
                            <button
                                class="locale-option"
                                type="button"
                                aria-pressed=${locale === 'ru' ? 'true' : 'false'}
                                @click=${() => this._setLocale('ru')}
                            >ru</button>
                        </div>
                        <button
                            class="theme-toggle"
                            type="button"
                            title=${themeMode === 'dark' ? this.t('search_page.theme_light') : this.t('search_page.theme_dark')}
                            aria-label=${themeMode === 'dark' ? this.t('search_page.theme_light') : this.t('search_page.theme_dark')}
                            @click=${this._toggleTheme}
                        >
                            <platform-icon name=${themeMode === 'dark' ? 'sun' : 'moon'} size="17"></platform-icon>
                        </button>
                        <button class="back-link" type="button" @click=${this._goHome}>
                            <platform-icon name="arrow-left" size="16"></platform-icon>
                            <span class="back-label">${this.t('search_page.back')}</span>
                        </button>
                    </div>
                </header>
                <section class=${searchHeadClass}>
                    <h1 class="search-title">${this.t('search_page.title')}</h1>
                    ${this._renderComposer()}
                </section>
                ${this._renderBody(stream)}
            </div>
        `;
    }
}

customElements.define('public-search-page', PublicSearchPage);
