/**
 * Страница настроек — настройки компании.
 *
 * Состав:
 *   - Профиль компании (имя, monthly_budget, metadata JSON).
 *   - AI providers (capabilities + custom OpenAI-compatible providers) — рендерится
 *     поверх единого core-компонента <platform-llm-config-editor>.
 *   - Platform LLM model scoring — только active company system.
 *
 * Все взаимодействие с AI-настройками — через resource-операции
 * apps/frontend/ui/events/resources/settings.resource.js.
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { formatDurationSeconds } from '@platform/lib/utils/format-duration.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '../../components/company-storage-settings.js';
import '@platform/lib/components/llm/llm-config-editor.js';
import '@platform/lib/components/llm/llm-context-editor.js';

const SEARCH_PROVIDER_CATALOG = Object.freeze({
    tinyfish: { label: 'TinyFish', logo: 'TF', tone: 'cyan', docs_url: 'https://app.tinyfish.ai' },
    linkup: { label: 'Linkup', logo: 'LU', tone: 'green', docs_url: 'https://app.linkup.so' },
    serper: { label: 'Serper', logo: 'G', tone: 'blue', docs_url: 'https://serper.dev' },
    tavily: { label: 'Tavily', logo: 'TV', tone: 'violet', docs_url: 'https://tavily.com' },
});
import '@platform/lib/components/platform-help-hint.js';
import {
    llmProviderErrorClassIsBlocking,
    llmProviderErrorClassLabel,
} from '../../components/llm-provider-status-strip.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord, recordField } from '@platform/lib/events/payload.js';

function companyIdOf(company: unknown): string | null {
    if (!isPlainRecord(company) || typeof company.company_id !== 'string') return null;
    return company.company_id;
}

function searchProviderMeta(providerId: unknown): { label: string; logo: string; tone: string; docs_url: string } {
    switch (providerId) {
        case 'tinyfish':
            return SEARCH_PROVIDER_CATALOG.tinyfish;
        case 'linkup':
            return SEARCH_PROVIDER_CATALOG.linkup;
        case 'serper':
            return SEARCH_PROVIDER_CATALOG.serper;
        case 'tavily':
            return SEARCH_PROVIDER_CATALOG.tavily;
        default:
            throw new Error(`settings-page: unknown search provider ${String(providerId)}`);
    }
}

function displayText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function missingAsNull(value: unknown): unknown {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return null;
    if (typeof value === 'number' && !Number.isFinite(value)) return null;
    return value;
}

function arrayField(value: unknown, label: string): unknown[] {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
    return value;
}

interface SearchProviderDraft {
    provider_id: string;
    enabled: boolean;
    credential_source: 'company' | 'platform';
    api_key: string;
    base_url: string;
    timeout_seconds: number | null;
    depth: string;
    search_depth: string;
    topic: string;
    include_answer: boolean | null;
}

interface ModelScoreDraft {
    capability: string;
    provider: string;
    model_id: string;
    editorial_prior: number;
    enabled: boolean;
    note: string;
}

function requireSearchProviderId(provider: Record<string, unknown>): string {
    if (typeof provider.provider_id !== 'string' || provider.provider_id.length === 0) {
        throw new Error('settings: search provider_id required');
    }
    return provider.provider_id;
}

function scoreField(row: Record<string, unknown>, field: string): string {
    const value = row[field];
    if (typeof value !== 'string') {
        throw new Error(`model scoring: ${field} must be a string`);
    }
    return value;
}

function scoreRows(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) {
        throw new Error('model scoring: items must be an array');
    }
    return value.map((row, index) => {
        if (!isPlainRecord(row)) {
            throw new Error(`model scoring: item ${index} must be an object`);
        }
        return row;
    });
}

function searchProviderDraftFrom(provider: Record<string, unknown>): SearchProviderDraft {
    return {
        provider_id: requireSearchProviderId(provider),
        enabled: provider.enabled === true,
        credential_source: provider.credential_source === 'company' ? 'company' : 'platform',
        api_key: '',
        base_url: typeof provider.base_url === 'string' ? provider.base_url : '',
        timeout_seconds: typeof provider.timeout_seconds === 'number' ? provider.timeout_seconds : null,
        depth: typeof provider.depth === 'string' ? provider.depth : '',
        search_depth: typeof provider.search_depth === 'string' ? provider.search_depth : '',
        topic: typeof provider.topic === 'string' ? provider.topic : '',
        include_answer: typeof provider.include_answer === 'boolean' ? provider.include_answer : null,
    };
}

function budgetNumber(value: unknown): number {
    if (value === undefined || value === null || value === '') return 0;
    const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
    if (!Number.isFinite(parsed)) throw new Error('settings: monthly_budget must be a number');
    return parsed;
}

const INTEGRATION_LIST = Object.freeze([
    { id: 'crm', route: '/crm' },
    { id: 'flows', route: '/flows' },
    { id: 'rag', route: '/rag' },
    { id: 'sync', route: '/sync' },
]);

export class FrontendSettingsPage extends PlatformPage {
    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host { display: block; container-type: inline-size; }

            .tabs {
                display: flex;
                gap: var(--space-1);
                margin-bottom: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .tab {
                padding: var(--space-2) var(--space-3);
                background: transparent;
                color: var(--text-secondary);
                border: none;
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border-bottom: 2px solid transparent;
            }
            .tab[data-active="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
            }

            section { margin-bottom: var(--space-4); }
            section > h3 {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                margin: 0 0 var(--space-2) 0;
            }
            section > .header {
                display: flex; align-items: center; justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }
            section > .header h3 {
                margin: 0;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }
            section .section-help {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-bottom: var(--space-2);
            }

            .form { display: flex; flex-direction: column; gap: var(--space-2); width: 100%; min-width: 0; }
            .form-narrow { max-width: 560px; }
            .field-error { color: var(--error); font-size: var(--text-xs); }

            .info-grid {
                display: grid;
                grid-template-columns: 140px 1fr;
                gap: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            .info-grid dt { color: var(--text-tertiary); }
            .info-grid dd { margin: 0; color: var(--text-primary); font-family: var(--font-mono); font-size: var(--text-xs); }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
                align-self: flex-start;
                margin-top: var(--space-3);
            }
            .btn:hover { filter: brightness(1.1); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--glass-border-subtle); }

            /* === Двухколоночные сетки на широких экранах === */
            .two-col {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-3);
            }
            .three-col {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-2);
            }
            @container (min-width: 880px) {
                .two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            @container (min-width: 1320px) {
                .two-col { grid-template-columns: repeat(3, minmax(0, 1fr)); }
            }

            .integration-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: var(--space-2);
            }
            .integration-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .integration-card .integration-name { color: var(--text-primary); font-weight: var(--font-semibold); font-size: var(--text-sm); }
            .integration-card .integration-id { color: var(--text-tertiary); font-size: var(--text-xs); font-family: var(--font-mono); }

            .empty {
                padding: var(--space-3);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
            }

            .capability-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                display: flex; flex-direction: column; gap: var(--space-2);
                min-width: 0;
            }
            .capability-card .header {
                display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
            }
            .capability-card h4 {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .capability-card .desc { color: var(--text-tertiary); font-size: var(--text-xs); }
            .capability-card .actions { display: flex; justify-content: flex-end; gap: var(--space-2); }

            .search-provider-hero {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-3);
                padding: var(--space-4);
                margin-bottom: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background:
                    linear-gradient(135deg, color-mix(in srgb, var(--accent) 16%, transparent), transparent 52%),
                    var(--glass-solid-subtle);
            }
            @container (min-width: 880px) {
                .search-provider-hero { grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.6fr); }
            }
            .search-provider-hero h3 {
                margin: 0 0 var(--space-1);
                color: var(--text-primary);
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
            }
            .search-provider-hero p {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.55;
            }
            .billing-note {
                display: grid;
                gap: var(--space-1);
                align-self: start;
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--glass-solid-subtle) 80%, transparent);
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .billing-note strong { color: var(--text-primary); font-size: var(--text-sm); }

            .search-provider-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-3);
            }
            @container (min-width: 1040px) {
                .search-provider-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            .search-provider-card {
                min-width: 0;
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .search-provider-card[data-source="company"] {
                border-color: color-mix(in srgb, var(--accent) 42%, var(--glass-border-subtle));
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 14%, transparent);
            }
            .provider-card-head {
                display: grid;
                grid-template-columns: auto minmax(0, 1fr) auto;
                gap: var(--space-2);
                align-items: start;
            }
            .provider-logo {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-md);
                display: grid;
                place-items: center;
                font-weight: var(--font-semibold);
                color: white;
                letter-spacing: 0;
                box-shadow: inset 0 0 0 1px var(--glass-tint-strong);
            }
            .provider-logo[data-tone="cyan"] { background: linear-gradient(135deg, #00a6ff, #00d6a3); }
            .provider-logo[data-tone="green"] { background: linear-gradient(135deg, var(--success), #84cc16); }
            .provider-logo[data-tone="blue"] { background: linear-gradient(135deg, #2563eb, #60a5fa); }
            .provider-logo[data-tone="violet"] { background: linear-gradient(135deg, var(--accent), var(--accent-tertiary)); }
            .provider-title {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .provider-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 0;
            }
            .provider-title-row h4 {
                margin: 0;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }
            .provider-description {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.45;
            }
            .info-dot {
                width: 22px;
                height: 22px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: transparent;
                color: var(--text-tertiary);
                cursor: help;
                font-size: var(--text-xs);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .provider-status {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
                justify-content: flex-end;
            }
            .provider-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 5px 9px;
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--glass-solid-subtle) 78%, transparent);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border: 1px solid var(--glass-border-subtle);
            }
            .provider-pill[data-ok="true"]::before {
                content: "";
                width: 7px;
                height: 7px;
                border-radius: var(--radius-full);
                background: var(--success);
            }
            .provider-form {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-2);
            }
            @container (min-width: 720px) {
                .provider-form.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            .credential-switch {
                display: inline-flex;
                padding: 4px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: color-mix(in srgb, var(--glass-solid-subtle) 80%, transparent);
                gap: 4px;
                width: fit-content;
            }
            .credential-switch button {
                border: 0;
                border-radius: calc(var(--radius-md) - 3px);
                padding: 7px 11px;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                cursor: pointer;
            }
            .credential-switch button[data-active="true"] {
                background: var(--accent);
                color: white;
            }
            .provider-actions {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                flex-wrap: wrap;
                padding-top: var(--space-1);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .order-controls {
                display: inline-flex;
                gap: var(--space-1);
            }

            .context-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .context-card .context-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .custom-provider-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .custom-provider-card {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-2) var(--space-3);
                align-items: start;
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
            }
            .custom-provider-card .meta { min-width: 0; display: flex; flex-direction: column; gap: var(--space-1); }
            .custom-provider-card .title-line {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                font-size: var(--text-sm);
                word-break: break-word;
            }
            .custom-provider-card .ref-line {
                font-family: var(--font-mono);
                color: var(--text-secondary);
                word-break: break-all;
            }
            .custom-provider-card .url-line {
                font-family: var(--font-mono);
                color: var(--text-primary);
                word-break: break-all;
            }
            .custom-provider-card .caps-line { color: var(--text-tertiary); }
            .custom-provider-card .key-line { color: var(--text-secondary); }
            .custom-provider-card .actions { display: flex; flex-wrap: wrap; gap: var(--space-1); justify-content: flex-end; }

            .scores-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                flex-wrap: wrap;
                margin-bottom: var(--space-2);
            }
            .scores-toolbar-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
            }
            .score-filter {
                display: flex;
                gap: var(--space-1);
            }
            .score-filter glass-button[data-active="true"] {
                color: var(--text-primary);
                border-color: var(--accent);
            }
            llm-provider-status-strip {
                display: block;
                margin: var(--space-2) 0;
            }
            .scores-table-wrap {
                overflow-x: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .scores-table {
                width: 100%;
                border-collapse: collapse;
                min-width: 1080px;
                font-size: var(--text-xs);
            }
            .scores-table tr.score-row-cooldown td {
                background: var(--warning-bg);
            }
            .scores-table tr.score-row-error td {
                background: var(--error-bg);
            }
            .score-status {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                white-space: nowrap;
            }
            .score-status-pill {
                display: inline-flex;
                align-items: center;
                padding: 0 var(--space-2);
                height: 1.5rem;
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .scores-table tr.score-row-cooldown .score-status-pill {
                color: var(--warning);
            }
            .scores-table tr.score-row-error .score-status-pill {
                color: var(--error);
            }
            .scores-table th,
            .scores-table td {
                padding: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                vertical-align: top;
            }
            .scores-table th {
                color: var(--text-tertiary);
                text-align: left;
                font-weight: var(--font-semibold);
                background: var(--glass-solid-subtle);
            }
            .scores-table tr:last-child td { border-bottom: 0; }
            .score-model {
                font-family: var(--font-mono);
                color: var(--text-primary);
                word-break: break-all;
            }
            .score-provider {
                font-family: var(--font-mono);
                color: var(--text-secondary);
                white-space: nowrap;
            }
            .score-actions {
                display: flex;
                gap: var(--space-1);
                justify-content: flex-end;
                align-items: center;
                white-space: nowrap;
            }
            .score-form {
                display: grid;
                grid-template-columns: minmax(120px, 180px) minmax(220px, 1fr) minmax(100px, 140px) minmax(220px, 1fr) auto;
                gap: var(--space-2);
                align-items: end;
            }
            @container (max-width: 960px) {
                .score-form { grid-template-columns: 1fr; }
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    static override properties: PropertyDeclarations = {
        _activeTab: { state: true },
        _storageName: { state: true },
        _storageEndpoint: { state: true },
        _storageBucket: { state: true },
        _storageRegion: { state: true },
        _storageAccessKey: { state: true },
        _storageSecret: { state: true },
        _storageKind: { state: true },
        _storageTargetId: { state: true },
        _name: { state: true },
        _monthlyBudget: { state: true },
        _metadataJson: { state: true },
        _metadataError: { state: true },
        _capabilityDrafts: { state: true },
        _llmContextDraft: { state: true },
        _searchProviderDrafts: { state: true },
        _searchProviderOrder: { state: true },
        _modelScoreDrafts: { state: true },
        _modelScoreNew: { state: true },
        _scoreStatusFilter: { state: true },
    }
    declare _activeTab: string;
    declare _storageName: string;
    declare _storageEndpoint: string;
    declare _storageBucket: string;
    declare _storageRegion: string;
    declare _storageAccessKey: string;
    declare _storageSecret: string;
    declare _storageKind: string;
    declare _storageTargetId: string;
    declare _name: string;
    declare _monthlyBudget: number;
    declare _metadataJson: string;
    declare _metadataError: string;
    declare _capabilityDrafts: Record<string, Record<string, unknown>>;
    declare _llmContextDraft: Record<string, unknown>;
    declare _searchProviderDrafts: Record<string, SearchProviderDraft>;
    declare _searchProviderOrder: string[];
    declare _modelScoreDrafts: Record<string, ModelScoreDraft>;
    declare _modelScoreNew: ModelScoreDraft;
    declare _scoreStatusFilter: string;
;

    constructor() {
        super();
        this._load = this.useOp('frontend/settings_load');
        this._update = this.useOp('frontend/settings_update');
        this._aiLoad = this.useOp('frontend/ai_providers_load');
        this._capPut = this.useOp('frontend/ai_provider_capability_put');
        this._capDelete = this.useOp('frontend/ai_provider_capability_delete');
        this._contextPut = this.useOp('frontend/ai_provider_llm_context_put');
        this._contextDelete = this.useOp('frontend/ai_provider_llm_context_delete');
        this._customCreate = this.useOp('frontend/ai_custom_provider_create');
        this._customDelete = this.useOp('frontend/ai_custom_provider_delete');
        this._searchLoad = this.useOp('search/providers_load');
        this._searchProviderPut = this.useOp('search/provider_update');
        this._searchProviderOrderPut = this.useOp('search/provider_order_update');
        this._searchProviderDelete = this.useOp('search/provider_reset');
        this._scoreLoad = this.useOp('frontend/llm_model_scores_load');
        this._scoreUpsert = this.useOp('frontend/llm_model_score_upsert');
        this._scoreDelete = this.useOp('frontend/llm_model_score_delete');
        this._scoreRefreshCache = this.useOp('frontend/llm_model_scores_refresh_cache');
        this._scoreProbe = this.useOp('frontend/llm_model_scores_probe_providers');
        this._loaded = false;
        this._aiLoaded = false;
        this._searchLoaded = false;
        this._scoresLoaded = false;
        this._lastSeededCompanyRef = null;
        this._lastSeededAiRef = null;
        this._lastSeededSearchRef = null;
        this._activeTab = 'company';
        this._storageName = '';
        this._storageEndpoint = '';
        this._storageBucket = '';
        this._storageRegion = 'us-east-1';
        this._storageAccessKey = '';
        this._storageSecret = '';
        this._storageKind = '';
        this._storageTargetId = 'platform';
        this._name = '';
        this._monthlyBudget = 0;
        this._metadataJson = '{}';
        this._metadataError = '';
        this._capabilityDrafts = {};
        this._llmContextDraft = {};
        this._searchProviderDrafts = {};
        this._searchProviderOrder = [];
        this._modelScoreDrafts = {};
        this._scoreStatusFilter = 'all';
        this._modelScoreNew = {
            capability: 'llm_chat',
            provider: 'openrouter',
            model_id: '',
            editorial_prior: 0,
            enabled: true,
            note: '',
        };
    }
    private _load: OpController;
    private _update: OpController;
    private _aiLoad: OpController;
    private _capPut: OpController;
    private _capDelete: OpController;
    private _contextPut: OpController;
    private _contextDelete: OpController;
    private _customCreate: OpController;
    private _customDelete: OpController;
    private _searchLoad: OpController;
    private _searchProviderPut: OpController;
    private _searchProviderOrderPut: OpController;
    private _searchProviderDelete: OpController;
    private _scoreLoad: OpController;
    private _scoreUpsert: OpController;
    private _scoreDelete: OpController;
    private _scoreRefreshCache: OpController;
    private _scoreProbe: OpController;
    private _loaded: boolean;
    private _aiLoaded: boolean;
    private _searchLoaded: boolean;
    private _scoresLoaded: boolean;
    private _lastSeededCompanyRef: unknown;
    private _lastSeededAiRef: unknown;
    private _lastSeededSearchRef: unknown;


    override updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._load.run();
        }
        if (!this._aiLoaded) {
            this._aiLoaded = true;
            this._aiLoad.run({ public_host: window.location.host });
        }
        if (!this._searchLoaded) {
            this._searchLoaded = true;
            this._searchLoad.run();
        }
        const company = this._load.lastResult;
        const companyId = companyIdOf(company);
        if (companyId === 'system' && !this._scoresLoaded) {
            this._scoresLoaded = true;
            this._scoreLoad.run();
        }
        if (companyId !== null && companyId !== 'system' && this._activeTab === 'model_scoring') {
            this._activeTab = 'company';
        }
        if (isPlainRecord(company) && company !== this._lastSeededCompanyRef) {
            this._lastSeededCompanyRef = company;
            this._seedDraft(company);
        }
        const ai = this._aiLoad.lastResult;
        if (isPlainRecord(ai) && ai !== this._lastSeededAiRef) {
            this._lastSeededAiRef = ai;
            this._seedAiDraft(ai);
        }
        const search = this._searchLoad.lastResult;
        if (isPlainRecord(search) && search !== this._lastSeededSearchRef) {
            this._lastSeededSearchRef = search;
            this._seedSearchDraft(search);
        }
    }

    _seedDraft(company: Record<string, unknown>) {
        this._name = displayText(company.name);
        this._monthlyBudget = budgetNumber(company.monthly_budget);
        const metadata = recordField(company.metadata, 'settings: company.metadata');
        this._metadataJson = JSON.stringify(metadata, null, 2);
    }

    _seedAiDraft(data: Record<string, unknown>) {
        const context = data.llm_context;
        if (!isPlainRecord(context) || !isPlainRecord(context.config)) {
            this._llmContextDraft = {};
            return;
        }
        this._llmContextDraft = { ...context.config };
    }

    _seedSearchDraft(data: Record<string, unknown>) {
        const providers = Array.isArray(data.providers) ? data.providers : [];
        const drafts: Record<string, SearchProviderDraft> = {};
        for (const provider of providers) {
            if (!isPlainRecord(provider) || typeof provider.provider_id !== 'string') {
                continue;
            }
            drafts[provider.provider_id] = searchProviderDraftFrom(provider);
        }
        this._searchProviderDrafts = drafts;
        const order: string[] = [];
        if (Array.isArray(data.provider_order)) {
            for (const providerId of data.provider_order) {
                if (typeof providerId !== 'string' || providerId.length === 0) {
                    throw new Error('settings: provider_order id must be a string');
                }
                order.push(providerId);
            }
        }
        this._searchProviderOrder = order;
    }

    _setTab(tab: string) {
        this._activeTab = tab;
    }

    _save() {
        let metadata = null;
        const trimmed = this._metadataJson.trim();
        if (trimmed) {
            try {
                const parsed = JSON.parse(trimmed);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    metadata = parsed;
                    this._metadataError = '';
                } else {
                    this._metadataError = this.t('settings_page.metadata_invalid');
                    return;
                }
            } catch (err) {
                if (!(err instanceof SyntaxError)) throw err;
                this._metadataError = this.t('settings_page.metadata_invalid');
                return;
            }
        }
        const body: Record<string, unknown> = {
            name: this._name.trim(),
            monthly_budget: this._monthlyBudget,
        };
        if (metadata !== null) body.metadata = metadata;
        this._update.run(body);
    }

    _renderTabs() {
        const isSystem = companyIdOf(this._load.lastResult) === 'system';
        const tabs = [
            { id: 'company', label: this.t('settings_page.tab_company') },
            { id: 'ai_providers', label: this.t('settings_page.tab_ai_providers') },
            { id: 'search_providers', label: this.t('settings_page.tab_search_providers') },
            ...(isSystem ? [{ id: 'model_scoring', label: this.t('settings_page.tab_model_scoring') }] : []),
            { id: 'security', label: this.t('settings_page.tab_security') },
            { id: 'integrations', label: this.t('settings_page.tab_integrations') },
            { id: 'storages', label: this.t('settings_page.tab_storages') },
        ];
        return html`
            <div class="tabs">
                ${tabs.map((t) => html`
                    <button class="tab"
                        data-active=${this._activeTab === t.id ? 'true' : 'false'}
                        @click=${() => this._setTab(t.id)}
                    >${t.label}</button>
                `)}
            </div>
        `;
    }

    _renderStoragesTab() {
        return html`<company-storage-settings></company-storage-settings>`;
    }

    _renderCompanyTab(company: Record<string, unknown>) {
        const saving = this._update.busy;
        return html`
            <div class="two-col">
                <section>
                    <h3>${this.t('settings_page.section_company')}</h3>
                    <div class="info-grid">
                        <dt>${this.t('settings_page.company_id')}</dt><dd>${displayText(company.company_id)}</dd>
                        <dt>${this.t('settings_page.company_status')}</dt><dd>${displayText(company.status)}</dd>
                        <dt>${this.t('settings_page.company_owner')}</dt><dd>${company.owner_user_id ? html`<platform-user-chip user-id=${company.owner_user_id} size="sm"></platform-user-chip>` : ''}</dd>
                        <dt>${this.t('settings_page.tariff_plan')}</dt><dd>${displayText(company.tariff_plan)}</dd>
                        <dt>${this.t('settings_page.created_at')}</dt><dd>${typeof company.created_at === 'string' && company.created_at.length > 0 ? new Date(company.created_at).toLocaleString() : ''}</dd>
                    </div>
                </section>

                <section>
                    <h3>${this.t('settings_page.company_section')}</h3>
                    <div class="form form-narrow">
                        <platform-field
                            type="string"
                            mode="edit"
                            label=${this.t('settings_page.label_company_name')}
                            .value=${this._name}
                            @change=${(e: CustomEvent) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('settings: company name expects detail.value string');
                                }
                                this._name = e.detail.value;
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="view"
                            label=${this.t('settings_page.label_subdomain')}
                            .value=${displayText(company.subdomain)}
                        ></platform-field>
                        <platform-field
                            type="integer"
                            mode="edit"
                            label=${this.t('settings_page.label_monthly_budget')}
                            .value=${this._monthlyBudget}
                            @change=${(e: CustomEvent) => {
                                if (!e.detail || e.detail.value === null || typeof e.detail.value !== 'number') {
                                    throw new Error('settings: monthly budget expects integer detail.value');
                                }
                                this._monthlyBudget = e.detail.value;
                            }}
                        ></platform-field>
                        <small class="section-help">${this.t('settings_page.budget_help')}</small>
                    </div>
                </section>
            </div>

            <section>
                <h3>${this.t('settings_page.metadata_title')}</h3>
                <div class="section-help">${this.t('settings_page.metadata_help')}</div>
                <div class="form">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=""
                        .value=${this._metadataJson}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('settings: metadata expects detail.value string');
                            }
                            this._metadataJson = e.detail.value;
                            this._metadataError = '';
                        }}
                    ></platform-field>
                    ${this._metadataError ? html`<div class="field-error">${this._metadataError}</div>` : ''}
                </div>
            </section>

            <button class="btn" ?disabled=${saving} @click=${this._save}>
                ${saving ? this.t('settings_page.saving') : this.t('settings_page.save')}
            </button>
        `;
    }

    _capabilityDraft(cap: Record<string, unknown>): Record<string, unknown> {
        if (typeof cap.capability !== 'string' || cap.capability.length === 0) {
            throw new Error('settings: capability name required');
        }
        const saved = this._capabilityDrafts[cap.capability];
        if (saved !== undefined) return saved;
        const provider = displayText(cap.provider);
        return {
            provider: provider.length > 0 ? provider : displayText(cap.platform_default_provider),
            api_key: '',
            base_url: displayText(cap.base_url),
            model: displayText(cap.model),
            dimension: missingAsNull(cap.dimension),
            mrl_output_dimension: missingAsNull(cap.mrl_output_dimension),
        };
    }

    _onCapabilityChange(capName: string, e: CustomEvent) {
        if (!isPlainRecord(e.detail) || !isPlainRecord(e.detail.config)) {
            return;
        }
        this._capabilityDrafts = {
            ...this._capabilityDrafts,
            [capName]: { ...e.detail.config },
        };
    }

    _saveCapability(capability: string) {
        const draft = this._capabilityDrafts[capability];
        if (draft === undefined || typeof draft.provider !== 'string' || draft.provider.length === 0) {
            return;
        }
        const body: Record<string, unknown> = { capability, provider: draft.provider };
        if (draft.api_key !== undefined && draft.api_key !== '') body.api_key = draft.api_key;
        if (draft.base_url !== undefined && draft.base_url !== '') body.base_url = draft.base_url;
        if (draft.model !== undefined && draft.model !== '') body.model = draft.model;
        if (draft.dimension !== undefined && draft.dimension !== '' && draft.dimension !== null && draft.dimension !== false) {
            body.dimension = draft.dimension;
        }
        if (draft.mrl_output_dimension !== undefined && draft.mrl_output_dimension !== '' && draft.mrl_output_dimension !== null && draft.mrl_output_dimension !== false) {
            body.mrl_output_dimension = draft.mrl_output_dimension;
        }
        if (draft.folder_id !== undefined && draft.folder_id !== '' && draft.folder_id !== null && draft.folder_id !== false) {
            body.folder_id = draft.folder_id;
        }
        if (draft.extra_request_headers !== undefined && draft.extra_request_headers !== '' && draft.extra_request_headers !== null && draft.extra_request_headers !== false) {
            body.extra_request_headers = draft.extra_request_headers;
        }
        if (Array.isArray(draft.fallback_models) && draft.fallback_models.length > 0) {
            body.fallback_models = draft.fallback_models;
        }
        this._capPut.run(body);
    }

    _clearCapability(capability: string) {
        this._capDelete.run({ capability });
        const next = { ...this._capabilityDrafts };
        delete next[capability];
        this._capabilityDrafts = next;
    }

    _saveLlmContext() {
        const draft = this._llmContextDraft && typeof this._llmContextDraft === 'object'
            ? this._llmContextDraft
            : {};
        if (Object.keys(draft).length === 0) {
            this._contextDelete.run();
            return;
        }
        this._contextPut.run(draft);
    }

    _clearLlmContext() {
        this._llmContextDraft = {};
        this._contextDelete.run();
    }

    _renderLlmContextCard(data: Record<string, unknown>) {
        const info = isPlainRecord(data.llm_context) ? data.llm_context : {};
        const configured = info.configured === true;
        return html`
            <section>
                <h3>${this.t('settings_page.ai_providers.section_context')}</h3>
                <div class="section-help">${this.t('settings_page.ai_providers.section_context_help')}</div>
                <div class="context-card">
                    <platform-llm-context-editor
                        .config=${this._llmContextDraft}
                        .resolved=${isPlainRecord(info.resolved) ? info.resolved : {}}
                        .profiles=${Array.isArray(info.profiles) ? info.profiles : []}
                        .budgets=${Array.isArray(info.budgets) ? info.budgets : []}
                        .clearable=${configured || Object.keys(this._llmContextDraft).length > 0}
                        @change=${(e: CustomEvent) => {
                            if (!isPlainRecord(e.detail) || !isPlainRecord(e.detail.config)) {
                                this._llmContextDraft = {};
                                return;
                            }
                            this._llmContextDraft = { ...e.detail.config };
                        }}
                        @clear=${() => this._clearLlmContext()}
                    ></platform-llm-context-editor>
                    <div class="context-actions">
                        <glass-button
                            size="sm"
                            variant="ghost"
                            ?disabled=${this._contextDelete.busy}
                            @click=${() => this._clearLlmContext()}
                        >
                            ${this.t('settings_page.ai_providers.clear_context')}
                        </glass-button>
                        <glass-button
                            size="sm"
                            ?disabled=${this._contextPut.busy}
                            @click=${() => this._saveLlmContext()}
                        >
                            ${this.t('settings_page.ai_providers.save_context')}
                        </glass-button>
                    </div>
                </div>
            </section>
        `;
    }

    _renderCapabilityCard(cap: Record<string, unknown>, catalog: Record<string, unknown>) {
        const draft = this._capabilityDraft(cap);
        const capabilityName = cap.capability;
        if (typeof capabilityName !== 'string' || capabilityName.length === 0) {
            throw new Error('settings: capability name required');
        }
        const providerCatalog = arrayField(catalog[capabilityName], `settings: catalog.${capabilityName}`);
        const platformModel = this._platformModelForCapability(cap, draft);
        const providerName = displayText(draft.provider);
        const companyPaid = displayText(draft.api_key).length > 0
            || displayText(draft.base_url).length > 0
            || providerName.startsWith('custom:');
        const keyMasked = displayText(cap.key_masked);
        return html`
            <div class="capability-card">
                <div class="header">
                    <h4>${this.t(`settings_page.ai_providers.cap_${cap.capability}`)}</h4>
                </div>
                <div class="desc">${this.t(`settings_page.ai_providers.cap_${cap.capability}_help`)}</div>
                <platform-llm-config-editor
                    mode="company_capability"
                    .capability=${cap.capability}
                    .config=${draft}
                    .providerCatalog=${providerCatalog}
                    .platformModel=${platformModel}
                    .costOrigin=${cap.configured ? (companyPaid ? 'company' : 'platform') : null}
                    .keyMasked=${keyMasked.length > 0 ? keyMasked : null}
                    .clearable=${cap.configured}
                    @change=${(e: CustomEvent) => this._onCapabilityChange(capabilityName, e)}
                    @clear-override=${() => this._clearCapability(capabilityName)}
                ></platform-llm-config-editor>
                <div class="actions">
                    <glass-button size="sm" @click=${() => this._saveCapability(capabilityName)}>
                        ${this.t('settings_page.ai_providers.save_capability')}
                    </glass-button>
                </div>
            </div>
        `;
    }

    _platformModelForCapability(cap: Record<string, unknown>, draft: Record<string, unknown>) {
        const platformModel = displayText(cap.platform_default_model);
        if (platformModel.length === 0) {
            return '';
        }
        const provider = displayText(draft.provider);
        if (provider !== displayText(cap.platform_default_provider)) {
            return '';
        }
        if (provider !== 'linnex_llm') {
            return platformModel;
        }
        const companyModel = typeof draft.model === 'string' && draft.model.length > 0 ? draft.model : 'auto';
        if (companyModel === platformModel) {
            return '';
        }
        return platformModel;
    }

    _normalizeCustomProviderRow(raw: unknown) {
        if (!isPlainRecord(raw)) {
            return {
                id: '',
                label: '',
                base_url: '',
                capabilities: [],
                key_masked: '',
                rerank_path: '',
                model_by_capability: {},
                extra_request_headers: {},
                extra_request_body: {},
            };
        }
        const id = raw.id != null ? String(raw.id) : '';
        const label = raw.label != null ? String(raw.label) : '';
        const baseUrl = raw.base_url != null
            ? String(raw.base_url)
            : (raw.baseUrl != null ? String(raw.baseUrl) : '');
        const caps = Array.isArray(raw.capabilities) ? raw.capabilities.map((c) => String(c)) : [];
        const keyMasked = raw.key_masked != null
            ? String(raw.key_masked)
            : (raw.keyMasked != null ? String(raw.keyMasked) : '');
        const rerankPath = raw.rerank_path != null
            ? String(raw.rerank_path)
            : (raw.rerankPath != null ? String(raw.rerankPath) : '');
        const modelByCapability = raw.model_by_capability && typeof raw.model_by_capability === 'object' && !Array.isArray(raw.model_by_capability)
            ? raw.model_by_capability
            : {};
        const extraRequestHeaders = raw.extra_request_headers && typeof raw.extra_request_headers === 'object' && !Array.isArray(raw.extra_request_headers)
            ? raw.extra_request_headers
            : {};
        const extraRequestBody = raw.extra_request_body && typeof raw.extra_request_body === 'object' && !Array.isArray(raw.extra_request_body)
            ? raw.extra_request_body
            : {};
        return {
            id,
            label,
            base_url: baseUrl,
            capabilities: caps,
            key_masked: keyMasked,
            rerank_path: rerankPath,
            model_by_capability: modelByCapability,
            extra_request_headers: extraRequestHeaders,
            extra_request_body: extraRequestBody,
        };
    }

    _openCustomProviderModal() {
        this.openModal('frontend.ai_custom_provider_create', { initialProvider: null });
    }

    _openCustomProviderEdit(raw: unknown) {
        const row = this._normalizeCustomProviderRow(raw);
        this.openModal('frontend.ai_custom_provider_create', { initialProvider: row });
    }

    _renderAiProvidersTab() {
        const data = this._aiLoad.lastResult;
        if (!data) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        if (!isPlainRecord(data)) {
            throw new Error('settings: ai providers payload must be an object');
        }
        const capabilities = arrayField(data.capabilities, 'settings: capabilities');
        const customProviders = arrayField(data.custom_providers, 'settings: custom_providers');
        const catalog = recordField(data.catalog, 'settings: catalog');
        return html`
            ${this._renderLlmContextCard(data)}

            <section>
                <div class="header">
                    <h3>${this.t('settings_page.ai_providers.section_custom_providers')}</h3>
                    <glass-button size="sm" @click=${() => this._openCustomProviderModal()}>
                        ${this.t('settings_page.ai_providers.add_custom_provider')}
                    </glass-button>
                </div>
                <div class="section-help">${this.t('settings_page.ai_providers.section_custom_providers_help')}</div>
                ${customProviders.length === 0
                    ? html`<platform-empty-state icon="llm_node" title=${this.t('settings_page.ai_providers.no_custom_providers')}></platform-empty-state>`
                    : html`
                          <div class="custom-provider-list">
                              ${customProviders.map((raw) => {
                                  if (!isPlainRecord(raw)) throw new Error('settings: custom provider must be an object');
                                  const p = this._normalizeCustomProviderRow(raw);
                                  const title = p.label.length > 0 ? p.label : (p.id.length > 0 ? p.id : '—');
                                  const ref = p.id ? `custom:${p.id}` : '—';
                                  const url = p.base_url.length > 0 ? p.base_url : '—';
                                  const caps = p.capabilities.length ? p.capabilities.join(', ') : '—';
                                  const km = p.key_masked.length > 0 ? p.key_masked : '—';
                                  return html`
                                      <div class="custom-provider-card">
                                          <div class="meta">
                                              <div class="title-line">${title}</div>
                                              <div class="ref-line">${ref}</div>
                                              <div class="url-line">${url}</div>
                                              <div class="caps-line">${this.t('settings_page.ai_providers.custom_capabilities')}: ${caps}</div>
                                              <div class="key-line">${this.t('settings_page.ai_providers.custom_key')}: ${km}</div>
                                          </div>
                                          <div class="actions">
                                              ${p.id
                                                  ? html`
                                                        <glass-button
                                                            variant="ghost"
                                                            size="sm"
                                                            @click=${() => this._openCustomProviderEdit(raw)}
                                                        >${this.t('settings_page.ai_providers.edit_custom')}</glass-button>
                                                        <glass-button
                                                            variant="danger"
                                                            size="sm"
                                                            @click=${() => this._customDelete.run({ provider_id: p.id })}
                                                        >${this.t('settings_page.ai_providers.delete_custom')}</glass-button>
                                                    `
                                                  : ''}
                                          </div>
                                      </div>
                                  `;
                              })}
                          </div>
                      `}
            </section>

            <section>
                <h3>${this.t('settings_page.ai_providers.section_capabilities')}</h3>
                <div class="section-help">${this.t('settings_page.ai_providers.section_capabilities_help')}</div>
                <div class="two-col">
                    ${capabilities.map((cap) => {
                        if (!isPlainRecord(cap)) throw new Error('settings: capability must be an object');
                        return this._renderCapabilityCard(cap, catalog);
                    })}
                </div>
            </section>
        `;
    }

    _searchProviderDraft(provider: Record<string, unknown>): SearchProviderDraft {
        const providerId = requireSearchProviderId(provider);
        const draft = this._searchProviderDrafts[providerId];
        if (draft !== undefined) {
            return draft;
        }
        return searchProviderDraftFrom(provider);
    }

    _setSearchProviderDraft(providerId: string, patch: Partial<SearchProviderDraft>) {
        const current = this._searchProviderDrafts[providerId];
        if (current === undefined) {
            throw new Error(`search provider draft missing: ${providerId}`);
        }
        this._searchProviderDrafts = {
            ...this._searchProviderDrafts,
            [providerId]: {
                ...current,
                ...patch,
            },
        };
    }

    _saveSearchProvider(providerId: string) {
        const draft = this._searchProviderDrafts[providerId];
        if (draft === undefined) {
            return;
        }
        const body: Record<string, unknown> = {
            provider_id: providerId,
            enabled: draft.enabled === true,
            credential_source: draft.credential_source === 'company' ? 'company' : 'platform',
            base_url: draft.base_url ? String(draft.base_url) : null,
            timeout_seconds: typeof draft.timeout_seconds === 'number' ? draft.timeout_seconds : null,
            depth: draft.depth ? String(draft.depth) : null,
            search_depth: draft.search_depth ? String(draft.search_depth) : null,
            topic: draft.topic ? String(draft.topic) : null,
            include_answer: typeof draft.include_answer === 'boolean' ? draft.include_answer : null,
        };
        if (draft.credential_source === 'company' && draft.api_key && String(draft.api_key).trim()) {
            body.api_key = String(draft.api_key).trim();
        }
        this._searchProviderPut.run(body);
    }

    _resetSearchProvider(providerId: string) {
        this._searchProviderDelete.run({ provider_id: providerId });
    }

    _moveSearchProvider(providerId: string, delta: number) {
        const current = this._searchProviderOrder.slice();
        const index = current.indexOf(providerId);
        if (index < 0) {
            return;
        }
        const target = index + delta;
        if (target < 0 || target >= current.length) {
            return;
        }
        const next = current.slice();
        const item = next[index];
        if (item === undefined) {
            throw new Error('settings: search provider order entry missing');
        }
        next.splice(index, 1);
        next.splice(target, 0, item);
        this._searchProviderOrder = next;
        this._searchProviderOrderPut.run({ provider_order: next });
    }

    _renderSearchProviderSpecificFields(provider: Record<string, unknown>, draft: SearchProviderDraft) {
        const providerId = requireSearchProviderId(provider);
        if (providerId === 'linkup') {
            return html`
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('settings_page.search_providers.depth')}
                    .value=${draft.depth}
                    .config=${{ values: [
                        { value: '', label: this.t('settings_page.search_providers.platform_default') },
                        { value: 'fast', label: 'fast' },
                        { value: 'standard', label: 'standard' },
                        { value: 'deep', label: 'deep' },
                    ] }}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('search provider depth expects string detail.value');
                        }
                        this._setSearchProviderDraft(providerId, { depth: e.detail.value });
                    }}
                ></platform-field>
            `;
        }
        if (providerId === 'tavily') {
            return html`
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('settings_page.search_providers.search_depth')}
                    .value=${draft.search_depth}
                    .config=${{ values: [
                        { value: '', label: this.t('settings_page.search_providers.platform_default') },
                        { value: 'basic', label: 'basic' },
                        { value: 'advanced', label: 'advanced' },
                    ] }}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('search provider search_depth expects string detail.value');
                        }
                        this._setSearchProviderDraft(providerId, { search_depth: e.detail.value });
                    }}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('settings_page.search_providers.topic')}
                    .value=${draft.topic}
                    .config=${{ values: [
                        { value: '', label: this.t('settings_page.search_providers.platform_default') },
                        { value: 'general', label: 'general' },
                        { value: 'news', label: 'news' },
                        { value: 'finance', label: 'finance' },
                    ] }}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('search provider topic expects string detail.value');
                        }
                        this._setSearchProviderDraft(providerId, { topic: e.detail.value });
                    }}
                ></platform-field>
                <platform-field
                    type="boolean"
                    mode="edit"
                    label=${this.t('settings_page.search_providers.include_answer')}
                    .value=${draft.include_answer === true}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'boolean') {
                            throw new Error('search provider include_answer expects boolean detail.value');
                        }
                        this._setSearchProviderDraft(providerId, { include_answer: e.detail.value });
                    }}
                ></platform-field>
            `;
        }
        return '';
    }

    _renderSearchProviderCard(provider: Record<string, unknown>) {
        const providerId = requireSearchProviderId(provider);
        const draft = this._searchProviderDraft(provider);
        const meta = searchProviderMeta(providerId);
        const { label, logo, tone } = meta;
        const description = this.t(`settings_page.search_providers.catalog.${providerId}.description`);
        const tooltip = this.t(`settings_page.search_providers.catalog.${providerId}.tooltip`);
        const isCompany = draft.credential_source === 'company';
        return html`
            <article class="search-provider-card" data-source=${isCompany ? 'company' : 'platform'}>
                <div class="provider-card-head">
                    <div class="provider-logo" data-tone=${tone}>${logo}</div>
                    <div class="provider-title">
                        <div class="provider-title-row">
                            <h4>${label}</h4>
                            <button class="info-dot" type="button" title=${tooltip} aria-label=${tooltip}>?</button>
                        </div>
                        <div class="provider-description">${description}</div>
                    </div>
                    <div class="provider-status">
                        <span class="provider-pill" data-ok=${provider.platform_enabled === true ? 'true' : 'false'}>
                            ${provider.platform_key_configured === true
                                ? this.t('settings_page.search_providers.platform_key_ready')
                                : this.t('settings_page.search_providers.platform_key_missing')}
                        </span>
                        ${provider.key_masked
                            ? html`<span class="provider-pill" data-ok="true">${provider.key_masked}</span>`
                            : ''}
                    </div>
                </div>

                <div class="credential-switch" role="group" aria-label=${this.t('settings_page.search_providers.credential_source')}>
                    <button
                        type="button"
                        data-active=${isCompany ? 'false' : 'true'}
                        @click=${() => this._setSearchProviderDraft(providerId, { credential_source: 'platform' })}
                    >${this.t('settings_page.search_providers.source_platform')}</button>
                    <button
                        type="button"
                        data-active=${isCompany ? 'true' : 'false'}
                        @click=${() => this._setSearchProviderDraft(providerId, { credential_source: 'company' })}
                    >${this.t('settings_page.search_providers.source_company')}</button>
                </div>

                <div class="provider-form two">
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label=${this.t('settings_page.search_providers.enabled')}
                        .value=${draft.enabled === true}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'boolean') {
                                throw new Error('search provider enabled expects boolean detail.value');
                            }
                            this._setSearchProviderDraft(providerId, { enabled: e.detail.value });
                        }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('settings_page.search_providers.timeout')}
                        .value=${draft.timeout_seconds}
                        placeholder=${this.t('settings_page.search_providers.platform_default')}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || (e.detail.value !== null && typeof e.detail.value !== 'number')) {
                                throw new Error('search provider timeout expects numeric detail.value');
                            }
                            this._setSearchProviderDraft(providerId, { timeout_seconds: e.detail.value });
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.search_providers.base_url')}
                        .value=${draft.base_url}
                        placeholder=${provider.platform_base_url}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('search provider base_url expects string detail.value');
                            }
                            this._setSearchProviderDraft(providerId, { base_url: e.detail.value });
                        }}
                    ></platform-field>
                    ${isCompany
                        ? html`
                            <platform-field
                                type="string"
                                mode="edit"
                                input-type="password"
                                label=${this.t('settings_page.search_providers.api_key')}
                                .value=${draft.api_key}
                                placeholder=${provider.key_masked
                                    ? this.t('settings_page.search_providers.keep_existing_key')
                                    : 'sk-...'}
                                @change=${(e: CustomEvent) => {
                                    if (!e.detail || typeof e.detail.value !== 'string') {
                                        throw new Error('search provider api_key expects string detail.value');
                                    }
                                    this._setSearchProviderDraft(providerId, { api_key: e.detail.value });
                                }}
                            ></platform-field>
                        `
                        : ''}
                    ${this._renderSearchProviderSpecificFields(provider, draft)}
                </div>

                <div class="provider-actions">
                    <div class="order-controls">
                        <glass-button
                            size="sm"
                            variant="ghost"
                            @click=${() => this._moveSearchProvider(providerId, -1)}
                        >${this.t('settings_page.search_providers.move_up')}</glass-button>
                        <glass-button
                            size="sm"
                            variant="ghost"
                            @click=${() => this._moveSearchProvider(providerId, 1)}
                        >${this.t('settings_page.search_providers.move_down')}</glass-button>
                    </div>
                    <div class="order-controls">
                        <glass-button
                            size="sm"
                            variant="ghost"
                            ?disabled=${this._searchProviderDelete.busy}
                            @click=${() => this._resetSearchProvider(providerId)}
                        >${this.t('settings_page.search_providers.reset')}</glass-button>
                        <glass-button
                            size="sm"
                            ?disabled=${this._searchProviderPut.busy}
                            @click=${() => this._saveSearchProvider(providerId)}
                        >${this.t('settings_page.search_providers.save')}</glass-button>
                    </div>
                </div>
            </article>
        `;
    }

    _renderSearchProvidersTab() {
        const data = this._searchLoad.lastResult;
        if (!data) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        const providers = isPlainRecord(data) && Array.isArray(data.providers) ? data.providers : [];
        const providerRecords = providers.filter((provider): provider is Record<string, unknown> => isPlainRecord(provider) && typeof provider.provider_id === 'string');
        const order = this._searchProviderOrder;
        const orderedProviders: Record<string, unknown>[] = [];
        for (const providerId of order) {
            const provider = providerRecords.find((item) => item.provider_id === providerId);
            if (provider !== undefined) {
                orderedProviders.push(provider);
            }
        }
        for (const provider of providerRecords) {
            if (!order.includes(requireSearchProviderId(provider))) {
                orderedProviders.push(provider);
            }
        }
        return html`
            <section class="search-provider-hero">
                <div>
                    <h3>${this.t('settings_page.search_providers.title')}</h3>
                    <p>${this.t('settings_page.search_providers.subtitle')}</p>
                </div>
                <div class="billing-note">
                    <strong>${this.t('settings_page.search_providers.billing_title')}</strong>
                    <span>${this.t('settings_page.search_providers.billing_platform')}</span>
                    <span>${this.t('settings_page.search_providers.billing_company')}</span>
                    <span>${this.t('settings_page.search_providers.billing_system')}</span>
                </div>
            </section>
            <section>
                <div class="search-provider-grid">
                    ${orderedProviders.map((provider) => this._renderSearchProviderCard(provider))}
                </div>
            </section>
        `;
    }

    _modelScoreKey(row: Record<string, unknown>) {
        return `${scoreField(row, 'capability')}\n${scoreField(row, 'provider')}\n${scoreField(row, 'model_id')}`;
    }

    _modelScoreDraft(row: Record<string, unknown>): ModelScoreDraft {
        const key = this._modelScoreKey(row);
        const saved = this._modelScoreDrafts[key];
        if (saved !== undefined) {
            return saved;
        }
        if (typeof row.editorial_prior !== 'number') {
            throw new Error('model scoring: editorial_prior must be a number');
        }
        if (typeof row.enabled !== 'boolean') {
            throw new Error('model scoring: enabled must be boolean');
        }
        const note = row.note === null || row.note === undefined ? '' : row.note;
        if (typeof note !== 'string') {
            throw new Error('model scoring: note must be a string');
        }
        return {
            provider: scoreField(row, 'provider'),
            model_id: scoreField(row, 'model_id'),
            capability: scoreField(row, 'capability'),
            enabled: row.enabled,
            note,
            editorial_prior: row.editorial_prior,
        };
    }

    _formatScoreBreakdown(breakdown: unknown) {
        if (breakdown == null) {
            return '—';
        }
        if (typeof breakdown !== 'object') {
            throw new Error('model scoring: score_breakdown must be an object');
        }
        const entries = Object.entries(breakdown);
        if (entries.length === 0) {
            return '—';
        }
        return entries
            .map(([dimension, value]) => `${dimension}: ${Number(value).toFixed(1)}`)
            .join(', ');
    }

    _formatAaIndex(value: unknown) {
        if (value == null) {
            return '—';
        }
        if (typeof value !== 'number') {
            throw new Error('model scoring: AA index must be a number');
        }
        return value.toFixed(1);
    }

    _setModelScoreDraft(row: Record<string, unknown>, patch: Partial<ModelScoreDraft>) {
        const key = this._modelScoreKey(row);
        this._modelScoreDrafts = {
            ...this._modelScoreDrafts,
            [key]: {
                ...this._modelScoreDraft(row),
                ...patch,
            },
        };
    }

    _saveModelScore(row: Record<string, unknown>) {
        const draft = this._modelScoreDraft(row);
        this._scoreUpsert.run({
            provider: draft.provider,
            model_id: draft.model_id,
            capability: draft.capability,
            enabled: draft.enabled,
            editorial_prior: draft.editorial_prior,
            note: draft.note === '' ? null : draft.note,
        });
    }

    _deleteModelScore(row: Record<string, unknown>) {
        this._scoreDelete.run({
            capability: scoreField(row, 'capability'),
            provider: scoreField(row, 'provider'),
            model_id: scoreField(row, 'model_id'),
        });
    }

    _createModelScore() {
        const draft = this._modelScoreNew;
        const provider = displayText(draft.provider).trim();
        const modelId = displayText(draft.model_id).trim();
        const capability = displayText(draft.capability).trim();
        if (!capability || !provider || !modelId) {
            return;
        }
        this._scoreUpsert.run({
            capability,
            provider,
            model_id: modelId,
            enabled: draft.enabled,
            editorial_prior: draft.editorial_prior,
            note: draft.note ? String(draft.note) : null,
        });
        this._modelScoreNew = {
            capability: 'llm_chat',
            provider: 'openrouter',
            model_id: '',
            editorial_prior: 0,
            enabled: true,
            note: '',
        };
    }

    _scoreErrorClassLabel(errorClass: string) {
        return llmProviderErrorClassLabel((key: string) => this.t(key), errorClass);
    }

    _scoreAvailabilityLabel(row: Record<string, unknown>) {
        if (row.availability === 'available') {
            return this.t('settings_page.model_scoring.status_available');
        }
        if (row.availability === 'disabled') {
            return this.t('settings_page.model_scoring.status_disabled');
        }
        if (row.availability === 'not_configured') {
            return this.t('settings_page.model_scoring.status_not_configured');
        }
        if (row.availability === 'cooldown') {
            if (typeof row.cooldown_seconds === 'number') {
                return `${this.t('settings_page.model_scoring.status_cooldown')} ${formatDurationSeconds(row.cooldown_seconds)}`;
            }
            return this.t('settings_page.model_scoring.status_cooldown');
        }
        throw new Error(`model scoring: unknown availability ${row.availability}`);
    }

    _scoreRowClass(row: Record<string, unknown>) {
        if (row.availability !== 'cooldown') {
            return '';
        }
        if (typeof row.error_class === 'string' && llmProviderErrorClassIsBlocking(row.error_class)) {
            return 'score-row-error';
        }
        return 'score-row-cooldown';
    }

    _scoreStatusHint(row: Record<string, unknown>) {
        const parts: string[] = [];
        if (typeof row.error_class === 'string') {
            parts.push(this._scoreErrorClassLabel(row.error_class));
        }
        if (typeof row.error_text === 'string' && row.error_text !== '') {
            parts.push(row.error_text);
        }
        return parts.join('\n');
    }

    _filteredScoreItems(items: Record<string, unknown>[]) {
        if (this._scoreStatusFilter === 'all') {
            return items;
        }
        if (this._scoreStatusFilter === 'blocked') {
            return items.filter((row) => row.availability === 'cooldown');
        }
        throw new Error(`model scoring: unknown status filter ${this._scoreStatusFilter}`);
    }

    _renderModelScoringTab() {
        const result = this._scoreLoad.lastResult;
        if (!result) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        if (!isPlainRecord(result)) {
            throw new Error('model scoring: payload must be an object');
        }
        if (!Array.isArray(result.providers)) {
            throw new Error('model scoring: providers must be an array');
        }
        const items = scoreRows(result.items);
        const visibleItems = this._filteredScoreItems(items);
        return html`
            <section>
                <div class="scores-toolbar">
                    <div>
                        <h3>${this.t('settings_page.model_scoring.title')}</h3>
                        <div class="section-help">${this.t('settings_page.model_scoring.help')}</div>
                    </div>
                    <div class="scores-toolbar-actions">
                        <div class="score-filter">
                            <glass-button
                                size="sm"
                                variant="ghost"
                                data-active=${this._scoreStatusFilter === 'all' ? 'true' : 'false'}
                                @click=${() => { this._scoreStatusFilter = 'all'; }}
                            >${this.t('settings_page.model_scoring.filter_all')}</glass-button>
                            <glass-button
                                size="sm"
                                variant="ghost"
                                data-active=${this._scoreStatusFilter === 'blocked' ? 'true' : 'false'}
                                @click=${() => { this._scoreStatusFilter = 'blocked'; }}
                            >${this.t('settings_page.model_scoring.filter_blocked')}</glass-button>
                        </div>
                        <glass-button
                            size="sm"
                            variant="ghost"
                            ?disabled=${this._scoreProbe.busy}
                            @click=${() => this._scoreProbe.run()}
                        >${this.t('settings_page.model_scoring.probe_now')}</glass-button>
                        <glass-button
                            size="sm"
                            variant="ghost"
                            ?disabled=${this._scoreRefreshCache.busy}
                            @click=${() => this._scoreRefreshCache.run()}
                        >${this.t('settings_page.model_scoring.refresh_cache')}</glass-button>
                    </div>
                </div>
                <llm-provider-status-strip .providers=${result.providers}></llm-provider-status-strip>
                <div class="section-help">${this.t('settings_page.model_scoring.providers_help')}</div>
                ${items.length === 0
                    ? html`<platform-empty-state icon="chart" title=${this.t('settings_page.model_scoring.empty')}></platform-empty-state>`
                    : visibleItems.length === 0
                    ? html`<platform-empty-state icon="chart" title=${this.t('settings_page.model_scoring.empty_blocked')}></platform-empty-state>`
                    : html`
                        <div class="scores-table-wrap">
                            <table class="scores-table">
                                <thead>
                                    <tr>
                                        <th>${this.t('settings_page.model_scoring.col_capability')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_provider')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_model')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_status')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_score')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_intelligence')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_coding')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_agentic')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_breakdown')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_editorial_prior')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_enabled')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_note')}</th>
                                        <th>${this.t('settings_page.model_scoring.col_actions')}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${visibleItems.map((row) => {
                                        if (typeof row.score !== 'number') {
                                            throw new Error('model scoring: score must be a number');
                                        }
                                        const draft = this._modelScoreDraft(row);
                                        const statusHint = this._scoreStatusHint(row);
                                        return html`
                                            <tr class=${this._scoreRowClass(row)}>
                                                <td class="score-provider">${row.capability}</td>
                                                <td class="score-provider">${row.provider}</td>
                                                <td class="score-model">${row.model_id}</td>
                                                <td>
                                                    <div class="score-status">
                                                        <span class="score-status-pill">${this._scoreAvailabilityLabel(row)}</span>
                                                        ${statusHint === ''
                                                            ? nothing
                                                            : html`<platform-help-hint .text=${statusHint}></platform-help-hint>`}
                                                    </div>
                                                </td>
                                                <td class="score-computed">${row.score.toFixed(1)}</td>
                                                <td class="score-computed">${this._formatAaIndex(row.intelligence_index)}</td>
                                                <td class="score-computed">${this._formatAaIndex(row.coding_index)}</td>
                                                <td class="score-computed">${this._formatAaIndex(row.agentic_index)}</td>
                                                <td class="score-breakdown">${this._formatScoreBreakdown(row.score_breakdown)}</td>
                                                <td>
                                                    <platform-field
                                                        type="number"
                                                        mode="edit"
                                                        label=""
                                                        .value=${draft.editorial_prior}
                                                        @change=${(e: CustomEvent) => {
                                                            if (!e.detail || typeof e.detail.value !== 'number') {
                                                                throw new Error('model scoring: editorial_prior expects numeric detail.value');
                                                            }
                                                            this._setModelScoreDraft(row, { editorial_prior: e.detail.value });
                                                        }}
                                                    ></platform-field>
                                                </td>
                                                <td>
                                                    <platform-field
                                                        type="boolean"
                                                        mode="edit"
                                                        label=""
                                                        .value=${draft.enabled}
                                                        @change=${(e: CustomEvent) => {
                                                            if (!e.detail || typeof e.detail.value !== 'boolean') {
                                                                throw new Error('model scoring: enabled expects boolean detail.value');
                                                            }
                                                            this._setModelScoreDraft(row, { enabled: e.detail.value });
                                                        }}
                                                    ></platform-field>
                                                </td>
                                                <td>
                                                    <platform-field
                                                        type="string"
                                                        mode="edit"
                                                        label=""
                                                        .value=${draft.note}
                                                        @change=${(e: CustomEvent) => {
                                                            if (!e.detail || typeof e.detail.value !== 'string') {
                                                                throw new Error('model scoring: note expects string detail.value');
                                                            }
                                                            this._setModelScoreDraft(row, { note: e.detail.value });
                                                        }}
                                                    ></platform-field>
                                                </td>
                                                <td>
                                                    <div class="score-actions">
                                                        <glass-button
                                                            size="sm"
                                                            ?disabled=${this._scoreUpsert.busy}
                                                            @click=${() => this._saveModelScore(row)}
                                                        >${this.t('settings_page.model_scoring.save')}</glass-button>
                                                        <glass-button
                                                            size="sm"
                                                            variant="danger"
                                                            ?disabled=${this._scoreDelete.busy}
                                                            @click=${() => this._deleteModelScore(row)}
                                                        >${this.t('settings_page.model_scoring.delete')}</glass-button>
                                                    </div>
                                                </td>
                                            </tr>
                                        `;
                                    })}
                                </tbody>
                            </table>
                        </div>
                    `}
            </section>

            <section>
                <h3>${this.t('settings_page.model_scoring.add_title')}</h3>
                <div class="score-form">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_capability')}
                        .value=${this._modelScoreNew.capability}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('model scoring: capability expects string detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, capability: e.detail.value };
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_provider')}
                        .value=${this._modelScoreNew.provider}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('model scoring: provider expects string detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, provider: e.detail.value };
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_model')}
                        .value=${this._modelScoreNew.model_id}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('model scoring: model_id expects string detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, model_id: e.detail.value };
                        }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_editorial_prior')}
                        .value=${this._modelScoreNew.editorial_prior}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'number') {
                                throw new Error('model scoring: new editorial_prior expects numeric detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, editorial_prior: e.detail.value };
                        }}
                    ></platform-field>
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_enabled')}
                        .value=${this._modelScoreNew.enabled}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'boolean') {
                                throw new Error('model scoring: new enabled expects boolean detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, enabled: e.detail.value };
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.model_scoring.col_note')}
                        .value=${this._modelScoreNew.note}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('model scoring: new note expects string detail.value');
                            }
                            this._modelScoreNew = { ...this._modelScoreNew, note: e.detail.value };
                        }}
                    ></platform-field>
                    <glass-button
                        size="sm"
                        ?disabled=${this._scoreUpsert.busy}
                        @click=${() => this._createModelScore()}
                    >${this.t('settings_page.model_scoring.add')}</glass-button>
                </div>
            </section>
        `;
    }

    _renderSecurityTab() {
        return html`
            <div class="two-col">
                <section>
                    <h3>${this.t('settings_page.security_title')}</h3>
                    <div class="section-help">${this.t('settings_page.security_info')}</div>
                    <platform-empty-state icon="smartphone" title=${this.t('settings_page.sessions_placeholder')}></platform-empty-state>
                </section>
                <section>
                    <h3>${this.t('settings_page.oauth_title')}</h3>
                    <div class="section-help">${this.t('settings_page.oauth_info')}</div>
                    <platform-empty-state icon="key" title=${this.t('settings_page.oauth_empty')}></platform-empty-state>
                </section>
            </div>
        `;
    }

    _renderIntegrationsTab() {
        return html`
            <section>
                <h3>${this.t('settings_page.integrations_title')}</h3>
                <div class="section-help">${this.t('settings_page.integrations_info')}</div>
                <div class="integration-grid">
                    ${INTEGRATION_LIST.map((it) => html`
                        <div class="integration-card">
                            <div class="integration-name">${it.id}</div>
                            <div class="integration-id">${it.route}</div>
                            <button class="btn btn-ghost"
                                @click=${() => this.navigate(it.route)}
                            >${this.t('settings_page.connect')}</button>
                        </div>
                    `)}
                </div>
            </section>
        `;
    }

    override render(): TemplateResult {
        const company = this._load.lastResult;
        if (company === null || company === undefined) {
            return html`
                <page-header title=${this.t('settings_page.title')}></page-header>
                <div class="page-body">
                <platform-empty-state loading></platform-empty-state>
                </div>
            `;
        }
        if (!isPlainRecord(company)) {
            throw new Error('settings-page: company must be an object');
        }
        return html`
            <page-header title=${this.t('settings_page.title')}></page-header>
            <div class="page-body">
            ${this._renderTabs()}
            ${this._activeTab === 'company' ? this._renderCompanyTab(company) : ''}
            ${this._activeTab === 'ai_providers' ? this._renderAiProvidersTab() : ''}
            ${this._activeTab === 'search_providers' ? this._renderSearchProvidersTab() : ''}
            ${this._activeTab === 'model_scoring' ? this._renderModelScoringTab() : ''}
            ${this._activeTab === 'security' ? this._renderSecurityTab() : ''}
            ${this._activeTab === 'integrations' ? this._renderIntegrationsTab() : ''}
            ${this._activeTab === 'storages' ? this._renderStoragesTab() : ''}
            </div>
        `;
    }
}

customElements.define('frontend-settings-page', FrontendSettingsPage);
