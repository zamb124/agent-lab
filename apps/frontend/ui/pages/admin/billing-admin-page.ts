/**
 * Страница admin billing (system): scope компании, каталог цен, правила settlement, usage.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/fields/platform-field-shell.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-json-editor.js';
import { FrontendSystemAccessModal } from '../../modals/system-access-modal.js';
import { FrontendBalanceGrantModal } from '../../modals/balance-grant-modal.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

interface PriceRow {
    category: string;
    resource_name: string;
    price: string;
}

interface BillingMatch {
    attribute_equals: Record<string, unknown>;
    attribute_regex: Record<string, unknown>;
    attribute_keys_present: unknown[];
    [key: string]: unknown;
}

interface BillingRule {
    match: BillingMatch;
    [key: string]: unknown;
}

interface BillingRulesDoc {
    version: unknown;
    application_mode: unknown;
    rules: BillingRule[];
    [key: string]: unknown;
}

interface PricingLayerRow {
    category: string;
    resource_name: string;
    static_base: number | null;
    global_override: number | null;
    company_override: number | null;
    base_effective: number | null;
    tariff_multiplier: number;
    unit_effective: number | null;
    source: string;
}

function billingMatch(value: unknown): BillingMatch {
    const match: BillingMatch = {
        attribute_equals: {},
        attribute_regex: {},
        attribute_keys_present: [],
    };
    if (!isPlainRecord(value)) return match;
    for (const [key, field] of Object.entries(value)) match[key] = field;
    if (!isPlainRecord(match.attribute_equals)) match.attribute_equals = {};
    if (!isPlainRecord(match.attribute_regex)) match.attribute_regex = {};
    if (!Array.isArray(match.attribute_keys_present)) match.attribute_keys_present = [];
    return match;
}

function billingRule(value: Record<string, unknown>): BillingRule {
    const rule: BillingRule = { match: billingMatch(value.match) };
    for (const [key, field] of Object.entries(value)) {
        if (key === 'match') continue;
        rule[key] = field;
    }
    return rule;
}
import type { OpController, FacetsController} from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function matchFieldName(scope: string, mode: string): string | null {
    switch (scope) {
        case 'operation':
            switch (mode) {
                case 'prefix':
                    return 'operation_name_prefix';
                case 'equals':
                    return 'operation_name_equals';
                case 'regex':
                    return 'operation_name_regex';
                default:
                    return null;
            }
        case 'service':
            switch (mode) {
                case 'equals':
                    return 'service_name_equals';
                case 'regex':
                    return 'service_name_regex';
                default:
                    return null;
            }
        case 'event':
            switch (mode) {
                case 'equals':
                    return 'event_type_equals';
                case 'regex':
                    return 'event_type_regex';
                default:
                    return null;
            }
        default:
            return null;
    }
}

function matchModeFields(scope: string): string[] | null {
    switch (scope) {
        case 'operation':
            return ['operation_name_prefix', 'operation_name_equals', 'operation_name_regex'];
        case 'service':
            return ['service_name_equals', 'service_name_regex'];
        case 'event':
            return ['event_type_equals', 'event_type_regex'];
        default:
            return null;
    }
}

function nestedRecord(source: unknown, field: string): Record<string, unknown> | null {
    if (!isPlainRecord(source)) return null;
    const value = source[field];
    return isPlainRecord(value) ? value : null;
}

function controlValue(event: Event): string {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
        return target.value;
    }
    throw new Error('billing-admin: text control required');
}

function displayText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function firstText(values: readonly unknown[]): string {
    for (const value of values) {
        const text = displayText(value);
        if (text.length > 0) return text;
    }
    return '';
}

function objectList(value: unknown, label: string): Record<string, unknown>[] {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
    const rows: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) throw new Error(`${label} item must be an object`);
        rows.push(item);
    }
    return rows;
}

const COMPANIES_PAGE_SIZE = 50;

const TABS = Object.freeze(['companies', 'prices_rules', 'usage']);
const BILLING_RULE_ATTR_SUGGESTIONS = Object.freeze([
    'platform.billing.quantity',
    'platform.billing.settlement_quantity_rub',
    'platform.billing.resource_name',
    'platform.billing.cost_origin',
    'platform.llm.provider',
    'platform.llm.model',
    'platform.llm.total_tokens',
    'platform.llm.input_tokens',
    'platform.llm.output_tokens',
]);

export class FrontendBillingAdminPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        _tab: { state: true },
        _companyId: { state: true },
        _companyName: { state: true },
        _companySubdomain: { state: true },
        _companyQuery: { state: true },
        _facetOpen: { state: true },
        _pricesDraft: { state: true },
        _companyPricesDraft: { state: true },
        _rulesDraft: { state: true },
        _rulesDraftError: { state: true },
        _matchModeDraft: { state: true },
        _usageFilters: { state: true },
        _usageFacetOpen: { state: true },
    }
    declare _tab: string;
    declare _companyId: string;
    declare _companyName: string;
    declare _companySubdomain: string;
    declare _companyQuery: string;
    declare _facetOpen: boolean;
    declare _pricesDraft: PriceRow[] | null;
    declare _companyPricesDraft: PriceRow[] | null;
    declare _rulesDraft: string | null;
    declare _rulesDraftError: string;
    declare _matchModeDraft: Record<string, string>;
    declare _usageFilters: Record<string, string>;
    declare _usageFacetOpen: string | null;
;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .tabs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                margin-bottom: var(--space-4);
            }
            .tab {
                padding: var(--space-2) var(--space-4);
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-sm);
                border-bottom: 2px solid transparent;
            }
            .tab[aria-selected="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .company-panel,
            section {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
            }
            .company-panel {
                display: grid;
                grid-template-columns: minmax(320px, 1fr) minmax(240px, 0.8fr);
                gap: var(--space-4);
                align-items: end;
            }
            .company-search { position: relative; min-width: 0; }
            .company-search platform-field { width: 100%; }
            .field-search-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                min-width: 32px;
                min-height: 32px;
                padding: 0;
                border: 1px solid var(--accent);
                border-radius: var(--radius-full);
                background: var(--accent);
                color: white;
                cursor: pointer;
                box-shadow: 0 8px 18px color-mix(in srgb, var(--accent) 24%, transparent);
                transition:
                    transform var(--motion-duration-micro) var(--motion-ease-standard),
                    box-shadow var(--motion-duration-micro) var(--motion-ease-standard),
                    background var(--motion-duration-micro) var(--motion-ease-standard);
            }
            .field-search-btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 22px color-mix(in srgb, var(--accent) 32%, transparent);
            }
            .field-search-btn:focus-visible {
                outline: 2px solid color-mix(in srgb, var(--accent) 38%, white);
                outline-offset: 2px;
            }
            .field-search-btn:disabled {
                opacity: 0.55;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            .company-meta {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .meta-item {
                min-width: 0;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
            }
            .meta-label {
                display: block;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: var(--space-1);
            }
            .meta-value {
                display: block;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                overflow-wrap: anywhere;
            }
            .suggest {
                position: absolute;
                top: calc(100% + 4px);
                left: 0;
                right: 0;
                background: var(--bg-primary);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
                max-height: 260px;
                overflow-y: auto;
                z-index: 20;
            }
            .suggest-item {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
            }
            .suggest-item:hover { background: var(--glass-solid-medium); }

            .section-head {
                display: flex;
                justify-content: space-between;
                gap: var(--space-3);
                align-items: flex-start;
                margin-bottom: var(--space-3);
            }
            .section-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }
            .section-subtitle,
            .hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.45;
            }
            .section-subtitle { max-width: 760px; }
            .stack { display: flex; flex-direction: column; gap: var(--space-4); }
            .split {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-4);
            }
            .actions {
                display: flex;
                gap: var(--space-2);
                margin-top: var(--space-3);
                flex-wrap: wrap;
                align-items: center;
            }
            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                min-height: 34px;
                padding: var(--space-2) var(--space-3);
                background: transparent;
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                font-size: var(--text-sm);
                white-space: nowrap;
            }
            .btn:hover { border-color: var(--accent); color: var(--text-primary); }
            .btn.primary { background: var(--accent); color: white; border-color: var(--accent); }
            .btn.danger { background: var(--error); color: white; border-color: var(--error); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .table-wrap {
                width: 100%;
                overflow-x: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
            }
            table { width: 100%; border-collapse: collapse; min-width: 720px; }
            th, td {
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                text-align: left;
                font-size: var(--text-sm);
                color: var(--text-primary);
                vertical-align: top;
            }
            tr:last-child td { border-bottom: none; }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                background: var(--glass-solid-medium);
            }
            td.mono {
                font-family: var(--font-mono);
                color: var(--text-secondary);
                overflow-wrap: anywhere;
            }
            .compact-table table { min-width: 0; }
            .source {
                display: inline-flex;
                align-items: center;
                min-height: 22px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
            .source.company { color: var(--accent); border-color: var(--accent); }
            .source.global { color: var(--warning); border-color: var(--warning); }
            .badge-row {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                justify-content: flex-end;
            }

            .filters {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                position: relative;
                min-width: 0;
            }
            .field label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .row-input {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                padding: var(--space-2) var(--space-3);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: 100%;
                min-height: 38px;
                box-sizing: border-box;
            }

            .summary-row {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            .summary-item {
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                min-width: 0;
            }
            .summary-value {
                display: block;
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                font-size: var(--text-lg);
                overflow-wrap: anywhere;
            }
            .summary-label {
                display: block;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: var(--space-1);
            }
            .rules-error {
                color: var(--error);
                font-size: var(--text-sm);
                margin-top: var(--space-2);
            }
            .rule-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .rule-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                padding: var(--space-2);
            }
            .rule-card:focus {
                outline: 2px solid color-mix(in srgb, var(--accent) 36%, transparent);
                outline-offset: 2px;
            }
            .rule-card-head {
                display: flex;
                justify-content: space-between;
                gap: var(--space-2);
                align-items: flex-start;
                margin-bottom: var(--space-2);
            }
            .rule-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }
            .rule-grid {
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .match-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                column-gap: var(--space-2);
                row-gap: var(--space-2);
                margin-top: var(--space-2);
                align-items: end;
            }
            .rule-subtitle platform-help-hint {
                flex-shrink: 0;
            }
            .match-combo-control {
                display: grid;
                grid-template-columns: auto minmax(0, 1fr);
                gap: var(--space-1);
                align-items: center;
                box-sizing: border-box;
            }
            .match-mode-picker {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                align-self: stretch;
                padding-right: var(--space-1);
                border-right: 1px solid var(--glass-border-subtle);
                box-sizing: border-box;
            }
            .match-mode-btn {
                width: 24px;
                height: 24px;
                min-width: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: 1px solid transparent;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
            }
            .match-mode-btn:hover,
            .match-mode-btn:focus-visible {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                outline: none;
            }
            .match-mode-btn[aria-pressed="true"] {
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 13%, transparent);
                border-color: color-mix(in srgb, var(--accent) 38%, transparent);
            }
            .match-value-input {
                padding: 0 var(--space-2);
            }
            .match-value-input:disabled {
                color: var(--text-tertiary);
                cursor: not-allowed;
            }
            .rule-subsection {
                margin-top: var(--space-2);
                padding-top: var(--space-2);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .rule-subtitle {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: var(--space-2);
            }
            .kv-editor-row {
                display: grid;
                grid-template-columns: minmax(160px, 1fr) minmax(180px, 1fr) auto;
                gap: var(--space-2);
                align-items: end;
                margin-bottom: var(--space-2);
            }
            .present-row {
                display: grid;
                grid-template-columns: minmax(220px, 1fr) auto;
                gap: var(--space-2);
                align-items: end;
                margin-bottom: var(--space-2);
            }
            .rule-card .btn {
                min-height: 30px;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
            }
            .rule-card platform-field {
                min-width: 0;
            }
            .json-details {
                margin-top: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                overflow: hidden;
            }
            .json-details summary {
                cursor: pointer;
                padding: var(--space-3);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                background: var(--glass-solid-medium);
            }
            .json-details platform-json-editor {
                border: none;
                border-radius: 0;
            }

            @media (max-width: 900px) {
                .company-panel,
                .split,
                .filters,
                .summary-row,
                .rule-grid,
                .match-grid,
                .kv-editor-row,
                .present-row {
                    grid-template-columns: 1fr;
                }
                .company-meta { grid-template-columns: 1fr; }
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    constructor() {
        super();
        this._tab = 'companies';
        this._companyId = '';
        this._companyName = '';
        this._companySubdomain = '';
        this._companyQuery = '';
        this._facetOpen = false;
        this._pricesDraft = null;
        this._companyPricesDraft = null;
        this._rulesDraft = null;
        this._rulesDraftError = '';
        this._matchModeDraft = {};
        this._usageFilters = {};
        this._usageFacetOpen = null;
        this._pendingRuleScrollId = null;

        this._companies = this.useOp('frontend/admin_billing_companies');
        this._companyResolve = this.useOp('frontend/admin_billing_company_resolve');
        this._pricesGlobal = this.useOp('frontend/admin_billing_prices_global_load');
        this._pricesGlobalSave = this.useOp('frontend/admin_billing_prices_global_update');
        this._companyPrices = this.useOp('frontend/admin_billing_company_prices_load');
        this._companyPricesSave = this.useOp('frontend/admin_billing_company_prices_update');
        this._rules = this.useOp('frontend/admin_billing_rules_load');
        this._rulesSave = this.useOp('frontend/admin_billing_rules_update');
        this._rulesDefault = this.useOp('frontend/admin_billing_rules_default_load');
        this._usage = this.useOp('frontend/admin_billing_usage_load');
        this._facets = this.useFacets('frontend/admin_billing_facets');
        this._systemAccessLeave = this.useOp('frontend/admin_system_access_leave');

        this._loadedTabs = new Set();
    }
    private _pendingRuleScrollId: string | null;
    private _companies: OpController;
    private _companyResolve: OpController;
    private _pricesGlobal: OpController;
    private _pricesGlobalSave: OpController;
    private _companyPrices: OpController;
    private _companyPricesSave: OpController;
    private _rules: OpController;
    private _rulesSave: OpController;
    private _rulesDefault: OpController;
    private _usage: OpController;
    private _facets: FacetsController;
    private _systemAccessLeave: OpController;
    private _loadedTabs: Set<string>;


    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        if (this._tab === 'companies' && !this._loadedTabs.has('companies')) {
            this._loadedTabs.add('companies');
            this._companies.run({ limit: COMPANIES_PAGE_SIZE, offset: 0 });
        }
        if (this._tab === 'prices_rules' && !this._loadedTabs.has('prices_rules')) {
            this._loadedTabs.add('prices_rules');
            this._pricesGlobal.run(null);
        }
        if (this._tab === 'usage' && !this._loadedTabs.has('usage')) {
            this._loadedTabs.add('usage');
            this._usage.run(this._usagePayload(0, this._usage.state.limit as number));
        }
    }

    _selectTab(tab: string) {
        this._tab = tab;
    }

    _companyLabelFromParts(companyId: string, name: string, subdomain: string) {
        const visibleName = typeof name === 'string' && name.length > 0 ? name : companyId;
        const visibleSlug = typeof subdomain === 'string' && (subdomain as string).length > 0 ? subdomain : companyId;
        return `${visibleName} (${visibleSlug})`;
    }

    _companyPartsFromFacet(item: Record<string, unknown>) {
        const value = item.value;
        if (typeof value !== 'string' || value.length === 0) {
            throw new Error('billing-admin: company facet value required');
        }
        const label = typeof item.label === 'string' && item.label.length > 0 ? item.label : value;
        if (label.endsWith(')') && label.includes('(')) {
            const openIdx = label.lastIndexOf('(');
            const name = label.slice(0, openIdx).trim();
            const subdomain = label.slice(openIdx + 1, -1).trim();
            return {
                companyId: value,
                name: name.length > 0 ? name : value,
                subdomain: subdomain.length > 0 ? subdomain : value,
                label,
            };
        }
        return {
            companyId: value,
            name: label,
            subdomain: value,
            label: this._companyLabelFromParts(value, label, value),
        };
    }

    async _loadCompanyContext(companyId: string) {
        this._companyPricesDraft = null;
        this._rulesDraft = null;
        this._rulesDraftError = '';
        this._usageFilters = { ...this._usageFilters, company_id: companyId };
        await Promise.all([
            this._companyPrices.run({ company_id: companyId }),
            this._rules.run({ company_id: companyId }),
        ]);
        if (this._tab === 'usage') {
            this._usage.run(this._usagePayload(0, this._usage.state.limit as number));
        }
    }

    async _resolveCompany() {
        const q = this._companyQuery.trim();
        if (!q) return;
        const result = await this._companyResolve.run({ q });
        if (!isPlainRecord(result) || typeof result.company_id !== 'string' || result.company_id.length === 0) return;
        if (typeof result.name !== 'string' || typeof result.subdomain !== 'string') {
            throw new Error('billing-admin: company resolve name and subdomain required');
        }
        this._companyId = result.company_id;
        this._companyName = result.name;
        this._companySubdomain = result.subdomain;
        this._companyQuery = this._companyLabelFromParts(result.company_id, result.name, result.subdomain);
        await this._loadCompanyContext(result.company_id);
    }

    _onCompanyInput(value: string) {
        this._companyQuery = value;
        if (value && value.length >= 2) {
            this._facetOpen = true;
            this._facets.search('companies', value);
        } else {
            this._facetOpen = false;
        }
    }

    async _selectCompanyFromFacet(item: Record<string, unknown>) {
        if (typeof item.value !== 'string' || item.value.length === 0) return;
        const parts = this._companyPartsFromFacet(item);
        this._companyId = parts.companyId;
        this._companyName = parts.name;
        this._companySubdomain = parts.subdomain;
        this._companyQuery = parts.label;
        this._facetOpen = false;
        await this._loadCompanyContext(parts.companyId);
    }

    _renderForbiddenOrUnavailable() {
        const terminal = this._companies.state && this._companies.state.terminal;
        if (terminal === 'forbidden') {
            return html`<platform-empty-state icon="lock" title=${this.t('platform_billing_page.forbidden')}></platform-empty-state>`;
        }
        if (terminal === 'unavailable') {
            return html`<platform-empty-state icon="alert-triangle" title=${this.t('platform_billing_page.unavailable')}></platform-empty-state>`;
        }
        return null;
    }

    _renderTabs() {
        return html`
            <div class="tabs" role="tablist" aria-label=${this.t('platform_billing_page.tabs_region_label')}>
                ${TABS.map((tab) => html`
                    <button
                        class="tab"
                        role="tab"
                        aria-selected=${this._tab === tab}
                        @click=${() => this._selectTab(tab)}
                    >${this.t(`platform_billing_page.tab_${tab}`)}</button>
                `)}
            </div>
        `;
    }

    _renderCompanyScope() {
        const items = objectList(this._facets.items('companies'), 'billing-admin: company facets');
        return html`
            <div class="company-panel">
                <div class="company-search">
                    <platform-field
                        type="string"
                        input-type="search"
                        mode="edit"
                        pill-density="compact"
                        .label=${this.t('platform_billing_page.billing_scope_banner_title')}
                        .placeholder=${this.t('platform_billing_page.billing_company_search_placeholder')}
                        .value=${this._companyQuery}
                        ?disabled=${this._companyResolve.busy}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing company scope: company query expects detail.value string');
                            }
                            this._onCompanyInput(e.detail.value);
                        }}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this._resolveCompany(); }}
                        @platform-field-managed-focus-out=${() => setTimeout(() => { this._facetOpen = false; }, 180)}
                    >
                        <button
                            slot="suffix"
                            type="button"
                            class="field-search-btn"
                            ?disabled=${this._companyResolve.busy}
                            title=${this.t('platform_billing_page.billing_company_apply')}
                            aria-label=${this.t('platform_billing_page.billing_company_apply')}
                            @click=${() => this._resolveCompany()}
                        >
                            <platform-icon name="refresh" size="15"></platform-icon>
                        </button>
                    ></platform-field>
                    ${this._facetOpen ? html`
                        <div class="suggest">
                            ${items.length === 0
                                ? html`<div class="suggest-item">${this.t('platform_billing_page.empty')}</div>`
                                : items.map((it) => html`
                                    <div
                                        class="suggest-item"
                                        @mousedown=${(e: Event) => { e.preventDefault(); this._selectCompanyFromFacet(it); }}
                                    >
                                        ${typeof it.label === 'string' && it.label.length > 0 ? it.label : it.value}
                                    </div>
                                `)}
                        </div>
                    ` : null}
                </div>
                <div class="company-meta">
                    <div class="meta-item">
                        <span class="meta-label">${this.t('platform_billing_page.billing_scope_active_label')}</span>
                        <span class="meta-value">${this._companyId ? this._companyId : this.t('platform_billing_page.billing_scope_none_short')}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">${this.t('platform_billing_page.billing_scope_display_label')}</span>
                        <span class="meta-value">${this._companyId ? this._companyLabelFromParts(this._companyId, this._companyName, this._companySubdomain) : this.t('platform_billing_page.billing_scope_none_hint')}</span>
                    </div>
                </div>
            </div>
        `;
    }

    _renderCompaniesTab() {
        const records = objectList(this._companies.state.items, 'billing-admin: companies');
        const hasMore = !!(this._companies.state && this._companies.state.hasMore);
        const offset = this._companies.state.offset;
        const busy = this._companies.busy;
        const forbidden = this._renderForbiddenOrUnavailable();
        if (forbidden) return forbidden;
        if (busy && records.length === 0) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        return html`
            <section>
                <div class="section-head">
                    <div>
                        <div class="section-title">${this.t('platform_billing_page.companies_overview_heading')}</div>
                        <div class="section-subtitle">${this.t('platform_billing_page.companies_overview_hint')}</div>
                    </div>
                </div>
                ${records.length === 0
                    ? html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`
                    : html`
                        <div class="table-wrap">
                            <table>
                                <thead><tr>
                                    <th>${this.t('platform_billing_page.col_company_id')}</th>
                                    <th>${this.t('platform_billing_page.col_name')}</th>
                                    <th>${this.t('platform_billing_page.col_subdomain')}</th>
                                    <th>${this.t('platform_billing_page.col_tariff')}</th>
                                    <th>${this.t('platform_billing_page.col_balance')}</th>
                                    <th>${this.t('platform_billing_page.col_monthly_budget')}</th>
                                    <th>${this.t('platform_billing_page.col_spent_month')}</th>
                                    <th>${this.t('platform_billing_page.col_actions')}</th>
                                </tr></thead>
                                <tbody>
                                    ${records.map((r) => {
                                        const companyId = r.company_id;
                                        if (typeof companyId !== 'string' || companyId.length === 0) {
                                            throw new Error('billing-admin: company_id required');
                                        }
                                        return html`
                                        <tr>
                                            <td class="mono">${companyId}</td>
                                            <td>${displayText(r.name)}</td>
                                            <td>${displayText(r.subdomain)}</td>
                                            <td>${displayText(r.tariff_plan)}</td>
                                            <td>${this._formatNumber(r.balance, 2)}</td>
                                            <td>${this._formatNumber(r.monthly_budget, 2)}</td>
                                            <td>${this._formatNumber(r.current_month_spent, 2)}</td>
                                            <td>
                                                <div class="actions">
                                                    <button class="btn" @click=${() => this.openModal(FrontendBalanceGrantModal, { company_id: companyId })}>
                                                        <platform-icon name="chart" size="16"></platform-icon>
                                                        ${this.t('platform_billing_page.balance_grant_button')}
                                                    </button>
                                                    <button class="btn" @click=${() => this.openModal(FrontendSystemAccessModal, { company_id: companyId })}>
                                                        <platform-icon name="login" size="16"></platform-icon>
                                                        ${this.t('platform_billing_page.system_access_enter')}
                                                    </button>
                                                    <button class="btn danger" @click=${() => this._systemAccessLeave.run({ company_id: companyId })}>
                                                        <platform-icon name="logout" size="16"></platform-icon>
                                                        ${this.t('platform_billing_page.system_access_leave')}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    `;
                                    })}
                                </tbody>
                            </table>
                        </div>
                    `}
                <div class="actions">
                    <button class="btn" ?disabled=${busy} @click=${() => this._companies.run({ limit: COMPANIES_PAGE_SIZE, offset: 0 })}>
                        <platform-icon name="refresh" size="16"></platform-icon>
                        ${this.t('platform_billing_page.reload')}
                    </button>
                    ${hasMore ? html`
                        <button class="btn primary" ?disabled=${busy}
                            @click=${() => this._companies.run({ limit: COMPANIES_PAGE_SIZE, offset })}>
                            ${this.t('platform_billing_page.companies_load_more')}
                        </button>
                    ` : null}
                </div>
            </section>
        `;
    }

    _flattenPrices(catalog: unknown) {
        if (!isPlainRecord(catalog)) return [];
        const out: PriceRow[] = [];
        for (const [category, resources] of Object.entries(catalog)) {
            if (!resources || typeof resources !== 'object') continue;
            for (const [resource_name, price] of Object.entries(resources)) {
                out.push({ category, resource_name, price: String(price) });
            }
        }
        out.sort((a, b) => `${a.category}:${a.resource_name}`.localeCompare(`${b.category}:${b.resource_name}`));
        return out;
    }

    _catalogHas(catalog: Record<string, unknown> | null | undefined, category: string, resourceName: string) {
        if (!catalog || typeof catalog !== 'object') return false;
        const bucket = catalog[category];
        return !!(bucket && typeof bucket === 'object' && Object.prototype.hasOwnProperty.call(bucket, resourceName));
    }

    _priceSource(row: { category: string; resource_name: string }, companyOverride: Record<string, unknown> | null | undefined, globalOverride: Record<string, unknown> | null | undefined) {
        if (this._catalogHas(companyOverride, row.category, row.resource_name)) return 'company';
        if (this._catalogHas(globalOverride, row.category, row.resource_name)) return 'global';
        return 'base';
    }

    _catalogValue(catalog: Record<string, unknown> | null | undefined, category: string, resourceName: string) {
        if (!catalog || typeof catalog !== 'object') return null;
        const bucket = catalog[category];
        if (!isPlainRecord(bucket)) return null;
        if (!Object.prototype.hasOwnProperty.call(bucket, resourceName)) return null;
        const value = bucket[resourceName];
        return typeof value === 'number' && !Number.isNaN(value) ? value : null;
    }

    _tariffMultiplier(tariffMultipliers: Record<string, unknown> | null | undefined, category: string, resourceName: string) {
        if (!tariffMultipliers || typeof tariffMultipliers !== 'object') return 1;
        const bucket = tariffMultipliers[category];
        if (!isPlainRecord(bucket)) return 1;
        if (Object.prototype.hasOwnProperty.call(bucket, resourceName)) {
            const value = bucket[resourceName];
            return typeof value === 'number' && !Number.isNaN(value) ? value : 1;
        }
        if (Object.prototype.hasOwnProperty.call(bucket, '*')) {
            const value = bucket['*'];
            return typeof value === 'number' && !Number.isNaN(value) ? value : 1;
        }
        return 1;
    }

    _pricingLayerRows({ staticBase, globalOverride, companyOverride, effective, unitEffective, tariffMultipliers }: Record<string, Record<string, unknown> | null>) {
        const keys = new Set<string>();
        for (const catalog of [staticBase, globalOverride, companyOverride, effective, unitEffective]) {
            if (!catalog || typeof catalog !== 'object') continue;
            for (const [category, resources] of Object.entries(catalog)) {
                if (!resources || typeof resources !== 'object') continue;
                for (const resourceName of Object.keys(resources)) {
                    keys.add(`${category}\u0000${resourceName}`);
                }
            }
        }
        const rows: PricingLayerRow[] = [];
        for (const key of keys) {
            const [category = '', resourceName = ''] = key.split('\u0000');
            const row = {
                category,
                resource_name: resourceName,
                static_base: this._catalogValue(staticBase, category, resourceName),
                global_override: this._catalogValue(globalOverride, category, resourceName),
                company_override: this._catalogValue(companyOverride, category, resourceName),
                base_effective: this._catalogValue(effective, category, resourceName),
                tariff_multiplier: this._tariffMultiplier(tariffMultipliers, category, resourceName),
                unit_effective: this._catalogValue(unitEffective, category, resourceName),
            };
            rows.push({
                ...row,
                source: this._priceSource(row, companyOverride, globalOverride),
            });
        }
        rows.sort((a, b) => `${a.category}:${a.resource_name}`.localeCompare(`${b.category}:${b.resource_name}`));
        return rows;
    }

    _buildCatalog(rows: readonly PriceRow[]) {
        const catalog: Record<string, Record<string, number>> = {};
        for (const r of rows) {
            const cat = r.category.trim();
            const name = r.resource_name.trim();
            if (cat.length === 0 || name.length === 0) continue;
            const price = Number(r.price);
            if (Number.isNaN(price)) throw new Error(`invalid price for ${cat}:${name}`);
            const bucket = catalog[cat];
            if (bucket === undefined) catalog[cat] = { [name]: price };
            else bucket[name] = price;
        }
        return catalog;
    }

    _renderPriceSource(source: string) {
        return html`<span class="source ${source}">${this.t(`platform_billing_page.price_source_${source}`)}</span>`;
    }

    _renderReadonlyPriceTable(rows: ReadonlyArray<PriceRow & { source?: string }>, showSource: boolean) {
        if (rows.length === 0) {
            return html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`;
        }
        return html`
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>${this.t('platform_billing_page.price_col_category')}</th>
                        <th>${this.t('platform_billing_page.price_col_resource')}</th>
                        <th>${this.t('platform_billing_page.price_col_price')}</th>
                        ${showSource ? html`<th>${this.t('platform_billing_page.price_col_source')}</th>` : null}
                    </tr></thead>
                    <tbody>
                        ${rows.map((r) => html`
                            <tr>
                                <td>${r.category}</td>
                                <td class="mono">${r.resource_name}</td>
                                <td>${r.price}</td>
                                ${showSource && typeof r.source === 'string' ? html`<td>${this._renderPriceSource(r.source)}</td>` : null}
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderPricingLayerTable(rows: readonly PricingLayerRow[], showCompanyPricing: boolean) {
        if (rows.length === 0) {
            return html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`;
        }
        return html`
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>${this.t('platform_billing_page.price_col_category')}</th>
                        <th>${this.t('platform_billing_page.price_col_resource')}</th>
                        <th>${this.t('platform_billing_page.price_col_static_base')}</th>
                        <th>${this.t('platform_billing_page.price_col_global_override')}</th>
                        ${showCompanyPricing ? html`<th>${this.t('platform_billing_page.price_col_company_override')}</th>` : null}
                        <th>${this.t('platform_billing_page.price_col_base_effective')}</th>
                        ${showCompanyPricing ? html`<th>${this.t('platform_billing_page.price_col_tariff_multiplier')}</th>` : null}
                        ${showCompanyPricing ? html`<th>${this.t('platform_billing_page.price_col_final_unit')}</th>` : null}
                        <th>${this.t('platform_billing_page.price_col_source')}</th>
                    </tr></thead>
                    <tbody>
                        ${rows.map((r) => html`
                            <tr>
                                <td>${r.category}</td>
                                <td class="mono">${r.resource_name}</td>
                                <td>${this._formatNumber(r.static_base, 8)}</td>
                                <td>${this._formatNumber(r.global_override, 8)}</td>
                                ${showCompanyPricing ? html`<td>${this._formatNumber(r.company_override, 8)}</td>` : null}
                                <td>${this._formatNumber(r.base_effective, 8)}</td>
                                ${showCompanyPricing ? html`<td>${this._formatNumber(r.tariff_multiplier, 4)}</td>` : null}
                                ${showCompanyPricing ? html`<td>${this._formatNumber(r.unit_effective, 8)}</td>` : null}
                                <td>${this._renderPriceSource(r.source)}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderPricesEditor(rows: PriceRow[], onChange: (rows: PriceRow[]) => void) {
        return html`
            ${rows.length === 0 ? html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.price_override_empty')}></platform-empty-state>` : html`
                <div class="table-wrap compact-table">
                    <table>
                        <thead><tr>
                            <th>${this.t('platform_billing_page.price_col_category')}</th>
                            <th>${this.t('platform_billing_page.price_col_resource')}</th>
                            <th>${this.t('platform_billing_page.price_col_price')}</th>
                            <th>${this.t('platform_billing_page.col_actions')}</th>
                        </tr></thead>
                        <tbody>
                            ${rows.map((r, idx) => html`
                                <tr>
                                    <td>
                                        <platform-field
                                            type="string"
                                            mode="edit"
                                            label=""
                                            .value=${r.category}
                                            @change=${(e: CustomEvent) => {
                                                if (!e.detail || typeof e.detail.value !== 'string') {
                                                    throw new Error('billing prices: category expects detail.value string');
                                                }
                                                const row = rows[idx];
                                                if (row === undefined) {
                                                    throw new Error('billing prices: row missing');
                                                }
                                                row.category = e.detail.value;
                                                onChange([...rows]);
                                            }}
                                        ></platform-field>
                                    </td>
                                    <td>
                                        <platform-field
                                            type="string"
                                            mode="edit"
                                            label=""
                                            .value=${r.resource_name}
                                            @change=${(e: CustomEvent) => {
                                                if (!e.detail || typeof e.detail.value !== 'string') {
                                                    throw new Error('billing prices: resource_name expects detail.value string');
                                                }
                                                const row = rows[idx];
                                                if (row === undefined) {
                                                    throw new Error('billing prices: row missing');
                                                }
                                                row.resource_name = e.detail.value;
                                                onChange([...rows]);
                                            }}
                                        ></platform-field>
                                    </td>
                                    <td>
                                        <platform-field
                                            type="number"
                                            mode="edit"
                                            label=""
                                            .value=${Number(r.price)}
                                            @change=${(e: CustomEvent) => {
                                                if (!e.detail || e.detail.value === null || typeof e.detail.value !== 'number') {
                                                    throw new Error('billing prices: price expects numeric detail.value');
                                                }
                                                const row = rows[idx];
                                                if (row === undefined) {
                                                    throw new Error('billing prices: row missing');
                                                }
                                                row.price = String(e.detail.value);
                                                onChange([...rows]);
                                            }}
                                        ></platform-field>
                                    </td>
                                    <td>
                                        <button class="btn" @click=${() => { rows.splice(idx, 1); onChange([...rows]); }}>
                                            <platform-icon name="trash" size="16"></platform-icon>
                                            ${this.t('platform_billing_page.price_remove_row')}
                                        </button>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            `}
            <div class="actions">
                <button class="btn" @click=${() => onChange([...rows, { category: '', resource_name: '', price: '0' }])}>
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.t('platform_billing_page.price_add_row')}
                </button>
            </div>
        `;
    }

    _syncPriceDrafts() {
        const pricesData = this._pricesGlobal.lastResult;
        if (this._pricesDraft === null && isPlainRecord(pricesData)) {
            this._pricesDraft = this._flattenPrices(pricesData.storage_override);
        }
        const companyPrices = this._companyPrices.lastResult;
        if (this._companyId && this._companyPricesDraft === null && isPlainRecord(companyPrices) && companyPrices.company_id === this._companyId) {
            this._companyPricesDraft = this._flattenPrices(companyPrices.storage_override);
        }
        const rulesData = this._rules.lastResult;
        if (this._companyId && this._rulesDraft === null && isPlainRecord(rulesData) && rulesData.document) {
            this._rulesDraft = JSON.stringify(rulesData.document, null, 2);
        }
    }

    _saveGlobalPrices() {
        const rows = this._pricesDraft;
        if (rows === null) throw new Error('billing-admin: prices draft required');
        try {
            this._pricesGlobalSave.run({ catalog: this._buildCatalog(rows) });
        } catch (_err) {
            this.toast('platform_billing_page.price_invalid_row', { type: 'error' });
        }
    }

    _saveCompanyPrices() {
        const rows = this._companyPricesDraft;
        if (rows === null) throw new Error('billing-admin: company prices draft required');
        try {
            this._companyPricesSave.run({
                company_id: this._companyId,
                catalog: this._buildCatalog(rows),
            });
        } catch (_err) {
            this.toast('platform_billing_page.price_invalid_row', { type: 'error' });
        }
    }

    _renderEffectivePricesSection() {
        const pricesData = this._pricesGlobal.lastResult;
        const companyPricesResult = this._companyPrices.lastResult;
        const companyPrices = isPlainRecord(companyPricesResult) && companyPricesResult.company_id === this._companyId ? companyPricesResult : null;
        const sourceData = this._companyId && companyPrices ? companyPrices : pricesData;
        if (!sourceData && (this._pricesGlobal.busy || this._companyPrices.busy)) {
            return html`<section><platform-empty-state loading></platform-empty-state></section>`;
        }
        const showCompanyPricing = !!(this._companyId && companyPrices);
        const staticBase = nestedRecord(sourceData, 'static_base');
        const effective = nestedRecord(sourceData, 'effective');
        const globalOverride = nestedRecord(pricesData, 'storage_override');
        const companyOverride = showCompanyPricing ? nestedRecord(companyPrices, 'storage_override') : null;
        const rows = this._pricingLayerRows({
            staticBase,
            globalOverride,
            companyOverride,
            effective,
            unitEffective: showCompanyPricing ? nestedRecord(companyPrices, 'unit_effective') : null,
            tariffMultipliers: showCompanyPricing ? nestedRecord(companyPrices, 'tariff_multipliers') : null,
        });
        return html`
            <section>
                <div class="section-head">
                    <div>
                        <div class="section-title">${this.t('platform_billing_page.price_effective_title')}</div>
                        <div class="section-subtitle">
                            ${showCompanyPricing
                                ? this.t('platform_billing_page.price_effective_company_layers_hint')
                                : this.t('platform_billing_page.price_effective_global_hint')}
                        </div>
                    </div>
                    <div class="badge-row">
                        <span class="source">${this.t('platform_billing_page.billing_readonly_catalog_rows', { count: rows.length })}</span>
                        ${showCompanyPricing ? html`
                            <span class="source">${this.t('platform_billing_page.price_tariff_badge', { tariff: displayText(companyPrices ? companyPrices.tariff_plan : '') })}</span>
                        ` : null}
                    </div>
                </div>
                ${this._renderPricingLayerTable(rows, showCompanyPricing)}
            </section>
        `;
    }

    _renderPriceOverridesSection() {
        const globalRows = Array.isArray(this._pricesDraft) ? this._pricesDraft : [];
        const companyRows = Array.isArray(this._companyPricesDraft) ? this._companyPricesDraft : [];
        return html`
            <div class="split">
                <section>
                    <div class="section-head">
                        <div>
                            <div class="section-title">${this.t('platform_billing_page.price_global_override_title')}</div>
                            <div class="section-subtitle">${this.t('platform_billing_page.hint_prices_global_scope')}</div>
                        </div>
                    </div>
                    ${this._renderPricesEditor(globalRows, (rows: PriceRow[]) => { this._pricesDraft = rows; })}
                    <div class="actions">
                        <button class="btn primary" ?disabled=${this._pricesGlobalSave.busy} @click=${() => this._saveGlobalPrices()}>
                            <platform-icon name="save" size="16"></platform-icon>
                            ${this.t('platform_billing_page.save_override')}
                        </button>
                        <button class="btn" ?disabled=${this._pricesGlobal.busy}
                            @click=${() => { this._pricesDraft = null; this._pricesGlobal.run(null); }}>
                            <platform-icon name="refresh" size="16"></platform-icon>
                            ${this.t('platform_billing_page.reload')}
                        </button>
                    </div>
                </section>

                <section>
                    <div class="section-head">
                        <div>
                            <div class="section-title">${this.t('platform_billing_page.subsection_company_prices_title')}</div>
                            <div class="section-subtitle">${this.t('platform_billing_page.hint_company_prices_scope')}</div>
                        </div>
                    </div>
                    ${this._companyId
                        ? html`
                            ${this._renderPricesEditor(companyRows, (rows: PriceRow[]) => { this._companyPricesDraft = rows; })}
                            <div class="actions">
                                <button class="btn primary" ?disabled=${this._companyPricesSave.busy} @click=${() => this._saveCompanyPrices()}>
                                    <platform-icon name="save" size="16"></platform-icon>
                                    ${this.t('platform_billing_page.save_company_override')}
                                </button>
                            </div>
                        `
                        : html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.billing_company_required')}></platform-empty-state>`}
                </section>
            </div>
        `;
    }

    _rulesDocFromDraft() {
        const draft = typeof this._rulesDraft === 'string' ? this._rulesDraft.trim() : '';
        if (!draft) return null;
        try {
            const doc = JSON.parse(draft);
            if (!doc || typeof doc !== 'object') return null;
            return doc;
        } catch (_err) {
            return null;
        }
    }

    _emptyRulesDoc(): BillingRulesDoc {
        return { version: 1, application_mode: 'first_win', rules: [] };
    }

    _cloneRulesDoc(): BillingRulesDoc {
        const parsed = this._rulesDocFromDraft();
        const source = isPlainRecord(parsed) ? parsed : this._emptyRulesDoc();
        const version = source.version;
        const applicationMode = source.application_mode;
        const doc: BillingRulesDoc = {
            version: version === undefined || version === null || version === '' || version === 0 ? 1 : version,
            application_mode: typeof applicationMode === 'string' && applicationMode.length > 0 ? applicationMode : 'first_win',
            rules: [],
        };
        const rules = source.rules;
        if (rules !== undefined && rules !== null) {
            if (!Array.isArray(rules)) throw new Error('billing-admin: rules must be a list');
            for (const item of rules) {
                if (!isPlainRecord(item)) throw new Error('billing-admin: rule must be an object');
                doc.rules.push(billingRule(item));
            }
        }
        for (const [key, field] of Object.entries(source)) {
            if (key === 'rules' || key === 'version' || key === 'application_mode') continue;
            doc[key] = field;
        }
        return doc;
    }

    _setRulesDoc(doc: BillingRulesDoc) {
        this._rulesDraft = JSON.stringify(doc, null, 2);
        this._rulesDraftError = '';
    }

    _updateRulesDoc(mutator: (doc: BillingRulesDoc) => void) {
        const doc = this._cloneRulesDoc();
        mutator(doc);
        this._setRulesDoc(doc);
    }

    _emptyRule() {
        return {
            rule_id: `rule_${Date.now().toString(36)}`,
            enabled: true,
            priority: 100,
            exclusive_group: null,
            resource_name: 'llm:*',
            usage_type: 'llm_request',
            quantity_from: 'const:1',
            match: {
                operation_name_prefix: '',
                attribute_equals: {},
                attribute_regex: {},
                attribute_keys_present: [],
            },
        };
    }

    _addRuleAndScroll() {
        const rule = this._emptyRule();
        this._pendingRuleScrollId = rule.rule_id;
        this._updateRulesDoc((draft: BillingRulesDoc) => {
            draft.rules.push(rule);
        });
        this.updateComplete.then(() => {
            requestAnimationFrame(() => this._scrollToPendingRule());
        });
    }

    _scrollToPendingRule() {
        const targetId = this._pendingRuleScrollId;
        this._pendingRuleScrollId = null;
        const cards: HTMLElement[] = [];
        for (const node of this.renderRoot.querySelectorAll('.rule-card')) {
            if (!(node instanceof HTMLElement)) {
                throw new Error('billing-admin: rule card must be an element');
            }
            cards.push(node);
        }
        if (cards.length === 0) return;
        const target = cards.find((card) => card.dataset.ruleId === targetId) || cards[cards.length - 1];
        if (!target) return;
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.focus({ preventScroll: true });
    }

    _ensureRule(doc: BillingRulesDoc, idx: number): BillingRule {
        const rule = doc.rules[idx];
        if (rule === undefined) throw new Error('billing-admin: rule missing');
        rule.match = billingMatch(rule.match);
        return rule;
    }

    _setRuleField(idx: number, field: string, value: unknown) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            rule[field] = value;
        });
    }

    _setRuleMatchField(idx: number, field: string, value: unknown) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            if (typeof value === 'string' && value.trim().length === 0) {
                delete rule.match[field];
            } else {
                rule.match[field] = value;
            }
        });
    }

    _matchModeDraftKey(idx: number, rule: BillingRule, scope: string) {
        const rid = rule && typeof rule.rule_id === 'string' && rule.rule_id.length > 0
            ? rule.rule_id
            : String(idx);
        return `${idx}:${rid}:${scope}`;
    }

    _setMatchModeDraft(key: string, mode: string) {
        this._matchModeDraft = { ...this._matchModeDraft, [key]: mode };
    }

    _clearMatchModeDraft(key: string) {
        const next = { ...this._matchModeDraft };
        delete next[key];
        this._matchModeDraft = next;
    }

    _setRuleMatchMode(idx: number, scope: string, mode: string) {
        const fields = matchModeFields(scope);
        if (!fields) return;
        const doc = this._cloneRulesDoc();
        const rule = this._ensureRule(doc, idx);
        const key = this._matchModeDraftKey(idx, rule, scope);
        let previous = '';
        for (const field of fields) {
            if (typeof rule.match[field] === 'string' && rule.match[field].length > 0) {
                previous = rule.match[field];
            }
            delete rule.match[field];
        }
        const target = fields.find((field) => field.endsWith(mode));
        if (target && previous.length > 0) {
            rule.match[target] = previous;
        }
        this._setRulesDoc(doc);
        if (!target) {
            this._clearMatchModeDraft(key);
        } else if (previous.length > 0) {
            this._clearMatchModeDraft(key);
        } else {
            this._setMatchModeDraft(key, mode);
        }
    }

    _actualMatchMode(match: Record<string, unknown>, scope: string) {
        if (!match || typeof match !== 'object') return 'none';
        if (scope === 'operation') {
            if (typeof match.operation_name_regex === 'string' && match.operation_name_regex.length > 0) return 'regex';
            if (typeof match.operation_name_equals === 'string' && match.operation_name_equals.length > 0) return 'equals';
            if (typeof match.operation_name_prefix === 'string' && match.operation_name_prefix.length > 0) return 'prefix';
        }
        if (scope === 'service') {
            if (typeof match.service_name_regex === 'string' && match.service_name_regex.length > 0) return 'regex';
            if (typeof match.service_name_equals === 'string' && match.service_name_equals.length > 0) return 'equals';
        }
        if (scope === 'event') {
            if (typeof match.event_type_regex === 'string' && match.event_type_regex.length > 0) return 'regex';
            if (typeof match.event_type_equals === 'string' && match.event_type_equals.length > 0) return 'equals';
        }
        return 'none';
    }

    _matchMode(match: BillingMatch, scope: string, idx: number | null = null, rule: BillingRule | null = null) {
        const actual = this._actualMatchMode(match, scope);
        if (actual !== 'none') return actual;
        if (idx === null || rule === null) return 'none';
        const draft = this._matchModeDraft[this._matchModeDraftKey(idx, rule, scope)];
        return typeof draft === 'string' && draft.length > 0 ? draft : 'none';
    }

    _matchValue(match: Record<string, unknown>, scope: string) {
        if (!match || typeof match !== 'object') return '';
        if (scope === 'operation') {
            return firstText([match.operation_name_regex, match.operation_name_equals, match.operation_name_prefix]);
        }
        if (scope === 'service') {
            return firstText([match.service_name_regex, match.service_name_equals]);
        }
        if (scope === 'event') {
            return firstText([match.event_type_regex, match.event_type_equals]);
        }
        return '';
    }

    _setMatchValueByMode(idx: number, scope: string, value: unknown, modeHint: string | null = null) {
        const doc = this._cloneRulesDoc();
        const rule = this._ensureRule(doc, idx);
        const mode = modeHint || this._matchMode(rule.match, scope, idx, rule);
        const field = matchFieldName(scope, mode);
        if (!field) return;
        const key = this._matchModeDraftKey(idx, rule, scope);
        if (typeof value === 'string' && value.trim().length === 0) {
            delete rule.match[field];
            this._setRulesDoc(doc);
            this._setMatchModeDraft(key, mode);
            return;
        }
        rule.match[field] = value;
        this._setRulesDoc(doc);
        this._clearMatchModeDraft(key);
    }

    _quantityParts(quantityFrom: unknown) {
        const value = typeof quantityFrom === 'string' ? quantityFrom : '';
        if (value.startsWith('attr:')) return { mode: 'attr', value: value.slice(5) };
        if (value.startsWith('const:')) return { mode: 'const', value: value.slice(6) };
        return { mode: 'const', value: '1' };
    }

    _setQuantityMode(idx: number, mode: string) {
        const rule = this._cloneRulesDoc().rules[idx];
        const current = this._quantityParts(rule && rule.quantity_from);
        const nextValue = mode === 'attr'
            ? (current.mode === 'attr' ? current.value : 'platform.billing.quantity')
            : (current.mode === 'const' ? current.value : '1');
        this._setRuleField(idx, 'quantity_from', `${mode}:${nextValue}`);
    }

    _setQuantityValue(idx: number, value: unknown) {
        const rule = this._cloneRulesDoc().rules[idx];
        const current = this._quantityParts(rule && rule.quantity_from);
        this._setRuleField(idx, 'quantity_from', `${current.mode}:${value}`);
    }

    _jsonScalarInput(value: unknown) {
        if (typeof value === 'string') return value;
        return JSON.stringify(value);
    }

    _parseScalarInput(value: unknown) {
        const raw = typeof value === 'string' ? value : '';
        const trimmed = raw.trim();
        if (!trimmed) return '';
        try {
            return JSON.parse(trimmed);
        } catch (_err) {
            return raw;
        }
    }

    _mapEntries(map: unknown): Array<[string, unknown]> {
        if (!isPlainRecord(map)) return [];
        return Object.entries(map);
    }

    _setMapEntry(idx: number, mapName: string, entryIndex: number, key: string, value: unknown) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            const entries = this._mapEntries(rule.match[mapName]);
            entries[entryIndex] = [key, value];
            rule.match[mapName] = Object.fromEntries(entries.filter(([k]) => typeof k === 'string' && k.length > 0));
        });
    }

    _addMapEntry(idx: number, mapName: string) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            const current = rule.match[mapName];
            rule.match[mapName] = { ...(current && typeof current === 'object' ? current : {}), '': '' };
        });
    }

    _removeMapEntry(idx: number, mapName: string, entryIndex: number) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            const entries = this._mapEntries(rule.match[mapName]);
            entries.splice(entryIndex, 1);
            rule.match[mapName] = Object.fromEntries(entries);
        });
    }

    _setPresentAttr(idx: number, entryIndex: number, value: unknown) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            rule.match.attribute_keys_present[entryIndex] = value;
            rule.match.attribute_keys_present = rule.match.attribute_keys_present.filter((v: unknown) => typeof v === 'string' && v.length > 0);
        });
    }

    _addPresentAttr(idx: number) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            rule.match.attribute_keys_present.push('');
        });
    }

    _removePresentAttr(idx: number, entryIndex: number) {
        this._updateRulesDoc((doc: BillingRulesDoc) => {
            const rule = this._ensureRule(doc, idx);
            rule.match.attribute_keys_present.splice(entryIndex, 1);
        });
    }

    _formatMatch(match: unknown) {
        if (!isPlainRecord(match)) return '';
        const parts: string[] = [];
        if (match.operation_name_equals) parts.push(`op=${match.operation_name_equals}`);
        if (match.operation_name_prefix) parts.push(`op^=${match.operation_name_prefix}`);
        if (match.operation_name_regex) parts.push(`op~=${match.operation_name_regex}`);
        if (match.service_name_equals) parts.push(`service=${match.service_name_equals}`);
        if (match.service_name_regex) parts.push(`service~=${match.service_name_regex}`);
        if (match.event_type_equals) parts.push(`event=${match.event_type_equals}`);
        if (match.event_type_regex) parts.push(`event~=${match.event_type_regex}`);
        const equals = match.attribute_equals;
        if (equals && typeof equals === 'object') {
            for (const [key, value] of Object.entries(equals)) {
                parts.push(`${key}=${String(value)}`);
            }
        }
        const regex = match.attribute_regex;
        if (regex && typeof regex === 'object') {
            for (const [key, value] of Object.entries(regex)) {
                parts.push(`${key}~=${String(value)}`);
            }
        }
        const present = Array.isArray(match.attribute_keys_present) ? match.attribute_keys_present : [];
        for (const key of present) {
            parts.push(`${key}:present`);
        }
        return parts.join(' · ');
    }

    _enumConfig(values: readonly string[] | readonly { value: string; label: string }[]) {
        return { values };
    }

    _ruleHint(key: string) {
        return this.t(`platform_billing_page.rule_hint_${key}`);
    }

    _numberOrNull(value: unknown) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    _numberOrDefault(value: unknown, fallback: number) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    _renderRulesSummary(doc: BillingRulesDoc) {
        const rules = doc && Array.isArray(doc.rules) ? doc.rules : [];
        if (rules.length === 0) {
            return html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`;
        }
        return html`
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>${this.t('platform_billing_page.rules_col_enabled')}</th>
                        <th>${this.t('platform_billing_page.rules_col_priority')}</th>
                        <th>${this.t('platform_billing_page.rules_col_rule')}</th>
                        <th>${this.t('platform_billing_page.rules_col_match')}</th>
                        <th>${this.t('platform_billing_page.rules_col_resource')}</th>
                        <th>${this.t('platform_billing_page.rules_col_quantity')}</th>
                    </tr></thead>
                    <tbody>
                        ${rules.map((rule) => html`
                            <tr>
                                <td>${rule.enabled === false ? this.t('platform_billing_page.rules_disabled') : this.t('platform_billing_page.rules_enabled')}</td>
                                <td>${rule.priority}</td>
                                <td class="mono">${rule.rule_id}</td>
                                <td class="mono">${this._formatMatch(rule.match)}</td>
                                <td class="mono">${rule.resource_name}</td>
                                <td class="mono">${rule.quantity_from}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderMatchSelector(idx: number, rule: BillingRule, scope: string, labelKey: string) {
        const mode = this._matchMode(rule.match, scope, idx, rule);
        const values = scope === 'operation'
            ? [
                { value: 'none', label: this.t('platform_billing_page.rules_match_none'), icon: 'close' },
                { value: 'prefix', label: this.t('platform_billing_page.rules_match_prefix'), icon: 'chevron-right' },
                { value: 'equals', label: this.t('platform_billing_page.rules_match_equals'), icon: 'target' },
                { value: 'regex', label: this.t('platform_billing_page.rules_match_regex'), icon: 'code' },
            ]
            : [
                { value: 'none', label: this.t('platform_billing_page.rules_match_none'), icon: 'close' },
                { value: 'equals', label: this.t('platform_billing_page.rules_match_equals'), icon: 'target' },
                { value: 'regex', label: this.t('platform_billing_page.rules_match_regex'), icon: 'code' },
            ];
        const disabled = mode === 'none';
        return html`
            <platform-field-shell
                .label=${this.t(labelKey)}
                .hint=${this._ruleHint(`match_${scope}`)}
                density="dense"
                floated
                editable
            >
                <div class="match-combo-control">
                    <div class="match-mode-picker" role="group" aria-label=${this.t(labelKey)}>
                        ${values.map((item) => html`
                            <button
                                type="button"
                                class="match-mode-btn"
                                title=${item.label}
                                aria-label=${item.label}
                                aria-pressed=${mode === item.value ? 'true' : 'false'}
                                @click=${() => this._setRuleMatchMode(idx, scope, item.value)}
                            >
                                <platform-icon name=${item.icon} size="14"></platform-icon>
                            </button>
                        `)}
                    </div>
                    <input
                        class="field-pill-input match-value-input"
                        type="text"
                        data-canon="input"
                        .value=${this._matchValue(rule.match, scope)}
                        placeholder=${disabled
                            ? this.t('platform_billing_page.rules_match_disabled_placeholder')
                            : this.t('platform_billing_page.rules_match_value_placeholder')}
                        ?disabled=${disabled}
                        @input=${(e: Event) => this._setMatchValueByMode(idx, scope, controlValue(e), mode)}
                    />
                </div>
            </platform-field-shell>
        `;
    }

    _renderAttributeMapEditor(idx: number, rule: BillingRule, mapName: string, titleKey: string, valueMode: string) {
        const entries = this._mapEntries(rule.match[mapName]);
        const isRegex = valueMode === 'regex';
        return html`
            <div class="rule-subsection">
                <div class="rule-subtitle">
                    <span>${this.t(titleKey)}</span>
                    <platform-help-hint
                        .text=${this._ruleHint(isRegex ? 'attr_regex_section' : 'attr_equals_section')}
                        .label=${this.t(titleKey)}
                        ?wide=${true}
                    ></platform-help-hint>
                </div>
                ${entries.length === 0 ? html`<div class="hint">${this.t('platform_billing_page.rules_no_attribute_rows')}</div>` : null}
                ${entries.map(([key, value], entryIdx) => html`
                    <div class="kv-editor-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            pill-density="dense"
                            .label=${this.t('platform_billing_page.rules_attr_key_label')}
                            .hint=${this._ruleHint('attr_key')}
                            .placeholder=${this.t('platform_billing_page.rules_attr_key_placeholder')}
                            .suggestions=${BILLING_RULE_ATTR_SUGGESTIONS}
                            .value=${key}
                            @change=${(e: CustomEvent) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('billing rule attribute: key expects detail.value string');
                                }
                                this._setMapEntry(idx, mapName, entryIdx, e.detail.value, value);
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            pill-density="dense"
                            .label=${this.t('platform_billing_page.rules_attr_value_label')}
                            .hint=${this._ruleHint(isRegex ? 'attr_regex_value' : 'attr_equals_value')}
                            .placeholder=${valueMode === 'regex'
                                ? this.t('platform_billing_page.rules_attr_regex_placeholder')
                                : this.t('platform_billing_page.rules_attr_value_placeholder')}
                            .value=${valueMode === 'regex' ? String(value) : this._jsonScalarInput(value)}
                            @change=${(e: CustomEvent) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('billing rule attribute: value expects detail.value string');
                                }
                                this._setMapEntry(
                                    idx,
                                    mapName,
                                    entryIdx,
                                    key,
                                    valueMode === 'regex' ? e.detail.value : this._parseScalarInput(e.detail.value),
                                );
                            }}
                        ></platform-field>
                        <button class="btn" @click=${() => this._removeMapEntry(idx, mapName, entryIdx)}>
                            <platform-icon name="trash" size="16"></platform-icon>
                            ${this.t('platform_billing_page.price_remove_row')}
                        </button>
                    </div>
                `)}
                <button class="btn" @click=${() => this._addMapEntry(idx, mapName)}>
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.t('platform_billing_page.rules_add_attribute_row')}
                </button>
            </div>
        `;
    }

    _renderPresentAttributes(idx: number, rule: BillingRule) {
        const items = Array.isArray(rule.match.attribute_keys_present) ? rule.match.attribute_keys_present : [];
        return html`
            <div class="rule-subsection">
                <div class="rule-subtitle">
                    <span>${this.t('platform_billing_page.rules_attr_present_title')}</span>
                    <platform-help-hint
                        .text=${this._ruleHint('attr_present_section')}
                        .label=${this.t('platform_billing_page.rules_attr_present_title')}
                        ?wide=${true}
                    ></platform-help-hint>
                </div>
                ${items.length === 0 ? html`<div class="hint">${this.t('platform_billing_page.rules_no_attribute_rows')}</div>` : null}
                ${items.map((value: unknown, entryIdx: number) => html`
                    <div class="present-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            pill-density="dense"
                            .label=${this.t('platform_billing_page.rules_attr_key_label')}
                            .hint=${this._ruleHint('attr_present_key')}
                            .placeholder=${this.t('platform_billing_page.rules_attr_key_placeholder')}
                            .suggestions=${BILLING_RULE_ATTR_SUGGESTIONS}
                            .value=${value}
                            @change=${(e: CustomEvent) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('billing rule present attribute: key expects detail.value string');
                                }
                                this._setPresentAttr(idx, entryIdx, e.detail.value);
                            }}
                        ></platform-field>
                        <button class="btn" @click=${() => this._removePresentAttr(idx, entryIdx)}>
                            <platform-icon name="trash" size="16"></platform-icon>
                            ${this.t('platform_billing_page.price_remove_row')}
                        </button>
                    </div>
                `)}
                <button class="btn" @click=${() => this._addPresentAttr(idx)}>
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.t('platform_billing_page.rules_add_attribute_row')}
                </button>
            </div>
        `;
    }

    _renderRuleCard(rule: BillingRule, idx: number) {
        const quantity = this._quantityParts(rule.quantity_from);
        const usageTypeValues = [
            'tool_call',
            'llm_request',
            'embedding_request',
            'rerank_request',
            'agent_execution',
            'flow_execution',
            'file_upload',
            'storage_usage',
        ];
        return html`
            <div class="rule-card" tabindex="-1" data-rule-id=${displayText(rule.rule_id)}>
                <div class="rule-card-head">
                    <div class="rule-title">
                        <span class="source">${idx + 1}</span>
                        <span class="mono">${rule.rule_id}</span>
                    </div>
                    <button class="btn" @click=${() => this._updateRulesDoc((doc: BillingRulesDoc) => { doc.rules.splice(idx, 1); })}>
                        <platform-icon name="trash" size="16"></platform-icon>
                        ${this.t('platform_billing_page.rules_remove_rule')}
                    </button>
                </div>
                <div class="rule-grid">
                    <platform-field
                        type="boolean"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_enabled')}
                        .hint=${this._ruleHint('enabled')}
                        .value=${rule.enabled !== false}
                        @change=${(e: CustomEvent) => this._setRuleField(idx, 'enabled', !!(e.detail && e.detail.value))}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_rule')}
                        .hint=${this._ruleHint('rule_id')}
                        .value=${displayText(rule.rule_id)}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rule: rule_id expects detail.value string');
                            }
                            this._setRuleField(idx, 'rule_id', e.detail.value);
                        }}
                    ></platform-field>
                    <platform-field
                        type="integer"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_priority')}
                        .hint=${this._ruleHint('priority')}
                        .value=${this._numberOrDefault(rule.priority, 100)}
                        @change=${(e: CustomEvent) => {
                            const value = e.detail && typeof e.detail.value === 'number' ? e.detail.value : 100;
                            this._setRuleField(idx, 'priority', value);
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_group')}
                        .hint=${this._ruleHint('exclusive_group')}
                        .value=${displayText(rule.exclusive_group)}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rule: exclusive_group expects detail.value string');
                            }
                            const trimmed = e.detail.value.trim();
                            this._setRuleField(idx, 'exclusive_group', trimmed.length > 0 ? e.detail.value : null);
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_resource')}
                        .hint=${this._ruleHint('resource_name')}
                        .value=${displayText(rule.resource_name)}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rule: resource_name expects detail.value string');
                            }
                            this._setRuleField(idx, 'resource_name', e.detail.value);
                        }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_col_usage_type')}
                        .hint=${this._ruleHint('usage_type')}
                        .value=${rule.usage_type || 'tool_call'}
                        .config=${this._enumConfig(usageTypeValues)}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rule: usage_type expects detail.value string');
                            }
                            if (e.detail.value.length === 0) {
                                return;
                            }
                            this._setRuleField(idx, 'usage_type', e.detail.value);
                        }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_quantity_mode')}
                        .hint=${this._ruleHint('quantity_mode')}
                        .value=${quantity.mode}
                        .config=${this._enumConfig([
                            { value: 'const', label: this.t('platform_billing_page.rules_quantity_const') },
                            { value: 'attr', label: this.t('platform_billing_page.rules_quantity_attr') },
                        ])}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rule: quantity mode expects detail.value string');
                            }
                            if (e.detail.value !== 'const' && e.detail.value !== 'attr') {
                                return;
                            }
                            this._setQuantityMode(idx, e.detail.value);
                        }}
                    ></platform-field>
                    <platform-field
                        type=${quantity.mode === 'const' ? 'number' : 'string'}
                        mode="edit"
                        pill-density="dense"
                        .label=${this.t('platform_billing_page.rules_quantity_value')}
                        .hint=${this._ruleHint(quantity.mode === 'attr' ? 'quantity_attr_value' : 'quantity_const_value')}
                        .value=${quantity.mode === 'const' ? this._numberOrNull(quantity.value) : quantity.value}
                        .suggestions=${quantity.mode === 'attr' ? BILLING_RULE_ATTR_SUGGESTIONS : []}
                        @change=${(e: CustomEvent) => {
                            const raw = e.detail ? e.detail.value : null;
                            this._setQuantityValue(idx, raw === null ? '' : String(raw));
                        }}
                    ></platform-field>
                </div>
                <div class="match-grid">
                    ${this._renderMatchSelector(idx, rule, 'operation', 'platform_billing_page.rules_match_operation')}
                    ${this._renderMatchSelector(idx, rule, 'service', 'platform_billing_page.rules_match_service')}
                    ${this._renderMatchSelector(idx, rule, 'event', 'platform_billing_page.rules_match_event')}
                </div>
                ${this._renderAttributeMapEditor(idx, rule, 'attribute_equals', 'platform_billing_page.rules_attr_equals_title', 'value')}
                ${this._renderAttributeMapEditor(idx, rule, 'attribute_regex', 'platform_billing_page.rules_attr_regex_title', 'regex')}
                ${this._renderPresentAttributes(idx, rule)}
            </div>
        `;
    }

    _renderRulesBuilder(doc: BillingRulesDoc) {
        const rules = doc && Array.isArray(doc.rules) ? doc.rules : [];
        return html`
            <div class="rule-grid">
                <platform-field
                    type="integer"
                    mode="edit"
                    pill-density="dense"
                    .label=${this.t('platform_billing_page.rules_doc_version')}
                    .hint=${this._ruleHint('doc_version')}
                    .value=${this._numberOrDefault(doc.version, 1)}
                    @change=${(e: CustomEvent) => {
                        const value = e.detail && typeof e.detail.value === 'number' ? e.detail.value : 1;
                        this._updateRulesDoc((draft: BillingRulesDoc) => { draft.version = value; });
                    }}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    pill-density="dense"
                    .label=${this.t('platform_billing_page.rules_application_mode')}
                    .hint=${this._ruleHint('application_mode')}
                    .value=${doc.application_mode || 'first_win'}
                    .config=${this._enumConfig(['first_win', 'all_matching'])}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('billing rules document: application_mode expects detail.value string');
                        }
                        if (e.detail.value !== 'first_win' && e.detail.value !== 'all_matching') {
                            return;
                        }
                        this._updateRulesDoc((draft: BillingRulesDoc) => { draft.application_mode = e.detail.value; });
                    }}
                ></platform-field>
            </div>
            <div class="actions">
                <button class="btn" @click=${() => this._addRuleAndScroll()}>
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${this.t('platform_billing_page.rules_add_rule')}
                </button>
            </div>
            ${rules.length === 0
                ? html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`
                : html`<div class="rule-list">${rules.map((rule, idx) => this._renderRuleCard(rule, idx))}</div>`}
        `;
    }

    async _saveRules() {
        const draft = typeof this._rulesDraft === 'string' ? this._rulesDraft : '';
        const text = draft.trim();
        if (!text) return;
        let document;
        try {
            document = JSON.parse(text);
        } catch (_err) {
            this._rulesDraftError = this.t('platform_billing_page.rules_parse_error');
            this.toast('platform_billing_page.rules_parse_error', { type: 'error' });
            return;
        }
        this._rulesDraftError = '';
        await this._rulesSave.run({ company_id: this._companyId, document });
    }

    async _loadRulesDefault() {
        if (!(await platformConfirm(this.t('platform_billing_page.confirm_replace_rules_default')))) return;
        const result = await this._rulesDefault.run(null);
        if (isPlainRecord(result) && result.document) {
            this._rulesDraft = JSON.stringify(result.document, null, 2);
            this._rulesDraftError = '';
        }
    }

    _renderRulesSection() {
        if (!this._companyId) {
            return html`
                <section>
                    <div class="section-title">${this.t('platform_billing_page.section_settlement_rules')}</div>
                    <platform-empty-state icon="table" title=${this.t('platform_billing_page.billing_company_required')}></platform-empty-state>
                </section>
            `;
        }
        if (this._rules.busy && !this._rulesDraft) {
            return html`<section><platform-empty-state loading></platform-empty-state></section>`;
        }
        const parsedDoc = this._rulesDocFromDraft();
        const doc = parsedDoc || this._emptyRulesDoc();
        return html`
            <section>
                <div class="section-head">
                    <div>
                        <div class="section-title">${this.t('platform_billing_page.section_settlement_rules')}</div>
                        <div class="section-subtitle">${this.t('platform_billing_page.hint_settlement_company_scope')}</div>
                    </div>
                    ${doc && Array.isArray(doc.rules)
                        ? html`<span class="source">${this.t('platform_billing_page.rules_count', { count: doc.rules.length })}</span>`
                        : null}
                </div>
                ${parsedDoc ? this._renderRulesBuilder(doc) : html`
                    <platform-empty-state icon="table" title=${this.t('platform_billing_page.rules_parse_error')}></platform-empty-state>
                `}
                ${this._rulesDraftError ? html`<div class="rules-error">${this._rulesDraftError}</div>` : null}
                <details class="json-details">
                    <summary>${this.t('platform_billing_page.rules_json_title')}</summary>
                    <platform-json-editor
                        .value=${typeof this._rulesDraft === 'string' ? this._rulesDraft : ''}
                        .readonly=${false}
                        .minHeight=${360}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('billing rules: json editor expects detail.value string');
                            }
                            this._rulesDraft = e.detail.value;
                            this._rulesDraftError = '';
                        }}
                    ></platform-json-editor>
                </details>
                <div class="actions">
                    <button class="btn primary" ?disabled=${this._rulesSave.busy} @click=${() => this._saveRules()}>
                        <platform-icon name="save" size="16"></platform-icon>
                        ${this.t('platform_billing_page.save_rules')}
                    </button>
                    <button class="btn" ?disabled=${this._rulesDefault.busy} @click=${() => this._loadRulesDefault()}>
                        <platform-icon name="import" size="16"></platform-icon>
                        ${this.t('platform_billing_page.rules_load_platform_default')}
                    </button>
                </div>
            </section>
        `;
    }

    _renderPricesRulesTab() {
        this._syncPriceDrafts();
        return html`
            <div class="stack">
                ${this._renderEffectivePricesSection()}
                ${this._renderPriceOverridesSection()}
                ${this._renderRulesSection()}
            </div>
        `;
    }

    _onUsageFilter(field: string, facet: string | null, value: string) {
        this._usageFilters = { ...this._usageFilters, [field]: value };
        if (facet && value && value.length >= 2) {
            this._usageFacetOpen = facet;
            this._facets.search(facet, value);
        } else {
            this._usageFacetOpen = null;
        }
    }

    _selectUsageFacet(field: string, item: Record<string, unknown>) {
        if (typeof item.value !== 'string') return;
        this._usageFilters = { ...this._usageFilters, [field]: item.value };
        this._usageFacetOpen = null;
    }

    _renderUsageFacetField(field: string, facet: string, labelKey: string) {
        const value = displayText(this._usageFilters[field]);
        const items = objectList(this._facets.items(facet), 'billing-admin: usage facets');
        const isOpen = this._usageFacetOpen === facet && value && value.length >= 2;
        return html`
            <div class="field">
                <label>${this.t(labelKey)}</label>
                <input class="row-input"
                    type="text"
                    data-canon="combobox"
                    .value=${value}
                    @input=${(e: Event) => this._onUsageFilter(field, facet, controlValue(e))}
                    @blur=${() => setTimeout(() => { this._usageFacetOpen = null; }, 180)} />
                ${isOpen ? html`
                    <div class="suggest">
                        ${items.length === 0
                            ? html`<div class="suggest-item">${this.t('platform_billing_page.empty')}</div>`
                            : items.map((it) => html`
                                <div class="suggest-item"
                                    @mousedown=${(e: Event) => { e.preventDefault(); this._selectUsageFacet(field, it); }}>
                                    ${typeof it.label === 'string' && it.label.length > 0 ? it.label : it.value}
                                </div>
                            `)}
                    </div>
                ` : null}
            </div>
        `;
    }

    _renderUsageTimeField(field: string, labelKey: string) {
        const value = displayText(this._usageFilters[field]);
        return html`
            <div class="field">
                <platform-field
                    type="datetime"
                    mode="edit"
                    label=${this.t(labelKey)}
                    .value=${value.length > 0 ? value : null}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('billing usage: time filter expects detail.value string');
                        }
                        this._onUsageFilter(field, null, e.detail.value);
                    }}
                ></platform-field>
            </div>
        `;
    }

    _usageSummary(items: Record<string, unknown>[]) {
        let quantity = 0;
        let cost = 0;
        const companies = new Set();
        for (const row of items) {
            if (typeof row.quantity === 'number') quantity += row.quantity;
            if (typeof row.cost === 'number') cost += row.cost;
            if (row.company_id) companies.add(row.company_id);
        }
        return { rows: items.length, quantity, cost, companies: companies.size };
    }

    _usagePayload(offset: number, limit: number) {
        const payload: Record<string, unknown> = { limit, offset };
        for (const key of ['company_id', 'usage_type', 'resource_name', 'from_time', 'to_time']) {
            const value = this._usageFilters[key];
            if (typeof value === 'string' && value !== '') payload[key] = value;
        }
        return payload;
    }

    _applySelectedCompanyToUsage() {
        if (!this._companyId) return;
        this._usageFilters = { ...this._usageFilters, company_id: this._companyId };
        this._usage.run(this._usagePayload(0, this._usage.state.limit as number));
    }

    _clearUsageFilters() {
        this._usageFilters = {};
        this._usage.run(this._usagePayload(0, this._usage.state.limit as number));
    }

    _renderUsageSummary(summary: Record<string, unknown>) {
        return html`
            <div class="summary-row">
                <div class="summary-item">
                    <span class="summary-value">${summary.rows}</span>
                    <span class="summary-label">${this.t('platform_billing_page.usage_summary_rows')}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-value">${this._formatNumber(summary.cost, 4)}</span>
                    <span class="summary-label">${this.t('platform_billing_page.usage_summary_cost')}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-value">${this._formatNumber(summary.quantity, 0)}</span>
                    <span class="summary-label">${this.t('platform_billing_page.usage_summary_quantity')}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-value">${summary.companies}</span>
                    <span class="summary-label">${this.t('platform_billing_page.usage_summary_companies')}</span>
                </div>
            </div>
        `;
    }

    _renderUsageTab() {
        const offset = this._usage.state.offset as number;
        const limit = this._usage.state.limit as number;
        const usageItems = this._usage.state.items;
        if (!Array.isArray(usageItems)) {
            throw new Error('billing-admin: usage items must be an array');
        }
        const items = usageItems;
        const summary = this._usageSummary(items);
        return html`
            <section>
                <div class="section-head">
                    <div>
                        <div class="section-title">${this.t('platform_billing_page.section_usage')}</div>
                        <div class="section-subtitle">${this.t('platform_billing_page.usage_facet_hint')}</div>
                    </div>
                </div>
                <div class="filters">
                    ${this._renderUsageFacetField('company_id', 'companies', 'platform_billing_page.filter_company')}
                    ${this._renderUsageFacetField('usage_type', 'usage_types', 'platform_billing_page.filter_usage_type')}
                    ${this._renderUsageFacetField('resource_name', 'resource_names', 'platform_billing_page.filter_resource')}
                    ${this._renderUsageTimeField('from_time', 'platform_billing_page.filter_from')}
                    ${this._renderUsageTimeField('to_time', 'platform_billing_page.filter_to')}
                </div>
                <div class="actions">
                    <button class="btn primary" ?disabled=${this._usage.busy}
                        @click=${() => this._usage.run(this._usagePayload(0, limit))}>
                        <platform-icon name="search" size="16"></platform-icon>
                        ${this.t('platform_billing_page.apply')}
                    </button>
                    ${this._companyId ? html`
                        <button class="btn" ?disabled=${this._usage.busy} @click=${() => this._applySelectedCompanyToUsage()}>
                            <platform-icon name="building" size="16"></platform-icon>
                            ${this.t('platform_billing_page.usage_filter_selected_company')}
                        </button>
                    ` : null}
                    <button class="btn" ?disabled=${this._usage.busy} @click=${() => this._clearUsageFilters()}>
                        <platform-icon name="close" size="16"></platform-icon>
                        ${this.t('platform_billing_page.usage_clear_filters')}
                    </button>
                </div>
            </section>

            <section>
                ${this._renderUsageSummary(summary)}
                ${this._usage.busy
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : (items.length === 0
                        ? html`<platform-empty-state icon="table" title=${this.t('platform_billing_page.empty')}></platform-empty-state>`
                        : html`
                            <div class="table-wrap">
                                <table>
                                    <thead><tr>
                                        <th>${this.t('platform_billing_page.col_time')}</th>
                                        <th>${this.t('platform_billing_page.col_company')}</th>
                                        <th>${this.t('platform_billing_page.col_type')}</th>
                                        <th>${this.t('platform_billing_page.col_resource')}</th>
                                        <th>${this.t('platform_billing_page.col_quantity')}</th>
                                        <th>${this.t('platform_billing_page.col_unit_cost')}</th>
                                        <th>${this.t('platform_billing_page.col_cost')}</th>
                                        <th>${this.t('platform_billing_page.col_span')}</th>
                                        <th>${this.t('platform_billing_page.col_rule')}</th>
                                    </tr></thead>
                                    <tbody>
                                        ${items.map((r: Record<string, unknown>) => html`
                                            <tr>
                                                <td>${this._formatDate(r.timestamp)}</td>
                                                <td>
                                                    <div>${firstText([r.company_name, r.company_id])}</div>
                                                    <div class="hint">${displayText(r.company_id)}</div>
                                                </td>
                                                <td>${displayText(r.usage_type)}</td>
                                                <td class="mono">${displayText(r.resource_name)}</td>
                                                <td>${this._formatNumber(r.quantity, 0)}</td>
                                                <td>${this._formatNumber(r.unit_cost, 8)}</td>
                                                <td>${this._formatNumber(r.cost, 4)}</td>
                                                <td class="mono">${typeof r.span_id === 'string' ? r.span_id.slice(0, 16) : ''}</td>
                                                <td class="mono">${displayText(r.rule_id)}</td>
                                            </tr>
                                        `)}
                                    </tbody>
                                </table>
                            </div>
                            <div class="actions">
                                <button class="btn" ?disabled=${offset === 0 || this._usage.busy}
                                    @click=${() => this._usage.run(this._usagePayload(Math.max(0, offset - limit), limit))}>
                                    <platform-icon name="chevron-left" size="16"></platform-icon>
                                    ${this.t('platform_billing_page.usage_prev')}
                                </button>
                                <span class="hint">
                                    ${this.t('platform_billing_page.usage_page_info', { from: offset + 1, to: offset + items.length })}
                                </span>
                                <button class="btn" ?disabled=${items.length < limit || this._usage.busy}
                                    @click=${() => this._usage.run(this._usagePayload(offset + limit, limit))}>
                                    ${this.t('platform_billing_page.usage_next')}
                                    <platform-icon name="chevron-right" size="16"></platform-icon>
                                </button>
                            </div>
                        `)}
            </section>
        `;
    }

    _formatDate(value: unknown) {
        if (!value) return '';
        const d = new Date(value as string | number);
        if (Number.isNaN(d.getTime())) return String(value);
        return d.toLocaleString();
    }

    _formatNumber(value: unknown, maximumFractionDigits: number) {
        if (typeof value !== 'number' || Number.isNaN(value)) return '';
        return new Intl.NumberFormat(undefined, {
            maximumFractionDigits,
        }).format(value);
    }

    override render(): TemplateResult {
        let content;
        if (this._tab === 'companies') content = this._renderCompaniesTab();
        else if (this._tab === 'prices_rules') content = this._renderPricesRulesTab();
        else if (this._tab === 'usage') content = this._renderUsageTab();

        return html`
            <page-header
                title=${this.t('platform_billing_page.title')}
                subtitle=${this.t('platform_billing_page.subtitle')}
            ></page-header>
            <div class="page-body">
                ${this._renderTabs()}
                ${this._tab !== 'companies' ? this._renderCompanyScope() : null}
                ${content}
            </div>
        `;
    }
}

customElements.define('frontend-billing-admin-page', FrontendBillingAdminPage);
