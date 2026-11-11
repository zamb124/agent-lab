import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { markdownToHtml } from '@platform/lib/utils/markdown.js';
import { applyInlineCitations } from '@platform/lib/flow-ui/utils/citations.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import {
    fileListToPublicSearchFiles,
    setPendingPublicSearchRunFiles,
    takePendingPublicSearchFiles,
} from '../_helpers/public-search-files.js';
import { takePublicSearchLandingTransition } from '../_helpers/public-search-transition.js';
import { redirectToLogin } from '@platform/lib/utils/auth-redirect.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { marketingPageHostStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { bindInputVisibleInVisualViewport } from '@platform/lib/utils/ensure-input-visible-in-visual-viewport.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import type { ControllerFor, OpController } from '@platform/lib/base/use-resource.js';
import type { RouterState } from '@platform/lib/events/reducers/router.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const SEARCH_MODES = Object.freeze([
    { key: 'quick', icon: 'search', label: 'search_page.mode_quick' },
    { key: 'deep', icon: 'layers', label: 'search_page.mode_deep' },
    { key: 'research', icon: 'sparkle', label: 'search_page.mode_research' },
]);
const SEARCH_CHROME_HIDE_DELTA_PX = 50;
const SEARCH_CHROME_SHOW_DELTA_PX = 14;
const SEARCH_CHROME_TOP_VISIBLE_PX = 24;
const MOBILE_SERP_MQ = '(max-width: 640px)';
const ANSWER_COLLAPSE_THRESHOLD_PX = 340;

type PublicSearchMode = 'quick' | 'deep' | 'research';

interface PublicSearchResult {
    title: string;
    url: string;
    snippet: string;
    display_url: string;
    provider: string;
    provider_rank: number;
    rank: number;
    score: number;
    published_at: string | null;
    source_type: string;
    site_name: string;
    favicon_url: string;
    preview_image_url: string;
}

interface PublicSearchProviderStatus {
    ok: boolean;
    results_count: number;
}

interface PublicSearchSuggestion {
    text: string;
}

interface PublicSearchInsight {
    url: string;
    relevance_hint: string;
}

interface PublicSearchResearchStep {
    phase: string;
    count: number;
    title: string;
}

interface PublicSearchResearchSource {
    index: number;
    url: string;
    title: string;
    snippet: string;
}

interface PublicSearchStream {
    query: string;
    mode: PublicSearchMode;
    phase: string;
    results: PublicSearchResult[];
    providers: Record<string, PublicSearchProviderStatus>;
    suggestions: PublicSearchSuggestion[];
    followups: PublicSearchSuggestion[];
    result_insights: PublicSearchInsight[];
    answer: string;
    completed: boolean;
    serp_cache_key: string;
    rank_stage: 'preview' | 'refined';
    total_count: number;
    has_more: boolean;
    page_limit: number;
    research_brief: string;
    research_sub_questions: string[];
    research_outline: string[];
    research_steps: PublicSearchResearchStep[];
    research_sources: PublicSearchResearchSource[];
    report: string;
}

function searchRecord(value: unknown, label: string): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error(`search-page: ${label} required`);
    }
    return value;
}

function searchString(value: unknown, label: string): string {
    if (typeof value !== 'string') {
        throw new Error(`search-page: ${label} must be a string`);
    }
    return value;
}

function searchNumber(value: unknown, label: string): number {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`search-page: ${label} must be a finite number`);
    }
    return value;
}

function searchBoolean(value: unknown, label: string): boolean {
    if (value !== true && value !== false) {
        throw new Error(`search-page: ${label} must be a boolean`);
    }
    return value;
}

function searchArray(value: unknown, label: string): unknown[] {
    if (!Array.isArray(value)) {
        throw new Error(`search-page: ${label} must be an array`);
    }
    return value;
}

function isPublicSearchMode(value: unknown): value is PublicSearchMode {
    return value === 'quick' || value === 'deep' || value === 'research';
}

function searchMode(value: unknown, label: string): PublicSearchMode {
    if (!isPublicSearchMode(value)) {
        throw new Error(`search-page: ${label} is invalid`);
    }
    return value;
}

function searchRankStage(value: unknown): 'preview' | 'refined' {
    if (value === 'preview' || value === 'refined') {
        return value;
    }
    throw new Error('search-page: rank_stage is invalid');
}

function searchNullableString(value: unknown, label: string): string | null {
    if (value === null) {
        return null;
    }
    return searchString(value, label);
}

function searchResult(value: unknown, index: number): PublicSearchResult {
    const item = searchRecord(value, `results[${index}]`);
    return {
        title: searchString(item.title, `results[${index}].title`),
        url: searchString(item.url, `results[${index}].url`),
        snippet: searchString(item.snippet, `results[${index}].snippet`),
        display_url: searchString(item.display_url, `results[${index}].display_url`),
        provider: searchString(item.provider, `results[${index}].provider`),
        provider_rank: searchNumber(item.provider_rank, `results[${index}].provider_rank`),
        rank: searchNumber(item.rank, `results[${index}].rank`),
        score: searchNumber(item.score, `results[${index}].score`),
        published_at: searchNullableString(item.published_at, `results[${index}].published_at`),
        source_type: searchString(item.source_type, `results[${index}].source_type`),
        site_name: searchString(item.site_name, `results[${index}].site_name`),
        favicon_url: searchString(item.favicon_url, `results[${index}].favicon_url`),
        preview_image_url: searchString(item.preview_image_url, `results[${index}].preview_image_url`),
    };
}

function searchProviders(value: unknown): Record<string, PublicSearchProviderStatus> {
    const providers = searchRecord(value, 'stream.providers');
    const statuses: Record<string, PublicSearchProviderStatus> = {};
    for (const [name, raw] of Object.entries(providers)) {
        const status = searchRecord(raw, `providers.${name}`);
        statuses[name] = {
            ok: searchBoolean(status.ok, `providers.${name}.ok`),
            results_count: searchNumber(status.results_count, `providers.${name}.results_count`),
        };
    }
    return statuses;
}

function searchSuggestions(value: unknown, label: string): PublicSearchSuggestion[] {
    return searchArray(value, label).map((item, index) => {
        const suggestion = searchRecord(item, `${label}[${index}]`);
        return { text: searchString(suggestion.text, `${label}[${index}].text`) };
    });
}

function searchInsight(value: unknown, index: number): PublicSearchInsight {
    const item = searchRecord(value, `result_insights[${index}]`);
    return {
        url: searchString(item.url, `result_insights[${index}].url`),
        relevance_hint: searchString(item.relevance_hint, `result_insights[${index}].relevance_hint`),
    };
}

function searchStringArray(value: unknown, label: string): string[] {
    return searchArray(value, label).map((item, index) => searchString(item, `${label}[${index}]`));
}

function searchResearchStep(value: unknown, index: number): PublicSearchResearchStep {
    const item = searchRecord(value, `research_steps[${index}]`);
    return {
        phase: searchString(item.phase, `research_steps[${index}].phase`),
        count: searchNumber(item.count, `research_steps[${index}].count`),
        title: searchString(item.title, `research_steps[${index}].title`),
    };
}

function searchResearchSource(value: unknown, index: number): PublicSearchResearchSource {
    const item = searchRecord(value, `research_sources[${index}]`);
    return {
        index: searchNumber(item.index, `research_sources[${index}].index`),
        url: searchString(item.url, `research_sources[${index}].url`),
        title: searchString(item.title, `research_sources[${index}].title`),
        snippet: searchString(item.snippet, `research_sources[${index}].snippet`),
    };
}

function readPublicSearchStream(value: unknown): PublicSearchStream {
    const stream = searchRecord(value, 'stream');
    return {
        query: searchString(stream.query, 'stream.query'),
        mode: searchMode(stream.mode, 'stream.mode'),
        phase: searchString(stream.phase, 'stream.phase'),
        results: searchArray(stream.results, 'stream.results').map((item, index) => searchResult(item, index)),
        providers: searchProviders(stream.providers),
        suggestions: searchSuggestions(stream.suggestions, 'stream.suggestions'),
        followups: searchSuggestions(stream.followups, 'stream.followups'),
        result_insights: searchArray(stream.result_insights, 'stream.result_insights').map((item, index) => searchInsight(item, index)),
        answer: searchString(stream.answer, 'stream.answer'),
        completed: searchBoolean(stream.completed, 'stream.completed'),
        serp_cache_key: searchString(stream.serp_cache_key, 'stream.serp_cache_key'),
        rank_stage: searchRankStage(stream.rank_stage),
        total_count: searchNumber(stream.total_count, 'stream.total_count'),
        has_more: searchBoolean(stream.has_more, 'stream.has_more'),
        page_limit: searchNumber(stream.page_limit, 'stream.page_limit'),
        research_brief: searchString(stream.research_brief, 'stream.research_brief'),
        research_sub_questions: searchStringArray(stream.research_sub_questions, 'stream.research_sub_questions'),
        research_outline: searchStringArray(stream.research_outline, 'stream.research_outline'),
        research_steps: searchArray(stream.research_steps, 'stream.research_steps').map((item, index) => searchResearchStep(item, index)),
        research_sources: searchArray(stream.research_sources, 'stream.research_sources').map((item, index) => searchResearchSource(item, index)),
        report: searchString(stream.report, 'stream.report'),
    };
}

export class PublicSearchPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        _query: { state: true },
        _mode: { state: true },
        _selectedFiles: { state: true },
        _preparingFiles: { state: true },
        _searchChromeHidden: { state: true },
        _entryAnimation: { state: true },
        _answerExpanded: { state: true },
        _answerOverflow: { state: true },
        _activeCitation: { state: true },
    }
    declare _query: string;
    declare _mode: string;
    declare _selectedFiles: File[];
    declare _preparingFiles: boolean;
    declare _searchChromeHidden: boolean;
    declare _entryAnimation: string;
    declare _answerExpanded: boolean;
    declare _answerOverflow: boolean;
    declare _activeCitation: number;
;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        marketingPageHostStyles,
        css`
            :host {
                display: block;
                min-height: var(--app-vh, 100vh);
                color: var(--text-primary);
                background: var(--marketing-page-bg);
            }

            .marketing-page-container {
                min-height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
            }

            .search-page-main {
                flex: 1;
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
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(22px);
                border-bottom: 1px solid var(--glass-border-subtle);
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
                color: var(--text-primary);
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
                background: var(--accent);
                color: var(--text-on-accent);
                font-weight: 700;
                letter-spacing: 0;
            }

            .brand-name {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 24px;
                line-height: 1;
                letter-spacing: 0;
            }

            .back-link {
                min-height: 40px;
                padding: 0 14px;
                border-radius: 999px;
                color: var(--text-secondary);
                background: var(--glass-tint-medium);
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
            }

            .back-link:hover {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
            }

            .locale-switch {
                min-height: 36px;
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 3px;
                border-radius: 999px;
                background: var(--glass-tint-medium);
                border: 1px solid var(--glass-border-subtle);
            }

            .locale-option {
                min-width: 34px;
                min-height: 28px;
                justify-content: center;
                border-radius: 999px;
                color: var(--text-secondary);
                font-size: 13px;
                line-height: 1;
                transition: background 180ms ease, color 180ms ease;
            }

            .locale-option[aria-pressed='true'] {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 36%, transparent);
            }

            .theme-toggle {
                width: 38px;
                height: 38px;
                justify-content: center;
                border-radius: 50%;
                color: var(--text-secondary);
                background: var(--glass-tint-medium);
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
            }

            .theme-toggle:hover,
            .locale-option:hover {
                color: var(--text-primary);
                background: var(--glass-tint-strong);
                transform: translateY(-1px);
            }

            .search-head {
                padding: clamp(34px, 7vw, 86px) clamp(18px, 4vw, 56px) 22px;
                display: grid;
                justify-items: center;
                gap: 18px;
            }

            .search-head.is-active {
                position: static;
                z-index: 16;
                padding: 12px clamp(18px, 4vw, 56px) 8px;
                background: var(--marketing-page-bg);
                border-bottom: 0;
                backdrop-filter: none;
                pointer-events: none;
                gap: 0;
                display: block;
            }

            .page.is-search-active .results-wrap {
                padding-top: 12px;
            }

            .search-title {
                margin: 0;
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-weight: 500;
                font-size: 92px;
                line-height: 0.96;
                letter-spacing: 0;
                text-align: center;
                color: var(--text-primary);
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
                background: var(--glass-bg-strong);
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-ultra);
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
                box-shadow: var(--glass-shadow-strong);
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
                color: var(--text-secondary);
            }

            input[type='search'] {
                min-width: 0;
                height: 54px;
                border: 0;
                outline: none;
                background: transparent;
                color: var(--text-primary);
                font: 500 20px/1.25 var(--font-sans);
                letter-spacing: 0;
            }

            .search-head.is-active input[type='search'] {
                height: 42px;
                font-size: 18px;
            }

            input[type='search']::placeholder {
                color: var(--text-disabled);
            }

            .send-button,
            .icon-tool {
                width: 44px;
                height: 44px;
                border: 0;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: var(--text-on-accent);
                background: var(--marketing-product-accent);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .send-button:hover,
            .icon-tool:hover {
                background: color-mix(in srgb, var(--marketing-product-accent) 88%, white);
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
                color: var(--text-secondary);
                background: var(--glass-bg-medium);
                font: 500 14px/1 var(--font-sans);
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
                background: var(--glass-border-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
            }

            .mode-chip[aria-pressed='true'] {
                color: var(--text-on-accent);
                background: color-mix(in srgb, var(--marketing-product-accent) 36%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--marketing-product-accent) 36%, transparent);
            }

            .icon-tool {
                width: 36px;
                height: 36px;
                color: var(--text-secondary);
                background: var(--glass-bg-medium);
            }

            .icon-tool:hover {
                background: var(--glass-border-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
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
                color: var(--text-primary);
                background: var(--glass-tint-strong);
                border: 1px solid var(--glass-border-subtle);
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
                font: 500 13px/1 var(--font-sans);
            }

            .file-size {
                flex-shrink: 0;
                color: var(--text-tertiary);
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
                color: var(--text-secondary);
                background: transparent;
                cursor: pointer;
                transition: color 160ms ease, background 160ms ease;
            }

            .file-remove:hover {
                color: var(--text-primary);
                background: var(--glass-tint-strong);
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
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-bg-subtle);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                box-sizing: border-box;
                overflow: hidden;
            }

            .sources-panel {
                border: 0;
                background: transparent;
                backdrop-filter: none;
                border-radius: 0;
                overflow: visible;
            }

            .answer-panel {
                position: relative;
                padding: 18px;
                min-height: 96px;
                background:
                    linear-gradient(135deg, color-mix(in srgb, var(--marketing-product-accent) 8%, transparent), transparent 46%),
                    var(--glass-bg-subtle);
            }

            .answer-collapse {
                position: relative;
            }

            .answer-collapse.is-collapsed {
                max-height: 300px;
                overflow: hidden;
            }

            .answer-collapse.is-collapsed::after {
                content: '';
                position: absolute;
                left: 0;
                right: 0;
                bottom: 0;
                height: 72px;
                pointer-events: none;
                background: linear-gradient(
                    to bottom,
                    transparent,
                    var(--glass-bg-subtle)
                );
            }

            .answer-toggle {
                margin-top: 10px;
                min-height: 32px;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                border: 0;
                border-radius: 999px;
                padding: 0 13px;
                color: var(--text-primary);
                background: var(--glass-bg-medium);
                font: 600 13px/1 var(--font-sans);
                cursor: pointer;
                transition: background 180ms ease, transform 180ms ease;
            }

            .answer-toggle:hover {
                background: var(--glass-border-strong);
                transform: translateY(-1px);
            }

            .answer-citation {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 18px;
                height: 18px;
                margin: 0 1px;
                padding: 0 5px;
                border-radius: 6px;
                vertical-align: text-top;
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 18%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 28%, transparent);
                font-size: 11px;
                font-weight: 700;
                line-height: 1;
                text-decoration: none;
                transition: background 160ms ease, color 160ms ease, transform 160ms ease;
            }

            .answer-citation:hover {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 42%, transparent);
                transform: translateY(-1px);
            }

            .answer-panel[data-state='error'] {
                border-color: color-mix(in srgb, var(--error) 20%, transparent);
                background:
                    linear-gradient(135deg, color-mix(in srgb, var(--error) 10%, transparent), var(--glass-solid-medium) 48%),
                    var(--glass-solid-medium);
            }

            .panel-label {
                display: flex;
                align-items: center;
                gap: 8px;
                margin: 0 0 10px;
                color: var(--text-tertiary);
                font-size: 12px;
                font-weight: 600;
                line-height: 1;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }

            .sources-panel .panel-label {
                margin-bottom: 8px;
                font-weight: 500;
                letter-spacing: 0.02em;
            }

            .panel-count {
                min-height: 20px;
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 0 7px;
                color: var(--text-secondary);
                background: var(--glass-tint-strong);
                font-size: 12px;
                line-height: 1;
                text-transform: none;
            }

            .panel-refining {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: 500;
                letter-spacing: 0.02em;
                text-transform: none;
                opacity: 0.85;
            }

            .answer-text {
                margin: 0;
                overflow-wrap: anywhere;
                color: var(--text-primary);
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
                color: var(--text-primary);
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
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
                border: 1px solid var(--glass-border-subtle);
                vertical-align: top;
            }

            .answer-text th,
            .source-ai-markdown th {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
                font-weight: 600;
            }

            .answer-text a,
            .source-ai-markdown a {
                color: var(--accent);
                text-decoration: none;
            }

            .answer-text a:hover,
            .source-ai-markdown a:hover {
                text-decoration: underline;
            }

            .answer-text code,
            .source-ai-markdown code {
                border-radius: var(--radius-sm);
                padding: 2px 6px;
                background: var(--glass-tint-strong);
                font-family: var(--font-mono);
                font-size: 0.88em;
            }

            .answer-text[data-error='true'] {
                color: var(--error);
            }

            .answer-error {
                display: grid;
                gap: 12px;
                color: var(--text-primary);
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
                color: var(--error);
                background: color-mix(in srgb, var(--error) 12%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--error) 20%, transparent);
            }

            .answer-error-copy {
                min-width: 0;
                display: grid;
                gap: 6px;
            }

            .answer-error-title {
                margin: 0;
                color: var(--text-primary);
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 22px;
                font-weight: 600;
                line-height: 1.18;
                letter-spacing: 0;
            }

            .answer-error-text {
                margin: 0;
                color: var(--text-secondary);
                font-size: 15px;
                line-height: 1.48;
            }

            .answer-error-action {
                width: fit-content;
                min-height: 34px;
                border: 0;
                border-radius: 999px;
                padding: 0 14px;
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 28%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 28%, transparent);
                font: 600 13px/1 var(--font-sans);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease;
            }

            .answer-error-action:hover {
                transform: translateY(-1px);
                background: color-mix(in srgb, var(--accent) 38%, transparent);
            }

            .answer-error-details {
                margin: 2px 0 0 46px;
                color: var(--text-secondary);
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
                color: var(--text-secondary);
                font: 12px/1.45 var(--font-mono);
            }

            .answer-placeholder {
                min-height: 54px;
                display: grid;
                align-items: center;
                color: var(--text-disabled);
                font-size: 16px;
                line-height: 1.5;
            }

            .stream-dot {
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: var(--accent);
                box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 42%, transparent);
                animation: streamPulse 1.1s ease infinite;
            }

            .source-list {
                display: grid;
                gap: 2px;
                margin-top: 6px;
            }

            .source-list:has(> .skeleton) {
                gap: 10px;
                margin-top: 10px;
            }

            .source-card {
                display: grid;
                gap: 7px;
                padding: 13px 12px;
                border-radius: 14px;
                color: inherit;
                text-decoration: none;
                background: transparent;
                border: 1px solid transparent;
                transition: background 160ms ease, border-color 160ms ease;
            }

            .source-card.is-cited {
                background: color-mix(in srgb, var(--marketing-product-accent) 14%, transparent);
                border-color: color-mix(in srgb, var(--marketing-product-accent) 42%, transparent);
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
                color: var(--text-secondary);
                font-size: 12px;
                line-height: 1.2;
            }

            .source-favicon {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                flex-shrink: 0;
                object-fit: cover;
                background: var(--glass-tint-strong);
            }

            .source-site-name {
                flex-shrink: 0;
                max-width: 42%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-primary);
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
                color: color-mix(in srgb, var(--accent) 92%, transparent);
            }

            .source-thumb {
                width: 72px;
                height: 72px;
                border-radius: 12px;
                object-fit: cover;
                background: var(--glass-tint-medium);
                border: 1px solid var(--glass-border-subtle);
            }

            .source-results-meta {
                margin: 2px 0 0;
                color: var(--text-secondary);
                font-size: 12px;
                line-height: 1.3;
            }

            .source-scroll-sentinel {
                width: 100%;
                height: 1px;
            }

            .source-card:hover {
                background: var(--glass-bg-medium);
                border-color: var(--glass-border-medium);
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
                border-radius: var(--radius-full);
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 0 10px;
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 20%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent);
                font: 600 13px/1 var(--font-sans);
                cursor: pointer;
                transition: transform 180ms ease, background 180ms ease, opacity 180ms ease;
            }

            .source-ai-button:hover {
                background: color-mix(in srgb, var(--accent) 30%, transparent);
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
                border: 1px solid color-mix(in srgb, var(--marketing-product-accent) 14%, transparent);
                background: transparent;
                color: var(--text-primary);
                animation: resultIn 220ms ease both;
            }

            .source-ai-label {
                display: inline-flex;
                align-items: center;
                gap: 7px;
                margin: 0 0 9px;
                color: var(--text-secondary);
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
                color: var(--text-primary);
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
                color: var(--accent);
                text-decoration: underline;
            }

            .source-url {
                margin: 0;
                color: var(--accent);
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
                color: var(--text-secondary);
                font-size: 13px;
                line-height: 1.42;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .source-insight {
                padding-top: 6px;
                border-top: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
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
                background: var(--glass-tint-strong);
                color: var(--text-secondary);
                font-size: 12px;
                line-height: 1;
            }

            .side-column {
                display: grid;
                gap: 10px;
                position: sticky;
                top: calc(var(--marketing-header-height) + 16px);
            }

            .provider-panel,
            .suggest-panel {
                padding: 14px;
            }

            .sources-panel {
                padding: 2px 0 0;
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
                color: var(--text-secondary);
                background: var(--glass-tint-medium);
                font: 500 13px/1 var(--font-sans);
            }

            .provider-count {
                color: var(--text-tertiary);
            }

            .suggest-chip {
                cursor: pointer;
                transition: background 180ms ease, color 180ms ease, transform 180ms ease;
                text-align: left;
                line-height: 1.16;
            }

            .suggest-chip:hover {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 26%, transparent);
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
                background: var(--warning);
            }

            .provider-chip[data-ok='true'] .provider-state {
                background: var(--success);
            }

            .empty-shell {
                width: min(780px, calc(100vw - 32px));
                margin: 0 auto;
                padding: 26px 0 70px;
            }

            .skeleton {
                height: 86px;
                border-radius: var(--radius-xl);
                background: linear-gradient(
                    90deg,
                    var(--glass-border-subtle),
                    var(--glass-border-medium),
                    var(--glass-border-subtle)
                );
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
                    box-shadow: 0 38px 120px color-mix(in srgb, var(--bg-primary) 54%, transparent);
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

            .page[data-entry='direct'] .results-wrap {
                animation: resultsFadeIn 240ms ease both;
            }

            @keyframes resultsFadeIn {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }

            @media (prefers-reduced-motion: reduce) {
                .search-shell,
                .search-head:not(.is-active) .search-shell,
                .page[data-entry='landing'] .topbar,
                .page[data-entry='landing'] .search-head.is-active .search-shell,
                .page[data-entry='landing'] .results-wrap,
                .page[data-entry='direct'] .results-wrap,
                .source-card,
                .answer-toggle,
                .answer-citation {
                    animation: none !important;
                    transition: none !important;
                }
            }

            @keyframes streamPulse {
                0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 42%, transparent); }
                100% { box-shadow: 0 0 0 13px color-mix(in srgb, var(--accent) 0%, transparent); }
            }

            @keyframes skeleton {
                0% { background-position: 120% 0; }
                100% { background-position: -120% 0; }
            }

            :host-context([data-theme="light"]) .search-shell {
                background: var(--bg-surface);
                border-color: color-mix(in srgb, var(--text-primary) 12%, transparent);
                box-shadow: 0 24px 70px color-mix(in srgb, var(--accent) 14%, transparent);
            }

            :host-context([data-theme="light"]) .search-head.is-active .search-shell {
                box-shadow: 0 18px 54px color-mix(in srgb, var(--accent) 14%, transparent);
            }

            :host-context([data-theme="light"]) .search-icon,
            :host-context([data-theme="light"]) .icon-tool {
                color: color-mix(in srgb, var(--text-primary) 56%, transparent);
            }

            :host-context([data-theme="light"]) input[type='search'] {
                color: var(--marketing-page-bg);
            }

            :host-context([data-theme="light"]) input[type='search']::placeholder {
                color: color-mix(in srgb, var(--text-primary) 46%, transparent);
            }

            :host-context([data-theme="light"]) .mode-chip,
            :host-context([data-theme="light"]) .provider-chip,
            :host-context([data-theme="light"]) .suggest-chip,
            :host-context([data-theme="light"]) .rank-badge,
            :host-context([data-theme="light"]) .provider-badge,
            :host-context([data-theme="light"]) .panel-count,
            :host-context([data-theme="light"]) .file-chip {
                color: color-mix(in srgb, var(--text-primary) 72%, transparent);
                background: color-mix(in srgb, var(--text-primary) 6%, transparent);
                border-color: color-mix(in srgb, var(--text-primary) 8%, transparent);
            }

            :host-context([data-theme="light"]) .mode-chip:hover,
            :host-context([data-theme="light"]) .suggest-chip:hover {
                color: var(--marketing-page-bg);
                background: color-mix(in srgb, var(--accent) 14%, transparent);
            }

            :host-context([data-theme="light"]) .mode-chip[aria-pressed='true'] {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 86%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 24%, transparent);
            }

            :host-context([data-theme="light"]) .answer-panel,
            :host-context([data-theme="light"]) .suggest-panel,
            :host-context([data-theme="light"]) .provider-panel {
                background: var(--bg-surface);
                border-color: color-mix(in srgb, var(--text-primary) 10%, transparent);
            }

            :host-context([data-theme="light"]) .sources-panel {
                background: transparent;
                border: 0;
                box-shadow: none;
                backdrop-filter: none;
            }

            :host-context([data-theme="light"]) .source-list > .skeleton {
                background: linear-gradient(
                    90deg,
                    color-mix(in srgb, var(--text-primary) 5%, transparent),
                    color-mix(in srgb, var(--text-primary) 10%, transparent),
                    color-mix(in srgb, var(--text-primary) 5%, transparent)
                );
                background-size: 220% 100%;
            }

            :host-context([data-theme="light"]) .answer-panel[data-state='error'] {
                border-color: color-mix(in srgb, var(--error) 18%, transparent);
                background:
                    linear-gradient(135deg, color-mix(in srgb, var(--error) 8%, transparent), var(--text-secondary) 48%),
                    var(--text-secondary);
            }

            :host-context([data-theme="light"]) .answer-error-icon {
                color: var(--error);
                background: color-mix(in srgb, var(--error) 10%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--error) 16%, transparent);
            }

            :host-context([data-theme="light"]) .answer-error-title {
                color: color-mix(in srgb, var(--text-primary) 94%, transparent);
            }

            :host-context([data-theme="light"]) .answer-error-text {
                color: color-mix(in srgb, var(--text-primary) 66%, transparent);
            }

            :host-context([data-theme="light"]) .answer-error-action {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 86%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 24%, transparent);
            }

            :host-context([data-theme="light"]) .answer-error-action:hover {
                background: color-mix(in srgb, var(--accent-active) 92%, transparent);
            }

            :host-context([data-theme="light"]) .answer-error-details,
            :host-context([data-theme="light"]) .answer-error-code {
                color: color-mix(in srgb, var(--text-primary) 54%, transparent);
            }

            :host-context([data-theme="light"]) .source-card {
                background: transparent;
                border-color: transparent;
            }

            :host-context([data-theme="light"]) .source-card:hover {
                background: color-mix(in srgb, var(--text-primary) 4%, transparent);
                border-color: color-mix(in srgb, var(--text-primary) 8%, transparent);
            }

            :host-context([data-theme="light"]) .source-card.is-cited {
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                border-color: color-mix(in srgb, var(--accent) 32%, transparent);
            }

            :host-context([data-theme="light"]) .answer-citation {
                color: var(--accent-active);
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 26%, transparent);
            }

            :host-context([data-theme="light"]) .answer-citation:hover {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 86%, transparent);
            }

            :host-context([data-theme="light"]) .answer-toggle {
                color: color-mix(in srgb, var(--text-primary) 90%, transparent);
                background: color-mix(in srgb, var(--text-primary) 6%, transparent);
            }

            :host-context([data-theme="light"]) .answer-collapse.is-collapsed::after {
                background: linear-gradient(to bottom, transparent, var(--bg-surface));
            }

            :host-context([data-theme="light"]) .panel-label,
            :host-context([data-theme="light"]) .answer-placeholder,
            :host-context([data-theme="light"]) .provider-count {
                color: color-mix(in srgb, var(--text-primary) 54%, transparent);
            }

            :host-context([data-theme="light"]) .sources-panel .panel-label {
                color: color-mix(in srgb, var(--text-primary) 44%, transparent);
            }

            :host-context([data-theme="light"]) .answer-text,
            :host-context([data-theme="light"]) .source-title,
            :host-context([data-theme="light"]) .source-ai-markdown {
                color: color-mix(in srgb, var(--text-primary) 92%, transparent);
            }

            :host-context([data-theme="light"]) .source-snippet,
            :host-context([data-theme="light"]) .source-insight {
                color: color-mix(in srgb, var(--text-primary) 70%, transparent);
            }

            :host-context([data-theme="light"]) .source-url,
            :host-context([data-theme="light"]) .answer-text a,
            :host-context([data-theme="light"]) .source-ai-markdown a,
            :host-context([data-theme="light"]) a.source-title {
                color: var(--accent-hover);
            }

            :host-context([data-theme="light"]) .source-ai-button {
                color: var(--accent-active);
                background: color-mix(in srgb, var(--accent) 16%, transparent);
                box-shadow:
                    inset 0 0 0 1px color-mix(in srgb, var(--accent) 26%, transparent),
                    0 8px 20px color-mix(in srgb, var(--accent) 10%, transparent);
            }

            :host-context([data-theme="light"]) .source-ai-button:hover {
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 86%, transparent);
                box-shadow:
                    inset 0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent),
                    0 10px 24px color-mix(in srgb, var(--accent) 18%, transparent);
            }

            :host-context([data-theme="light"]) .source-ai-button:disabled {
                color: color-mix(in srgb, var(--accent-active) 78%, transparent);
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent);
                opacity: 0.86;
            }

            :host-context([data-theme="light"]) .source-ai-panel {
                color: color-mix(in srgb, var(--text-primary) 84%, transparent);
                background: color-mix(in srgb, var(--marketing-product-accent) 8%, transparent);
                border-color: color-mix(in srgb, var(--marketing-product-accent) 22%, transparent);
            }

            :host-context([data-theme="light"]) .source-site-row {
                color: color-mix(in srgb, var(--text-primary) 62%, transparent);
            }

            :host-context([data-theme="light"]) .source-site-name {
                color: color-mix(in srgb, var(--text-primary) 88%, transparent);
            }

            :host-context([data-theme="light"]) .source-display-url {
                color: var(--accent-hover);
            }

            :host-context([data-theme="light"]) .source-results-meta {
                color: color-mix(in srgb, var(--text-primary) 54%, transparent);
            }

            :host-context([data-theme="light"]) .source-favicon,
            :host-context([data-theme="light"]) .source-thumb {
                background: color-mix(in srgb, var(--text-primary) 6%, transparent);
                border-color: color-mix(in srgb, var(--text-primary) 10%, transparent);
            }

            @media (min-width: 768px) {
                .page[data-entry='landing'] .search-head.is-active .search-shell {
                    animation: none;
                    transform: none;
                    filter: none;
                }

                .page[data-entry='landing'] .results-wrap {
                    animation: none;
                    transform: none;
                    filter: none;
                }
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

            @media (max-width: 767px) {
                .page.is-search-active {
                    min-height: 0;
                }

                .search-page-main:has(.page.is-search-active) {
                    flex: 0 1 auto;
                }

                .marketing-page-container:has(.page.is-search-active) {
                    min-height: 0;
                }

                .search-head.is-active {
                    padding: 0;
                    margin: 0;
                    width: 100%;
                    background: var(--marketing-header-bg);
                }

                .search-head.is-active .search-shell {
                    animation: none;
                    transform: none;
                    transition: none;
                    filter: none;
                    will-change: auto;
                    background: transparent;
                    box-shadow: none;
                    border: 0;
                    border-bottom: 1px solid var(--glass-border-medium);
                }

                .page[data-entry='landing'] .search-head.is-active .search-shell {
                    animation: none;
                }

                .page[data-entry='landing'] .results-wrap {
                    animation: none;
                }

                .results-wrap {
                    padding-top: 0;
                }
            }

            @media (max-width: 640px) {
                .search-head {
                    padding: 0;
                }

                .search-head:not(.is-active) {
                    padding: 20px 0 12px;
                }

                .search-title {
                    font-size: 40px;
                    padding: 0 12px;
                    box-sizing: border-box;
                }

                .search-shell {
                    width: 100%;
                    max-width: none;
                    border-radius: 0;
                    padding: 8px 12px;
                    box-shadow: none;
                    border: 0;
                    border-bottom: 1px solid var(--glass-border-medium);
                    background: var(--marketing-header-bg);
                }

                .search-head.is-active {
                    position: static;
                    top: auto;
                    z-index: 16;
                    padding: 0;
                    margin: 0;
                    gap: 0;
                }

                .search-head.is-active .search-shell {
                    width: 100%;
                    border-radius: 0;
                    padding: 8px 12px;
                    box-shadow: none;
                    border: 0;
                    border-bottom: 1px solid var(--glass-border-medium);
                    background: transparent;
                }

                .search-head.is-active.is-chrome-hidden .search-shell {
                    opacity: 1;
                    transform: none;
                    filter: none;
                    pointer-events: auto;
                }

                .search-line {
                    grid-template-columns: 38px minmax(0, 1fr) 42px;
                }

                input[type='search'] {
                    height: 48px;
                    font-size: 17px;
                }

                .tool-row {
                    align-items: center;
                    flex-direction: row;
                    overflow-x: auto;
                    padding-top: 6px;
                    gap: 8px;
                }

                .search-head.is-active .tool-row {
                    padding-top: 6px;
                }

                .mode-group {
                    flex: 1 1 auto;
                    overflow-x: auto;
                    padding-bottom: 2px;
                }

                .side-tools {
                    flex-shrink: 0;
                    justify-content: flex-end;
                }

                .file-name {
                    max-width: 180px;
                }

                .results-wrap {
                    width: 100%;
                    max-width: none;
                    margin: 0;
                    padding: 0 0 32px;
                    gap: 0;
                }

                .primary-column,
                .side-column {
                    gap: 0;
                }

                .answer-panel,
                .sources-panel,
                .suggest-panel,
                .provider-panel {
                    border-radius: 0;
                    border-left: 0;
                    border-right: 0;
                    border-top: 0;
                    border-bottom: 1px solid var(--glass-border-medium);
                    box-shadow: none;
                    backdrop-filter: none;
                    background: var(--marketing-page-bg);
                }

                .answer-panel {
                    padding: 16px 12px;
                    min-height: 0;
                }

                .answer-panel[data-state='error'] {
                    background: var(--marketing-page-bg);
                    border-color: color-mix(in srgb, var(--error) 22%, transparent);
                }

                .sources-panel,
                .provider-panel,
                .suggest-panel {
                    padding: 12px;
                }

                .source-ai-panel {
                    border-radius: 0;
                    border: 0;
                    border-top: 1px solid color-mix(in srgb, var(--marketing-product-accent) 14%, transparent);
                    padding: 12px 0 0;
                    background: transparent;
                }

                .panel-label {
                    margin-bottom: 8px;
                }

                .answer-text {
                    font-size: 16px;
                    line-height: 1.5;
                }

                .source-list {
                    gap: 0;
                    margin-top: 0;
                }

                .source-list:has(> .skeleton) {
                    gap: 10px;
                    margin-top: 8px;
                }

                .source-list > .skeleton {
                    border-radius: var(--radius-lg);
                }

                .source-card {
                    border-radius: 0;
                    border: 0;
                    border-bottom: 1px solid var(--glass-border-medium);
                    background: transparent;
                    padding: 14px 0;
                    box-shadow: none;
                }

                .source-card:last-child {
                    border-bottom: 0;
                }

                .source-card:hover {
                    transform: none;
                    background: var(--glass-tint-subtle);
                }

                .empty-shell {
                    width: 100%;
                    max-width: none;
                    padding: 24px 12px 48px;
                }

                :host-context(html[data-keyboard-visual='1']) .search-head.is-active .tool-row {
                    flex-wrap: nowrap;
                    overflow-x: auto;
                    -webkit-overflow-scrolling: touch;
                }

                :host-context(html[data-keyboard-visual='1']) .mode-chip {
                    height: 30px;
                    padding: 0 10px;
                    font-size: 12px;
                }

                :host-context(html[data-theme="light"]) .search-shell,
                :host-context(html[data-theme="light"]) .search-head.is-active .search-shell {
                    border-bottom-color: color-mix(in srgb, var(--text-primary) 10%, transparent);
                    box-shadow: none;
                }

                :host-context(html[data-theme="light"]) .answer-panel,
                :host-context(html[data-theme="light"]) .sources-panel,
                :host-context(html[data-theme="light"]) .suggest-panel,
                :host-context(html[data-theme="light"]) .provider-panel {
                    border-bottom-color: color-mix(in srgb, var(--text-primary) 10%, transparent);
                }

                :host-context(html[data-theme="light"]) .answer-panel[data-state='error'] {
                    background: var(--marketing-page-bg);
                    border-color: color-mix(in srgb, var(--error) 22%, transparent);
                }

                :host-context(html[data-theme="light"]) .source-card {
                    border-bottom-color: color-mix(in srgb, var(--text-primary) 8%, transparent);
                    background: transparent;
                }

                :host-context(html[data-theme="light"]) .source-ai-panel {
                    border-top-color: color-mix(in srgb, var(--marketing-product-accent) 18%, transparent);
                    background: transparent;
                }

                :host-context(html[data-theme="light"]) .source-card:hover {
                    background: color-mix(in srgb, var(--text-primary) 3%, transparent);
                }
            }

            .research-brief {
                margin: 0 0 14px;
                font-size: 15px;
                line-height: 1.55;
                color: var(--text-primary);
            }

            .research-timeline {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            .research-step {
                display: flex;
                align-items: flex-start;
                gap: 10px;
                font-size: 13px;
                line-height: 1.4;
                color: var(--text-secondary);
            }

            .research-step .step-icon {
                flex: 0 0 auto;
                margin-top: 1px;
                color: var(--marketing-product-accent);
            }

            .research-step[data-active="true"] {
                color: var(--text-primary);
                font-weight: 600;
            }

            .research-subquestions {
                list-style: none;
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .research-subquestions li {
                position: relative;
                padding-left: 16px;
                font-size: 13px;
                line-height: 1.45;
                color: var(--text-secondary);
            }

            .research-subquestions li::before {
                content: "";
                position: absolute;
                left: 2px;
                top: 8px;
                width: 5px;
                height: 5px;
                border-radius: 50%;
                background: var(--marketing-product-accent);
            }

            .research-report .answer-text {
                font-size: 15px;
                line-height: 1.65;
            }

            .research-report table {
                border-collapse: collapse;
                width: 100%;
                margin: 12px 0;
                font-size: 13.5px;
            }

            .research-report th,
            .research-report td {
                border: 1px solid var(--glass-border-medium);
                padding: 6px 10px;
                text-align: left;
            }
        `,
    ];

    constructor() {
        super();
        this._search = this.useOp('frontend/public_search_run');
        this._serpMore = this.useOp('frontend/public_search_serp_more');
        this._serpClick = this.useOp('frontend/public_search_serp_click');
        this._sourceDescribe = this.useOp('frontend/public_search_source_describe');
        this._route = this.select((state) => state.router);
        this._query = '';
        this._mode = 'quick';
        this._selectedFiles = [];
        this._preparingFiles = false;
        this._searchChromeHidden = false;
        this._entryAnimation = 'direct';
        this._answerExpanded = false;
        this._answerOverflow = false;
        this._activeCitation = 0;
        this._lastRouteSig = '';
        this._runSeq = 0;
        this._lastScrollY = 0;
        this._scrollAnchorY = 0;
        this._scrollDirection = 'still';
        this._scrollFrame = 0;
        this._serpObserver = null;
        this._serpObservedSentinel = null;
        this._serpLoadBlocked = false;
        this._lastSerpCacheKey = '';
        this._serpRects = new Map();
        /** @type {string | undefined} */
        this._serpOrderSignature = undefined;
        /** @type {string | undefined} */
        this._serpDataSignature = undefined;
        /** @type {string | undefined} */
        this._measuredAnswer = undefined;
        this._handleWindowScroll = this._handleWindowScroll.bind(this);
        /** @type {(() => void) | null} */
        this._releaseSearchInputViewport = null;
    }
    private _search: ControllerFor<'frontend/public_search_run'>;
    private _serpMore: OpController;
    private _serpClick: OpController;
    private _sourceDescribe: OpController;
    private _route: SelectController<RouterState>;
    private _lastRouteSig: string;
    private _runSeq: number;
    private _lastScrollY: number;
    private _scrollAnchorY: number;
    private _scrollDirection: string;
    private _scrollFrame: number;
    private _serpObserver: IntersectionObserver | null;
    private _serpObservedSentinel: HTMLElement | null;
    private _serpLoadBlocked: boolean;
    private _lastSerpCacheKey: string;
    private _serpRects: Map<string, DOMRect>;
    private _serpOrderSignature: string | undefined;
    private _serpDataSignature: string | undefined;
    private _measuredAnswer: string | undefined;
    private _releaseSearchInputViewport: (() => void) | null;


    override firstUpdated(changedProperties: PropertyValues<this>): void {
        super.firstUpdated(changedProperties);
        this._bindSearchInputViewport();
    }

    _bindSearchInputViewport() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        const input = root.querySelector('[data-role="public-search-input"]');
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        if (this._releaseSearchInputViewport !== null) {
            this._releaseSearchInputViewport();
        }
        this._releaseSearchInputViewport = bindInputVisibleInVisualViewport(input);
    }

    _isMobileSerpViewport() {
        if (typeof window === 'undefined') {
            return false;
        }
        return window.matchMedia(MOBILE_SERP_MQ).matches;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._lastScrollY = window.scrollY;
        this._scrollAnchorY = this._lastScrollY;
        this.useDomEvent(window, 'scroll', this._handleWindowScroll, { passive: true });
        const pendingFiles = takePendingPublicSearchFiles();
        if (pendingFiles.length > 0) {
            this._selectedFiles = pendingFiles;
        }
        this._syncFromRoute();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._releaseSearchInputViewport !== null) {
            this._releaseSearchInputViewport();
            this._releaseSearchInputViewport = null;
        }
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

    override updated(changedProperties: PropertyValues<this>): void {
        super.updated(changedProperties);
        this._syncFromRoute();
        const stream = this._searchStream();
        if (stream.serp_cache_key !== this._lastSerpCacheKey) {
            this._lastSerpCacheKey = stream.serp_cache_key;
            this._serpLoadBlocked = false;
        }
        this._ensureSerpSentinelObserver();
        // Layout-чтения (FLIP-rects, scrollHeight) — только при смене данных:
        // иначе каждый стрим-токен гоняет forced reflow, и sticky topbar
        // с backdrop-filter перерисовывается десятки раз в секунду.
        const resultsSig = `${stream.rank_stage}|${stream.results.map((item) => item.url).join('|')}`;
        if (resultsSig !== this._serpDataSignature) {
            this._serpDataSignature = resultsSig;
            this._animateSerpReorder();
        }
        if (stream.answer !== this._measuredAnswer) {
            this._measuredAnswer = stream.answer;
            this._measureAnswerOverflow();
        }
    }

    /**
     * FLIP-переупорядочивание SERP: когда refined-этап меняет порядок карточек
     * (keyed repeat переносит те же DOM-узлы), плавно анимируем их из прошлой
     * позиции в новую. Анимация запускается только при смене порядка, чтобы
     * стриминг ответа над списком не дёргал карточки.
     */
    _animateSerpReorder() {
        const cards = this.renderRoot.querySelectorAll('.source-card[data-url]');
        const nextRects = new Map<string, DOMRect>();
        const order: string[] = [];
        for (const el of cards) {
            const url = el.getAttribute('data-url');
            if (url === null) {
                continue;
            }
            order.push(url);
            nextRects.set(url, el.getBoundingClientRect());
        }
        const orderSignature = order.join('|');
        const prevRects = this._serpRects;
        const orderChanged = this._serpOrderSignature !== undefined
            && orderSignature !== this._serpOrderSignature;
        if (orderChanged) {
            for (const el of cards) {
                const url = el.getAttribute('data-url');
                if (url === null) {
                    continue;
                }
                const oldRect = prevRects.get(url);
                const newRect = nextRects.get(url);
                if (oldRect === undefined || newRect === undefined) {
                    continue;
                }
                const dx = oldRect.left - newRect.left;
                const dy = oldRect.top - newRect.top;
                if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1) {
                    continue;
                }
                el.animate(
                    [
                        { transform: `translate(${dx}px, ${dy}px)` },
                        { transform: 'translate(0, 0)' },
                    ],
                    { duration: 340, easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)' },
                );
            }
        }
        this._serpRects = nextRects;
        this._serpOrderSignature = orderSignature;
    }

    _measureAnswerOverflow() {
        const el = this.renderRoot.querySelector('[data-role="answer-text"]');
        if (!(el instanceof HTMLElement)) {
            if (this._answerOverflow) {
                this._answerOverflow = false;
            }
            return;
        }
        const overflow = el.scrollHeight > ANSWER_COLLAPSE_THRESHOLD_PX;
        if (overflow !== this._answerOverflow) {
            this._answerOverflow = overflow;
        }
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
        const stream = this._searchStream();
        const scrollY = Math.max(0, window.scrollY);
        if (this._isMobileSerpViewport()) {
            this._lastScrollY = scrollY;
            this._scrollAnchorY = scrollY;
            this._scrollDirection = 'still';
            if (this._searchChromeHidden) {
                this._searchChromeHidden = false;
            }
            return;
        }
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

    _searchStream(): PublicSearchStream {
        const stream: unknown = this._search.state.stream;
        return readPublicSearchStream(stream);
    }

    _isMode(value: unknown): value is PublicSearchMode {
        return isPublicSearchMode(value);
    }

    _isStreamActive(stream: PublicSearchStream) {
        return stream.phase !== 'idle' || this._search.busy || stream.results.length > 0;
    }

    _handleInput(event: Event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLTextAreaElement)) {
            throw new Error('search-page: search field required');
        }
        this._query = target.value;
    }

    _setMode(mode: string) {
        if (!this._isMode(mode)) {
            throw new Error(`Invalid search mode: ${mode}`);
        }
        this._mode = mode;
    }

    _submit(event: Event) {
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

    async _runSearch(query: string, mode: string) {
        if (this._preparingFiles) {
            return;
        }
        this._answerExpanded = false;
        this._answerOverflow = false;
        this._activeCitation = 0;
        this._searchChromeHidden = false;
        this._lastScrollY = Math.max(0, window.scrollY);
        this._scrollAnchorY = this._lastScrollY;
        this._scrollDirection = 'still';
        this._runSeq += 1;
        const runId = `public_search_${Date.now().toString(36)}_${this._runSeq.toString(36)}`;
        this._preparingFiles = true;
        try {
            setPendingPublicSearchRunFiles(this._selectedFiles);
            this._preparingFiles = false;
            void this._search.run({ run_id: runId, query, mode });
        } catch (error) {
            this._preparingFiles = false;
            this.toast('search_page.file_upload_error', {
                type: 'error',
                vars: { message: this._fileErrorMessage(error) },
            });
        }
    }

    _fileErrorMessage(error: unknown) {
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

    _handleFilesSelected(event: Event) {
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

    _removeFile(index: number) {
        if (!Number.isInteger(index) || index < 0 || index >= this._selectedFiles.length) {
            throw new Error('PublicSearchPage._removeFile: index out of range');
        }
        this._selectedFiles = this._selectedFiles.filter((_, itemIndex) => itemIndex !== index);
    }

    _displayUrl(result: PublicSearchResult) {
        return result.display_url !== '' ? result.display_url : result.url;
    }

    _markdownTemplate(text: string) {
        return unsafeHTML(markdownToHtml(text));
    }

    _answerTemplate(stream: PublicSearchStream) {
        let out = markdownToHtml(stream.answer);
        if (stream.results.length > 0) {
            const results = stream.results;
            out = applyInlineCitations(out, (index) => {
                if (!Number.isInteger(index) || index < 1 || index > results.length) {
                    return null;
                }
                const result = results[index - 1];
                if (result === undefined || !/^https?:\/\//.test(result.url)) {
                    return null;
                }
                return { url: result.url, label: result.title };
            });
        }
        return unsafeHTML(out);
    }

    _citationRankFromEvent(event: Event) {
        for (const node of event.composedPath()) {
            if (node instanceof HTMLElement && node.hasAttribute('data-citation')) {
                const value = Number(node.getAttribute('data-citation'));
                return Number.isInteger(value) && value > 0 ? value : 0;
            }
        }
        return 0;
    }

    _onAnswerClick(event: Event) {
        const rank = this._citationRankFromEvent(event);
        if (rank === 0) {
            return;
        }
        const stream = this._searchStream();
        const result = stream.results[rank - 1];
        if (rank > stream.results.length || result === undefined) {
            return;
        }
        this._reportSourceClick(stream, result, rank - 1);
    }

    _onAnswerPointer(event: Event) {
        const rank = this._citationRankFromEvent(event);
        if (rank !== this._activeCitation) {
            this._activeCitation = rank;
        }
    }

    _onAnswerPointerLeave() {
        if (this._activeCitation !== 0) {
            this._activeCitation = 0;
        }
    }

    _toggleAnswerExpand() {
        this._answerExpanded = !this._answerExpanded;
    }

    _insightForUrl(stream: PublicSearchStream, url: string) {
        for (const insight of stream.result_insights) {
            if (insight.url === url) {
                return insight;
            }
        }
        return null;
    }

    _suggest(text: string) {
        if (this._preparingFiles) {
            return;
        }
        this._query = text;
        const search = `?q=${encodeURIComponent(text)}&mode=${encodeURIComponent(this._mode)}`;
        this.navigate('search', {}, { search });
    }

    _describeSource(stream: PublicSearchStream, result: PublicSearchResult) {
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

    _renderModeChip(mode: { key: string; icon: string; label: string }) {
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

    _renderSelectedFile(file: File, index: number) {
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
                        data-role="public-search-input"
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

    _normalizeSearchErrorKind(kind: string) {
        if (
            kind === 'search_timeout'
            || kind === 'search_service_unavailable'
            || kind === 'search_runtime_unavailable'
            || kind === 'search_stream_incomplete'
            || kind === 'search_quota_exhausted'
            || kind === 'search_failed'
        ) {
            return kind;
        }
        return 'search_failed';
    }

    _searchErrorTitleKey(kind: string) {
        const errorKind = this._normalizeSearchErrorKind(kind);
        if (errorKind === 'search_timeout') {
            return 'search_page.error_timeout_title';
        }
        if (errorKind === 'search_service_unavailable') {
            return 'search_page.error_service_title';
        }
        if (errorKind === 'search_runtime_unavailable') {
            return 'search_page.error_runtime_title';
        }
        if (errorKind === 'search_stream_incomplete') {
            return 'search_page.error_stream_title';
        }
        if (errorKind === 'search_quota_exhausted') {
            return 'search_page.quota_exhausted_title';
        }
        return 'search_page.error_generic_title';
    }

    _searchErrorTextKey(kind: string) {
        const errorKind = this._normalizeSearchErrorKind(kind);
        if (errorKind === 'search_timeout') {
            return 'search_page.error_timeout_text';
        }
        if (errorKind === 'search_service_unavailable') {
            return 'search_page.error_service_text';
        }
        if (errorKind === 'search_runtime_unavailable') {
            return 'search_page.error_runtime_text';
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
        const errorKind = this._search.state.error_kind;
        if (typeof errorKind !== 'string') {
            throw new Error('PublicSearchPage: search error_kind must be string');
        }
        const kind = this._normalizeSearchErrorKind(errorKind);
        const detail = this._searchErrorDetail();
        const isQuotaExhausted = kind === 'search_quota_exhausted';
        return html`
            <section class="answer-panel" data-state="error">
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

    _renderAnswer(stream: PublicSearchStream) {
        const error = this._search.error;
        if (typeof error === 'string' && error !== '') {
            return this._renderSearchError();
        }
        const hasAnswer = stream.answer.trim() !== '';
        const collapsible = this._answerOverflow && !this._answerExpanded;
        return html`
            <section class="answer-panel">
                <p class="panel-label">
                    ${stream.completed ? html`<platform-icon name="sparkle" size="14"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>${this.t('search_page.ai_overview_label')}</span>
                </p>
                ${hasAnswer
                    ? html`
                        <div class="answer-collapse ${collapsible ? 'is-collapsed' : ''}">
                            <div
                                class="answer-text"
                                data-role="answer-text"
                                @click=${this._onAnswerClick}
                                @pointerover=${this._onAnswerPointer}
                                @pointerleave=${this._onAnswerPointerLeave}
                            >${this._answerTemplate(stream)}</div>
                        </div>
                        ${this._answerOverflow ? html`
                            <button class="answer-toggle" type="button" @click=${this._toggleAnswerExpand}>
                                <span>${this._answerExpanded ? this.t('search_page.answer_show_less') : this.t('search_page.answer_show_full')}</span>
                                <platform-icon name=${this._answerExpanded ? 'chevron-up' : 'chevron-down'} size="15"></platform-icon>
                            </button>
                        ` : nothing}
                    `
                    : html`<div class="answer-placeholder">${this.t('search_page.answer_pending')}</div>`}
            </section>
        `;
    }

    _renderSourceAiDescription(result: PublicSearchResult) {
        const descriptions = this._sourceDescribe.state.descriptions;
        const activeUrl = this._sourceDescribe.state.active_url;
        if (!isPlainRecord(descriptions)) {
            return nothing;
        }
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
        if (!isPlainRecord(description)) {
            return nothing;
        }
        if (typeof description.answer !== 'string') {
            throw new Error('search-page: source description answer required');
        }
        const answer = description.answer;
        const activity = typeof description.activity === 'string' ? description.activity : '';
        const completed = description.completed === true;
        const hasAnswer = answer.trim() !== '';
        if (!hasAnswer && !completed && this._sourceDescribe.busy) {
            return html`
                <div class="source-ai-panel">
                    <p class="source-ai-label"><span class="stream-dot"></span><span>AI</span></p>
                    <div class="source-ai-markdown">${activity}</div>
                </div>
            `;
        }
        if (!hasAnswer) {
            return nothing;
        }
        return html`
            <div class="source-ai-panel">
                <p class="source-ai-label">
                    ${completed ? html`<platform-icon name="check" size="13"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>AI</span>
                </p>
                <div class="source-ai-markdown">
                    ${this._markdownTemplate(answer)}
                </div>
            </div>
        `;
    }

    _onFaviconError(event: Event) {
        const target = event.currentTarget;
        if (target instanceof HTMLImageElement) {
            target.remove();
        }
    }

    _ensureSerpSentinelObserver() {
        const stream = this._searchStream();
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
        const stream = this._searchStream();
        if (
            !stream.has_more
            || this._serpMore.busy
            || stream.serp_cache_key === ''
            || this._serpLoadBlocked
        ) {
            return;
        }
        if (stream.page_limit <= 0) {
            throw new Error('search-page: page_limit must be positive');
        }
        const pageLimit = stream.page_limit;
        const mode = stream.mode;
        if (!this._isMode(mode)) {
            throw new Error(`Invalid search mode: ${String(mode)}`);
        }
        const result = await this._serpMore.run({
            serp_cache_key: stream.serp_cache_key,
            offset: stream.results.length,
            limit: pageLimit,
            mode,
        });
        if (result === null) {
            this._serpLoadBlocked = true;
            this.toast('search_page.load_more_error', { type: 'error' });
            this._ensureSerpSentinelObserver();
        }
    }

    _reportSourceClick(stream: PublicSearchStream, result: PublicSearchResult, index: number) {
        if (stream.query === '') {
            return;
        }
        const position = result.rank > 0 ? result.rank : index + 1;
        void this._serpClick.run({
            query: stream.query,
            mode: stream.mode,
            url: result.url,
            position,
            provider: result.provider,
            search_index_id: '',
            serp_cache_key: stream.serp_cache_key,
        });
    }

    _renderSource(stream: PublicSearchStream, result: PublicSearchResult, index: number) {
        const insight = this._insightForUrl(stream, result.url);
        const activeUrl = this._sourceDescribe.state.active_url;
        const describing = this._sourceDescribe.busy && activeUrl === result.url;
        const siteLabel = result.site_name !== '' ? result.site_name : result.display_url;
        const displayUrl = this._displayUrl(result);
        const rankNum = result.rank > 0 ? result.rank : index + 1;
        const cited = this._activeCitation === rankNum;
        return html`
            <article
                class="source-card ${cited ? 'is-cited' : ''}"
                data-rank=${rankNum}
                data-url=${result.url}
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
                                <a
                                    class="source-title"
                                    href=${result.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    @click=${() => this._reportSourceClick(stream, result, index)}
                                >${result.title}</a>
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
                        <p class="source-snippet">${unsafeHTML(markdownToHtml(result.snippet))}</p>
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

    _renderSources(stream: PublicSearchStream) {
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
                    ${stream.rank_stage === 'preview' && !stream.completed ? html`
                        <span class="panel-refining">
                            <span class="stream-dot"></span>
                            <span>${this.t('search_page.refining_order')}</span>
                        </span>
                    ` : html``}
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
                    ${repeat(
                        stream.results,
                        (result: PublicSearchResult) => result.url,
                        (result, index) => this._renderSource(stream, result, index),
                    )}
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

    _renderProviders(stream: PublicSearchStream) {
        const providers: { name: string; ok: boolean; resultsCount: number }[] = [];
        for (const [name, status] of Object.entries(stream.providers)) {
            providers.push({
                name,
                ok: status.ok,
                resultsCount: status.results_count,
            });
        }
        if (providers.length === 0) {
            return html``;
        }
        return html`
            <section class="provider-panel">
                <p class="panel-label"><platform-icon name="server" size="14"></platform-icon><span>${this.t('search_page.providers_label')}</span></p>
                <div class="provider-list">
                    ${providers.map((provider) => html`
                        <span class="provider-chip" data-ok=${provider.ok ? 'true' : 'false'}>
                            <span class="provider-state"></span>
                            <span>${provider.name}</span>
                            <span class="provider-count">${provider.resultsCount}</span>
                        </span>
                    `)}
                </div>
            </section>
        `;
    }

    _renderSuggestions(stream: PublicSearchStream) {
        const query = stream.query.trim().toLowerCase();
        const seen = new Set<string>();
        const suggestions: string[] = [];
        for (const item of [...stream.followups, ...stream.suggestions]) {
            const text = item.text.trim();
            const key = text.toLowerCase();
            if (text.length === 0 || seen.has(key)) {
                continue;
            }
            seen.add(key);
            // Самоссылки пайплайна («…по запросу "query"», повтор самого
            // запроса) — не уточнения, а шум генерации.
            if (query.length > 0
                && (key === query || key.includes(`"${query}"`) || key.includes(`«${query}»`))) {
                continue;
            }
            suggestions.push(text);
        }
        if (suggestions.length === 0) {
            return html``;
        }
        return html`
            <section class="suggest-panel">
                <p class="panel-label"><platform-icon name="search" size="14"></platform-icon><span>${this.t('search_page.related_label')}</span></p>
                <div class="suggest-list">
                    ${suggestions.map((text) => html`
                        <button class="suggest-chip" type="button" ?disabled=${this._preparingFiles} @click=${() => this._suggest(text)}>
                            ${text}
                        </button>
                    `)}
                </div>
            </section>
        `;
    }

    _researchReportTemplate(stream: PublicSearchStream) {
        let out = markdownToHtml(stream.report);
        const sources = stream.research_sources;
        if (sources.length > 0) {
            out = applyInlineCitations(out, (index) => {
                if (!Number.isInteger(index) || index < 1) {
                    return null;
                }
                const match = sources.find((item) => item.index === index);
                if (match === undefined || !/^https?:\/\//.test(match.url)) {
                    return null;
                }
                return { url: match.url, label: match.title };
            });
        }
        return unsafeHTML(out);
    }

    _researchPhaseLabelKey(phase: string) {
        if (phase === 'plan') {
            return 'search_page.research_phase_plan';
        }
        if (phase === 'searching' || phase === 'search') {
            return 'search_page.research_phase_search';
        }
        if (phase === 'reading' || phase === 'read') {
            return 'search_page.research_phase_read';
        }
        if (phase === 'reflecting' || phase === 'reflect') {
            return 'search_page.research_phase_reflect';
        }
        if (phase === 'synthesizing') {
            return 'search_page.research_phase_synthesize';
        }
        return 'search_page.research_phase_start';
    }

    _renderResearchStep(step: PublicSearchResearchStep) {
        if (step.phase === 'plan') {
            return this.t('search_page.research_step_plan', { count: String(step.count) });
        }
        if (step.phase === 'search') {
            return this.t('search_page.research_step_search', { count: String(step.count) });
        }
        if (step.phase === 'read') {
            return this.t('search_page.research_step_read', { title: step.title });
        }
        if (step.phase === 'reflect') {
            return this.t('search_page.research_step_reflect', { count: String(step.count) });
        }
        return step.phase;
    }

    _renderResearchTimeline(stream: PublicSearchStream) {
        const steps = stream.research_steps;
        return html`
            <section class="answer-panel">
                <p class="panel-label">
                    ${stream.completed ? html`<platform-icon name="check" size="14"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>${this.t('search_page.research_timeline_label')}</span>
                </p>
                <div class="research-timeline">
                    ${steps.length === 0
                        ? html`<div class="research-step" data-active="true">
                            <platform-icon class="step-icon" name="sparkle" size="14"></platform-icon>
                            <span>${this.t(this._researchPhaseLabelKey(stream.phase))}</span>
                        </div>`
                        : repeat(
                            steps,
                            (step, index) => `${step.phase}-${index}-${step.count}`,
                            (step) => html`
                                <div class="research-step">
                                    <platform-icon class="step-icon" name="check" size="14"></platform-icon>
                                    <span>${this._renderResearchStep(step)}</span>
                                </div>
                            `,
                        )}
                    ${!stream.completed && steps.length > 0 ? html`
                        <div class="research-step" data-active="true">
                            <span class="stream-dot"></span>
                            <span>${this.t(this._researchPhaseLabelKey(stream.phase))}</span>
                        </div>
                    ` : nothing}
                </div>
            </section>
        `;
    }

    _researchReportPendingKey(stream: PublicSearchStream) {
        if (stream.phase === 'synthesizing') {
            return 'search_page.research_report_synthesizing';
        }
        if (stream.phase === 'plan') {
            return 'search_page.research_phase_plan';
        }
        if (stream.phase === 'searching' || stream.phase === 'search') {
            return 'search_page.research_phase_search';
        }
        if (stream.phase === 'reading' || stream.phase === 'read') {
            return 'search_page.research_phase_read';
        }
        if (stream.phase === 'reflecting' || stream.phase === 'reflect') {
            return 'search_page.research_phase_reflect';
        }
        return 'search_page.research_report_pending';
    }

    _renderResearchPlan(stream: PublicSearchStream) {
        const subQuestions = stream.research_sub_questions;
        const outline = stream.research_outline;
        if (subQuestions.length === 0 && outline.length === 0) {
            return nothing;
        }
        return html`
            ${subQuestions.length > 0 ? html`
                <section class="suggest-panel">
                    <p class="panel-label">
                        <platform-icon name="layers" size="14"></platform-icon>
                        <span>${this.t('search_page.research_subquestions_label')}</span>
                    </p>
                    <ul class="research-subquestions">
                        ${subQuestions.map((question: string) => html`<li>${question}</li>`)}
                    </ul>
                </section>
            ` : nothing}
            ${outline.length > 0 ? html`
                <section class="suggest-panel">
                    <p class="panel-label">
                        <platform-icon name="list" size="14"></platform-icon>
                        <span>${this.t('search_page.research_outline_label')}</span>
                    </p>
                    <ul class="research-subquestions">
                        ${outline.map((section: string) => html`<li>${section}</li>`)}
                    </ul>
                </section>
            ` : nothing}
        `;
    }

    _renderResearchReport(stream: PublicSearchStream) {
        const error = this._search.error;
        if (typeof error === 'string' && error !== '') {
            return this._renderSearchError();
        }
        const showReport = stream.completed || stream.phase === 'synthesizing';
        const hasReport = showReport && stream.report.trim() !== '';
        return html`
            <section class="answer-panel research-report">
                <p class="panel-label">
                    ${stream.completed ? html`<platform-icon name="sparkle" size="14"></platform-icon>` : html`<span class="stream-dot"></span>`}
                    <span>${this.t('search_page.research_report_label')}</span>
                </p>
                ${stream.research_brief !== '' ? html`<p class="research-brief">${stream.research_brief}</p>` : nothing}
                ${hasReport
                    ? html`<div class="answer-text" data-role="answer-text" @click=${this._onResearchReportClick}>${this._researchReportTemplate(stream)}</div>`
                    : html`<div class="answer-placeholder">${this.t(this._researchReportPendingKey(stream))}</div>`}
            </section>
        `;
    }

    _onResearchReportClick(event: Event) {
        const rank = this._citationRankFromEvent(event);
        if (rank === 0) {
            return;
        }
        const stream = this._searchStream();
        const match = stream.research_sources.find((item) => item.index === rank);
        if (match === undefined || match.url.length === 0) {
            return;
        }
        window.open(match.url, '_blank', 'noopener');
    }

    _renderResearchSources(stream: PublicSearchStream) {
        const sources = stream.research_sources;
        if (sources.length === 0 && !this._search.busy) {
            return nothing;
        }
        return html`
            <section class="sources-panel">
                <p class="panel-label">
                    <platform-icon name="link" size="14"></platform-icon>
                    <span>${this.t('search_page.sources_label')}</span>
                    <span class="panel-count">${sources.length}</span>
                </p>
                <div class="source-list">
                    ${sources.length === 0 && this._search.busy ? html`
                        <div class="skeleton"></div>
                        <div class="skeleton"></div>
                    ` : nothing}
                    ${repeat(
                        sources,
                        (source) => source.url,
                        (source) => html`
                            <article class="source-card">
                                <div class="source-body">
                                    <div class="source-head">
                                        <span class="source-rank">${source.index}</span>
                                        <a class="source-title" href=${source.url} target="_blank" rel="noopener">${source.title}</a>
                                    </div>
                                    <p class="source-snippet">${unsafeHTML(markdownToHtml(source.snippet !== '' ? source.snippet : source.url))}</p>
                                </div>
                            </article>
                        `,
                    )}
                </div>
            </section>
        `;
    }

    _renderResearch(stream: PublicSearchStream) {
        return html`
            <main class="results-wrap">
                <div class="primary-column">
                    ${this._renderResearchReport(stream)}
                    ${this._renderResearchSources(stream)}
                </div>
                <aside class="side-column">
                    ${this._renderResearchTimeline(stream)}
                    ${this._renderResearchPlan(stream)}
                </aside>
            </main>
        `;
    }

    _renderBody(stream: PublicSearchStream) {
        const active = this._isStreamActive(stream);
        if (!active) {
            return html`<platform-empty-state class="empty-shell" icon="search" title=${this.t('search_page.empty_hint')}></platform-empty-state>`;
        }
        if (stream.mode === 'research') {
            return this._renderResearch(stream);
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

    override render(): TemplateResult {
        const stream = this._searchStream();
        const active = this._isStreamActive(stream);
        const searchHeadClass = active
            ? `search-head is-active${this._searchChromeHidden ? ' is-chrome-hidden' : ''}`
            : 'search-head';
        const pageClass = active ? 'page is-search-active' : 'page';
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <div class="search-page-main">
                    <div class=${pageClass} data-entry=${this._entryAnimation}>
                        <section class=${searchHeadClass}>
                            ${active ? nothing : html`<h1 class="search-title">${this.t('search_page.title')}</h1>`}
                            ${this._renderComposer()}
                        </section>
                        ${this._renderBody(stream)}
                    </div>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('public-search-page', PublicSearchPage);
