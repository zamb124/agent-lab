/**
 * Админка биллинга: прайс-лист, правила settlement, отчёт usage (только system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { BaseService } from '@platform/lib/services/BaseService.js';
import { FlowsCatalogService } from '../../services/flows-catalog.service.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';

const api = new BaseService('/frontend');
const flowsCatalog = new FlowsCatalogService();

const USAGE_FACET_DEBOUNCE_MS = 300;

function _usageFacetItemIsObject(item) {
    return item !== null && typeof item === 'object' && typeof item.value === 'string';
}

function _shortCompanyIdHint(id) {
    if (!id) {
        return '';
    }
    return id.length > 8 ? `${id.slice(0, 8)}...` : id;
}

const USAGE_TYPES = [
    'tool_call', 'llm_request', 'embedding_request',
    'agent_execution', 'flow_execution', 'file_upload', 'storage_usage',
];

const SETTLEMENT_RESOURCE_NAMES_BASE = [
    'llm:*', 'tool:external_api', 'tool:mcp_*',
    'tool:channel_telegram', 'tool:channel_webhook',
    'embedding:*',
    'livekit:room_create', 'livekit:egress_composite', 'livekit:egress_segmented',
];

const QUANTITY_SOURCES = [
    'const:1',
    'attr:platform.billing.quantity',
    'attr:platform.llm.total_tokens',
];

const OPERATION_PREFIXES = [
    'flows.llm', 'flows.llm_resource', 'flows.external_api',
    'flows.mcp', 'flows.channel', 'flows.tools',
    'livekit.room', 'livekit.egress',
];

const OPERATION_NAMES = [
    'flows.llm.invoke_task',
    'flows.llm_resource.complete', 'flows.llm_resource.chat', 'flows.llm_resource.chat_with_tools',
    'flows.tools.ocr_vision',
    'flows.external_api.call',
    'flows.mcp.call_tool',
    'flows.channel.execute_action',
    'livekit.room.create', 'livekit.egress.composite', 'livekit.egress.segmented',
];

const SERVICE_NAMES = ['flows', 'sync', 'rag', 'crm', 'frontend', 'scheduler'];

const EVENT_TYPES = [
    'llm.call', 'llm.invoke', 'llm.complete', 'llm.chat', 'llm.chat_with_tools', 'llm.vision',
    'external_api.call', 'mcp.call_tool', 'channel.action',
    'livekit.room', 'livekit.egress',
];

const KNOWN_ATTR_KEYS = [
    'platform.billing.usage_type', 'platform.billing.resource_name',
    'platform.llm.model',
    'platform.livekit.operation',
    'platform.external_api.url', 'platform.external_api.method',
    'platform.mcp.server_id', 'platform.mcp.tool_name',
    'platform.channel.type', 'platform.channel.action',
];


function _emptyRule() {
    return {
        rule_id: '',
        enabled: true,
        priority: 100,
        exclusive_group: '',
        resource_name: '',
        usage_type: 'tool_call',
        quantity_from: 'const:1',
        match: {
            operation_name_prefix: '',
            operation_name_equals: '',
            service_name_equals: '',
            event_type_equals: '',
            attribute_equals: {},
        },
    };
}

function _overrideToRows(obj) {
    const rows = [];
    if (!obj || typeof obj !== 'object') return rows;
    for (const [cat, resources] of Object.entries(obj)) {
        if (typeof resources !== 'object') continue;
        for (const [res, price] of Object.entries(resources)) {
            rows.push({ category: cat, resource: res, price: Number(price) || 0 });
        }
    }
    return rows;
}

function _rowsToOverride(rows) {
    const out = {};
    for (const { category, resource, price } of rows) {
        const cat = (category || '').trim();
        const res = (resource || '').trim();
        if (!cat || !res) continue;
        if (!out[cat]) out[cat] = {};
        out[cat][res] = Number(price) || 0;
    }
    return out;
}

function _cleanRule(r) {
    const m = r.match || {};
    const cleaned = {
        rule_id: r.rule_id,
        enabled: r.enabled,
        priority: Number(r.priority) || 100,
        resource_name: r.resource_name,
        usage_type: r.usage_type,
        quantity_from: r.quantity_from || 'const:1',
        match: {},
    };
    if (r.exclusive_group) cleaned.exclusive_group = r.exclusive_group;
    if (m.operation_name_prefix) cleaned.match.operation_name_prefix = m.operation_name_prefix;
    if (m.operation_name_equals) cleaned.match.operation_name_equals = m.operation_name_equals;
    if (m.service_name_equals) cleaned.match.service_name_equals = m.service_name_equals;
    if (m.event_type_equals) cleaned.match.event_type_equals = m.event_type_equals;
    const attrs = m.attribute_equals;
    if (attrs && typeof attrs === 'object' && Object.keys(attrs).length > 0) {
        cleaned.match.attribute_equals = { ...attrs };
    }
    return cleaned;
}


export class BillingAdminPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            :host { display: block; }

            .section {
                margin-bottom: var(--space-8);
            }
            .section-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-2);
            }
            .err {
                color: var(--error);
                font-size: var(--text-sm);
                margin-bottom: var(--space-2);
            }

            .toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                margin-top: var(--space-3);
            }

            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                padding: 0;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .icon-btn:hover {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
                border-color: var(--border-strong);
            }
            .icon-btn.primary {
                background: var(--accent);
                border-color: var(--accent);
                color: white;
            }
            .icon-btn.primary:hover {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
            }
            .icon-btn.danger {
                color: var(--error);
                background: transparent;
                border-color: transparent;
            }
            .icon-btn.danger:hover {
                background: rgba(244, 63, 94, 0.12);
            }
            .icon-btn.sm {
                width: 28px;
                height: 28px;
            }
            .icon-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }

            :host-context([data-theme="light"]) .icon-btn {
                background: var(--glass-tint-medium);
                border-color: var(--border-default);
                color: var(--text-secondary);
            }
            :host-context([data-theme="light"]) .icon-btn:hover {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
            :host-context([data-theme="light"]) .icon-btn.primary {
                background: var(--accent);
                border-color: var(--accent);
                color: white;
            }

            /* Price table */
            .price-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: var(--space-3);
            }
            .price-table th,
            .price-table td {
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: visible;
                vertical-align: middle;
            }
            .price-table th {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
            }
            .price-table td:last-child {
                width: 40px;
                text-align: center;
            }
            .price-table input,
            .price-table select {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            /* Rules */
            .rule-card {
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-3);
                background: var(--glass-solid-subtle);
            }
            .rule-header {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                cursor: pointer;
                user-select: none;
            }
            .rule-header .rule-summary {
                flex: 1;
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                min-width: 0;
            }
            .rule-header .rule-id-label {
                font-weight: var(--font-semibold);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .rule-header .rule-resource-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .rule-header .chevron {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                transition: transform var(--duration-fast);
            }
            .rule-header .chevron.open {
                transform: rotate(90deg);
            }
            .rule-body {
                padding: 0 var(--space-3) var(--space-3);
                display: grid;
                gap: var(--space-3);
            }
            .rule-body .form-row {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
                gap: var(--space-3);
            }

            .match-section {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                padding: var(--space-3);
            }
            .match-section .match-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2);
            }

            .kv-row {
                display: flex;
                gap: var(--space-2);
                align-items: center;
                margin-bottom: var(--space-2);
            }
            .kv-row input,
            .kv-row select {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                min-height: 42px;
                box-sizing: border-box;
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            /* Usage table */
            .table-wrap {
                background: var(--glass-solid-medium);
                border-radius: var(--radius-lg);
                overflow-x: auto;
            }
            table.usage-table {
                width: 100%;
                border-collapse: collapse;
            }
            .usage-table th,
            .usage-table td {
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-xs);
                color: var(--text-primary);
                vertical-align: top;
            }
            .usage-table th {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-top: none;
            }
            .usage-table tfoot td {
                font-weight: var(--font-semibold);
                border-top: 2px solid var(--border-default);
            }

            .usage-table .muted {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .usage-filters-bar {
                margin-bottom: var(--space-3);
                width: 100%;
                overflow-x: auto;
                overflow-y: visible;
                padding-bottom: var(--space-1);
            }

            .usage-filters-row {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: flex-end;
                gap: var(--space-2);
                min-width: min-content;
            }

            .usage-filters-row > label.field {
                flex: 1 1 0;
                min-width: 6.5rem;
                max-width: 11rem;
                margin-bottom: 0;
            }

            .usage-filters-row > label.field.usage-filter-datetime {
                flex: 1 1 8rem;
                min-width: 8rem;
                max-width: 10rem;
            }

            .usage-filters-row > label.field.usage-filter-limit {
                flex: 0 0 4.5rem;
                min-width: 4rem;
                max-width: 4.75rem;
            }

            .usage-filters-submit {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                flex: 0 0 auto;
            }

            .billing-suggest-wrap {
                position: relative;
                width: 100%;
            }

            .billing-suggest-panel {
                position: absolute;
                left: 0;
                right: 0;
                top: calc(100% + 2px);
                z-index: 50;
                max-height: 220px;
                overflow: auto;
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-strong);
                box-shadow: var(--shadow-md);
            }

            .billing-suggest-item {
                display: block;
                width: 100%;
                text-align: left;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                word-break: break-word;
            }

            .billing-suggest-item:last-child {
                border-bottom: none;
            }

            .billing-suggest-item:hover,
            .billing-suggest-item:focus-visible {
                background: var(--glass-tint-medium);
                outline: none;
            }

            .usage-filters-row .billing-suggest-wrap input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                min-height: 42px;
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .usage-filters-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.35;
                max-width: min(22rem, 40vw);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            label.field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .field-label-row {
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-1);
                flex-wrap: nowrap;
            }
            .field-label-row platform-help-hint {
                flex-shrink: 0;
            }
            label.field input,
            label.field select {
                padding: var(--space-2) var(--space-3);
                min-height: 42px;
                box-sizing: border-box;
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            label.field platform-date-picker {
                min-width: 0;
            }

            .pagination {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
        `,
    ];

    static properties = {
        _effectivePrices: { type: Object, state: true },
        _overrideRows: { type: Array, state: true },
        _pricesError: { type: String, state: true },
        _pricesLoading: { type: Boolean, state: true },

        _rulesDoc: { type: Object, state: true },
        _rulesExpandedIdx: { type: Number, state: true },
        _rulesError: { type: String, state: true },
        _rulesLoading: { type: Boolean, state: true },

        _cPriceCompanyId: { type: String, state: true },
        _cPriceOverrideRows: { type: Array, state: true },
        _cPriceError: { type: String, state: true },
        _cPriceLoading: { type: Boolean, state: true },

        _usageRows: { type: Array, state: true },
        _usageError: { type: String, state: true },
        _usageLoading: { type: Boolean, state: true },
        _uCompany: { type: String, state: true },
        _uUsageType: { type: String, state: true },
        _uResource: { type: String, state: true },
        _uFrom: { type: String, state: true },
        _uTo: { type: String, state: true },
        _uLimit: { type: Number, state: true },
        _uOffset: { type: Number, state: true },

        _registryToolIds: { type: Array, state: true },
        _registryToolsError: { type: String, state: true },

        _usageFacetOpen: { type: String, state: true },
        _usageFacetItems: { type: Object, state: true },
    };

    constructor() {
        super();
        this._effectivePrices = {};
        this._overrideRows = [];
        this._pricesError = '';
        this._pricesLoading = false;

        this._rulesDoc = { version: 1, application_mode: 'all_matching', rules: [] };
        this._rulesExpandedIdx = -1;
        this._rulesError = '';
        this._rulesLoading = false;

        this._cPriceCompanyId = '';
        this._cPriceOverrideRows = [];
        this._cPriceError = '';
        this._cPriceLoading = false;

        this._usageRows = [];
        this._usageError = '';
        this._usageLoading = false;
        this._uCompany = '';
        this._uUsageType = '';
        this._uResource = '';
        this._uFrom = '';
        this._uTo = '';
        this._uLimit = 200;
        this._uOffset = 0;

        this._registryToolIds = [];
        this._registryToolsError = '';

        this._pickCompany = '';
        this._pickUsageType = '';
        this._pickResource = '';
        this._usageFacetOpen = '';
        this._usageFacetItems = { company: [], usage_type: [], resource_name: [] };
        this._usageFacetDebounce = {};
        this._usageOnDocClick = (e) => {
            if (!this._usageFacetOpen) {
                return;
            }
            const path = e.composedPath();
            const hit = path.some(
                (n) => n instanceof HTMLElement && n.classList?.contains('billing-suggest-wrap'),
            );
            if (!hit) {
                this._usageFacetOpen = '';
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._usageOnDocClick);
        void this._loadPrices();
        void this._loadSettlementRules();
        void this._loadRegistryTools();
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._usageOnDocClick);
        Object.values(this._usageFacetDebounce).forEach((id) => clearTimeout(id));
        super.disconnectedCallback();
    }

    _t(key, params = {}) {
        return this.i18n.t(`platform_billing_page.${key}`, params);
    }

    get _priceCategories() {
        return Object.keys(this._effectivePrices);
    }

    _priceResources(category) {
        const bucket = this._effectivePrices[category];
        if (!bucket || typeof bucket !== 'object') return [];
        return Object.keys(bucket);
    }

    _mergedPriceResources(category) {
        const fromCatalog = this._priceResources(category);
        if (category !== 'tool') {
            return fromCatalog;
        }
        return [...new Set([...fromCatalog, ...this._registryToolIds])].sort();
    }

    get _settlementResourceNameOptions() {
        const fromRegistry = this._registryToolIds.map((id) => `tool:${id}`);
        return [...new Set([...SETTLEMENT_RESOURCE_NAMES_BASE, ...fromRegistry])].sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: 'base' }),
        );
    }

    async _loadRegistryTools() {
        this._registryToolsError = '';
        try {
            const items = await flowsCatalog.listTools();
            const ids = items
                .filter((row) => row && (row.item_type === undefined || row.item_type === 'tool'))
                .map((row) => row.tool_id)
                .filter((id) => typeof id === 'string' && id.length > 0);
            this._registryToolIds = [...new Set(ids)].sort((a, b) =>
                a.localeCompare(b, undefined, { sensitivity: 'base' }),
            );
        } catch (e) {
            this._registryToolIds = [];
            this._registryToolsError = e.message;
        }
    }

    // ── Prices ──

    async _loadPrices() {
        this._pricesLoading = true;
        this._pricesError = '';
        try {
            const data = await api.get('/api/platform-billing/prices');
            this._effectivePrices = data.effective ?? {};
            const ovr = data.storage_override ?? {};
            this._overrideRows = _overrideToRows(ovr);
        } catch (e) {
            this._pricesError = e.message;
        } finally {
            this._pricesLoading = false;
        }
    }

    async _saveOverride() {
        this._pricesError = '';
        const catalog = _rowsToOverride(this._overrideRows);
        try {
            await api.put('/api/platform-billing/prices', catalog);
            await this._loadPrices();
            this.success(this._t('saved_ok'));
        } catch (e) {
            this._pricesError = e.message;
        }
    }

    _addOverrideRow() {
        this._overrideRows = [...this._overrideRows, { category: '', resource: '', price: 0 }];
    }

    _removeOverrideRow(idx) {
        this._overrideRows = this._overrideRows.filter((_, i) => i !== idx);
    }

    _updateOverrideRow(idx, field, value) {
        const rows = [...this._overrideRows];
        rows[idx] = { ...rows[idx], [field]: field === 'price' ? Number(value) || 0 : value };
        this._overrideRows = rows;
    }

    // ── Settlement Rules ──

    async _loadSettlementRules() {
        this._rulesLoading = true;
        this._rulesError = '';
        try {
            const data = await api.get('/api/platform-billing/settlement-rules');
            const doc = data.document ?? { version: 1, application_mode: 'all_matching', rules: [] };
            this._rulesDoc = doc;
        } catch (e) {
            this._rulesError = e.message;
        } finally {
            this._rulesLoading = false;
        }
    }

    async _saveSettlementRules() {
        this._rulesError = '';
        const payload = {
            version: this._rulesDoc.version || 1,
            application_mode: this._rulesDoc.application_mode || 'all_matching',
            rules: (this._rulesDoc.rules || []).map(_cleanRule),
        };
        try {
            await api.put('/api/platform-billing/settlement-rules', payload);
            await this._loadSettlementRules();
            this.success(this._t('saved_ok'));
        } catch (e) {
            this._rulesError = e.message;
        }
    }

    _addRule() {
        const rules = [...(this._rulesDoc.rules || []), _emptyRule()];
        this._rulesDoc = { ...this._rulesDoc, rules };
        this._rulesExpandedIdx = rules.length - 1;
    }

    _removeRule(idx) {
        const rules = (this._rulesDoc.rules || []).filter((_, i) => i !== idx);
        this._rulesDoc = { ...this._rulesDoc, rules };
        if (this._rulesExpandedIdx === idx) this._rulesExpandedIdx = -1;
        else if (this._rulesExpandedIdx > idx) this._rulesExpandedIdx--;
    }

    _updateRule(idx, field, value) {
        const rules = [...(this._rulesDoc.rules || [])];
        rules[idx] = { ...rules[idx], [field]: value };
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    _updateRuleMatch(idx, field, value) {
        const rules = [...(this._rulesDoc.rules || [])];
        const match = { ...(rules[idx].match || {}), [field]: value };
        rules[idx] = { ...rules[idx], match };
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    _addRuleAttr(idx) {
        const rules = [...(this._rulesDoc.rules || [])];
        const match = { ...(rules[idx].match || {}) };
        const attrs = { ...(match.attribute_equals || {}), '': '' };
        match.attribute_equals = attrs;
        rules[idx] = { ...rules[idx], match };
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    _removeRuleAttr(ruleIdx, attrKey) {
        const rules = [...(this._rulesDoc.rules || [])];
        const match = { ...(rules[ruleIdx].match || {}) };
        const attrs = { ...(match.attribute_equals || {}) };
        delete attrs[attrKey];
        match.attribute_equals = attrs;
        rules[ruleIdx] = { ...rules[ruleIdx], match };
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    _updateRuleAttr(ruleIdx, oldKey, newKey, newValue) {
        const rules = [...(this._rulesDoc.rules || [])];
        const match = { ...(rules[ruleIdx].match || {}) };
        const attrs = { ...(match.attribute_equals || {}) };
        if (oldKey !== newKey) delete attrs[oldKey];
        attrs[newKey] = newValue;
        match.attribute_equals = attrs;
        rules[ruleIdx] = { ...rules[ruleIdx], match };
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    // ── Company Prices ──

    async _loadCompanyPrices() {
        const cid = this._cPriceCompanyId.trim();
        if (!cid) {
            this._cPriceError = this._t('company_id_required');
            return;
        }
        this._cPriceLoading = true;
        this._cPriceError = '';
        try {
            const data = await api.get(`/api/platform-billing/prices/company/${encodeURIComponent(cid)}`);
            const ovr = data.storage_override ?? {};
            this._cPriceOverrideRows = _overrideToRows(ovr);
        } catch (e) {
            this._cPriceError = e.message;
        } finally {
            this._cPriceLoading = false;
        }
    }

    async _saveCompanyPrices() {
        const cid = this._cPriceCompanyId.trim();
        if (!cid) {
            this._cPriceError = this._t('company_id_required');
            return;
        }
        this._cPriceError = '';
        const catalog = _rowsToOverride(this._cPriceOverrideRows);
        try {
            await api.put(`/api/platform-billing/prices/company/${encodeURIComponent(cid)}`, catalog);
            await this._loadCompanyPrices();
            this.success(this._t('saved_ok'));
        } catch (e) {
            this._cPriceError = e.message;
        }
    }

    // ── Usage ──

    async _loadUsage() {
        this._usageLoading = true;
        this._usageError = '';
        const params = {};
        if (this._uCompany.trim()) params.company_id = this._uCompany.trim();
        if (this._uUsageType.trim()) params.usage_type = this._uUsageType.trim();
        if (this._uResource.trim()) params.resource_name = this._uResource.trim();
        if (this._uFrom) params.from = this._uFrom;
        if (this._uTo) params.to = this._uTo;
        if (this._uLimit > 0) params.limit = this._uLimit;
        if (this._uOffset > 0) params.offset = this._uOffset;
        try {
            const data = await api.get('/api/platform-billing/usage-report', params);
            this._usageRows = Array.isArray(data.items) ? data.items : [];
        } catch (e) {
            this._usageError = e.message;
        } finally {
            this._usageLoading = false;
        }
    }

    _usagePrevPage() {
        this._uOffset = Math.max(0, this._uOffset - this._uLimit);
        void this._loadUsage();
    }

    _usageNextPage() {
        this._uOffset += this._uLimit;
        void this._loadUsage();
    }

    _usageFacetStorageKey(kind) {
        if (kind === 'company') return 'company';
        if (kind === 'usage_type') return 'usage_type';
        return 'resource_name';
    }

    _scheduleUsageFacet(kind, q) {
        if (this._usageFacetDebounce[kind]) {
            clearTimeout(this._usageFacetDebounce[kind]);
        }
        this._usageFacetDebounce[kind] = window.setTimeout(() => {
            void this._loadUsageFacet(kind, q);
        }, USAGE_FACET_DEBOUNCE_MS);
    }

    async _loadUsageFacet(kind, q) {
        const trimmed = (q || '').trim();
        const storageKey = this._usageFacetStorageKey(kind);
        try {
            if (kind === 'company') {
                const params = {};
                if (trimmed.length >= 2) {
                    params.q = trimmed;
                }
                const data = await api.get('/api/platform-tracing/facets/companies', params);
                const items = Array.isArray(data.items) ? data.items : [];
                this._usageFacetItems = { ...this._usageFacetItems, company: items };
                return;
            }
            if (kind === 'usage_type') {
                const params = {};
                if (trimmed.length >= 2) {
                    params.q = trimmed;
                }
                const data = await api.get('/api/platform-billing/facets/usage-types', params);
                const items = Array.isArray(data.items) ? data.items : [];
                this._usageFacetItems = { ...this._usageFacetItems, usage_type: items };
                return;
            }
            if (kind === 'resource_name') {
                const params = {};
                if (trimmed.length >= 2) {
                    params.q = trimmed;
                }
                const data = await api.get('/api/platform-billing/facets/resource-names', params);
                const items = Array.isArray(data.items) ? data.items : [];
                this._usageFacetItems = { ...this._usageFacetItems, resource_name: items };
            }
        } catch {
            this._usageFacetItems = { ...this._usageFacetItems, [storageKey]: [] };
        }
    }

    _onUsageSuggestFocus(kind) {
        this._usageFacetOpen = kind;
        const q = kind === 'company'
            ? this._uCompany
            : kind === 'usage_type'
              ? this._uUsageType
              : this._uResource;
        void this._loadUsageFacet(kind, q);
    }

    _onUsageSuggestInput(kind, e) {
        const raw = e.target?.value ?? '';
        if (kind === 'company') {
            this._uCompany = raw;
            if (raw.trim() !== this._pickCompany.trim()) {
                this._pickCompany = '';
            }
        } else if (kind === 'usage_type') {
            this._uUsageType = raw;
            if (raw.trim() !== this._pickUsageType.trim()) {
                this._pickUsageType = '';
            }
        } else if (kind === 'resource_name') {
            this._uResource = raw;
            if (raw.trim() !== this._pickResource.trim()) {
                this._pickResource = '';
            }
        }
        this._usageFacetOpen = kind;
        this._scheduleUsageFacet(kind, raw);
    }

    _pickUsageSuggest(kind, raw) {
        const v = _usageFacetItemIsObject(raw) ? raw.value : (raw ?? '');
        if (kind === 'company') {
            this._uCompany = v;
            this._pickCompany = v;
        } else if (kind === 'usage_type') {
            this._uUsageType = v;
            this._pickUsageType = v;
        } else if (kind === 'resource_name') {
            this._uResource = v;
            this._pickResource = v;
        }
        this._usageFacetOpen = '';
    }

    _renderUsageSuggest(kind, labelContent) {
        const open = this._usageFacetOpen === kind;
        const storageKey = this._usageFacetStorageKey(kind);
        const items = Array.isArray(this._usageFacetItems[storageKey])
            ? this._usageFacetItems[storageKey]
            : [];
        const value = kind === 'company'
            ? this._uCompany
            : kind === 'usage_type'
              ? this._uUsageType
              : this._uResource;
        return html`
            <label class="field">
                <span class="field-label-row">${labelContent}</span>
                <div class="billing-suggest-wrap" @click=${(e) => e.stopPropagation()}>
                    <input
                        type="text"
                        .value=${value}
                        @focus=${() => this._onUsageSuggestFocus(kind)}
                        @input=${(e) => this._onUsageSuggestInput(kind, e)}
                    />
                    ${open && items.length > 0
                        ? html`
                            <div class="billing-suggest-panel" role="listbox">
                                ${items.map(
                                    (item) => html`
                                        <button
                                            type="button"
                                            class="billing-suggest-item"
                                            role="option"
                                            @mousedown=${(e) => e.preventDefault()}
                                            @click=${() => this._pickUsageSuggest(kind, item)}
                                        >
                                            ${_usageFacetItemIsObject(item) ? item.label : item}
                                        </button>
                                    `,
                                )}
                            </div>
                        `
                        : ''}
                </div>
            </label>
        `;
    }

    // ── Render helpers ──

    _selectWithEmpty(options, value, onChange) {
        const hasCustom = value && !options.includes(value);
        return html`
            <select .value=${value || ''} @change=${(e) => onChange(e.target.value)}>
                <option value="">—</option>
                ${hasCustom ? html`<option value=${value} selected>${value}</option>` : ''}
                ${options.map(o => html`<option value=${o} ?selected=${o === value}>${o}</option>`)}
            </select>
        `;
    }

    _hint(key) {
        return html`<platform-help-hint text=${this._t(key)}></platform-help-hint>`;
    }

    _iconBtn(icon, opts = {}) {
        const cls = ['icon-btn', opts.variant || '', opts.size || ''].filter(Boolean).join(' ');
        return html`
            <button class=${cls}
                title=${opts.title || ''}
                ?disabled=${opts.disabled || false}
                @click=${opts.onClick}>
                <platform-icon name=${icon} size=${opts.iconSize || '16'}></platform-icon>
            </button>
        `;
    }

    // ── Render ──

    render() {
        return html`
            <page-header
                title=${this._t('title')}
                subtitle=${this._t('subtitle')}
            ></page-header>

            ${this._registryToolsError
                ? html`<div class="err">${this._t('registry_tools_error', { message: this._registryToolsError })}</div>`
                : ''}

            ${this._renderPricesSection()}
            ${this._renderSettlementRulesSection()}
            ${this._renderCompanyPricesSection()}
            ${this._renderUsageSection()}
        `;
    }

    // ── Price catalog ──

    _renderPriceTable(rows, onUpdate, onRemove, onAdd) {
        return html`
            <table class="price-table">
                <thead>
                    <tr>
                        <th>${this._t('price_col_category')} ${this._hint('hint_price_category')}</th>
                        <th>${this._t('price_col_resource')} ${this._hint('hint_price_resource')}</th>
                        <th>${this._t('price_col_price')} ${this._hint('hint_price_price')}</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${rows.map((row, i) => html`
                        <tr>
                            <td>
                                ${this._selectWithEmpty(this._priceCategories, row.category,
                                    (v) => onUpdate(i, 'category', v))}
                            </td>
                            <td>
                                ${this._selectWithEmpty(
                                    this._mergedPriceResources(row.category),
                                    row.resource,
                                    (v) => onUpdate(i, 'resource', v),
                                )}
                            </td>
                            <td>
                                <input type="number" step="any" .value=${String(row.price)}
                                    @input=${(e) => onUpdate(i, 'price', e.target.value)} />
                            </td>
                            <td>
                                ${this._iconBtn('trash', {
                                    variant: 'danger', size: 'sm',
                                    title: this._t('price_remove_row'),
                                    onClick: () => onRemove(i),
                                })}
                            </td>
                        </tr>
                    `)}
                </tbody>
            </table>
            ${this._iconBtn('plus', {
                title: this._t('price_add_row'),
                onClick: onAdd,
            })}
        `;
    }

    _renderPricesSection() {
        return html`
            <div class="section">
                <h2 class="section-title">${this._t('section_prices')} ${this._hint('hint_prices_section')}</h2>
                ${this._pricesError ? html`<div class="err">${this._pricesError}</div>` : ''}
                ${this._pricesLoading
                    ? html`<div>${this._t('loading')}</div>`
                    : html`
                        ${this._renderPriceTable(
                            this._overrideRows,
                            (i, f, v) => this._updateOverrideRow(i, f, v),
                            (i) => this._removeOverrideRow(i),
                            () => this._addOverrideRow(),
                        )}

                        <div class="toolbar">
                            ${this._iconBtn('refresh', {
                                title: this._t('reload'),
                                onClick: () => this._loadPrices(),
                            })}
                            ${this._iconBtn('save', {
                                variant: 'primary',
                                title: this._t('save_override'),
                                onClick: () => this._saveOverride(),
                            })}
                        </div>
                    `}
            </div>
        `;
    }

    // ── Settlement rules ──

    _renderSettlementRulesSection() {
        return html`
            <div class="section">
                <h2 class="section-title">${this._t('section_settlement_rules')} ${this._hint('hint_settlement_section')}</h2>
                ${this._rulesError ? html`<div class="err">${this._rulesError}</div>` : ''}
                ${this._rulesLoading
                    ? html`<div>${this._t('loading')}</div>`
                    : html`
                        ${this._renderRulesForm()}

                        <div class="toolbar">
                            ${this._iconBtn('refresh', {
                                title: this._t('reload'),
                                onClick: () => this._loadSettlementRules(),
                            })}
                            ${this._iconBtn('save', {
                                variant: 'primary',
                                title: this._t('save_rules'),
                                onClick: () => this._saveSettlementRules(),
                            })}
                        </div>
                    `}
            </div>
        `;
    }

    _renderRulesForm() {
        const doc = this._rulesDoc;
        const rules = doc.rules || [];
        return html`
            <div style="display: flex; gap: var(--space-4); align-items: center; margin-bottom: var(--space-4);">
                <label class="field">
                    <span class="field-label-row">${this._t('rules_application_mode')} ${this._hint('hint_application_mode')}</span>
                    <select .value=${doc.application_mode || 'all_matching'}
                        @change=${(e) => { this._rulesDoc = { ...doc, application_mode: e.target.value }; }}>
                        <option value="all_matching">all_matching</option>
                        <option value="first_win">first_win</option>
                    </select>
                </label>
            </div>

            ${rules.map((rule, idx) => this._renderRuleCard(rule, idx))}

            ${this._iconBtn('plus', {
                title: this._t('rules_add_rule'),
                onClick: () => this._addRule(),
            })}
        `;
    }

    _renderRuleCard(rule, idx) {
        const expanded = this._rulesExpandedIdx === idx;
        return html`
            <div class="rule-card">
                <div class="rule-header" @click=${() => { this._rulesExpandedIdx = expanded ? -1 : idx; }}>
                    <span class="chevron ${expanded ? 'open' : ''}">&#9654;</span>
                    <div class="rule-summary">
                        <span class="rule-id-label">${rule.rule_id || this._t('rules_new')}</span>
                        <span class="rule-resource-label">${rule.resource_name || ''}</span>
                    </div>
                    <platform-switch
                        ?checked=${rule.enabled !== false}
                        size="sm"
                        @change=${(e) => { e.stopPropagation(); this._updateRule(idx, 'enabled', e.detail.value); }}
                    ></platform-switch>
                    <span @click=${(e) => { e.stopPropagation(); this._removeRule(idx); }}>
                        ${this._iconBtn('trash', { variant: 'danger', size: 'sm' })}
                    </span>
                </div>

                ${expanded ? html`
                    <div class="rule-body">
                        <div class="form-row">
                            <label class="field">
                                <span class="field-label-row">rule_id ${this._hint('hint_rule_id')}</span>
                                <input .value=${rule.rule_id || ''}
                                    @input=${(e) => this._updateRule(idx, 'rule_id', e.target.value)} />
                            </label>
                            <label class="field">
                                <span class="field-label-row">resource_name ${this._hint('hint_resource_name')}</span>
                                ${this._selectWithEmpty(this._settlementResourceNameOptions, rule.resource_name || '',
                                    (v) => this._updateRule(idx, 'resource_name', v))}
                            </label>
                            <label class="field">
                                <span class="field-label-row">usage_type ${this._hint('hint_usage_type')}</span>
                                ${this._selectWithEmpty(USAGE_TYPES, rule.usage_type || 'tool_call',
                                    (v) => this._updateRule(idx, 'usage_type', v))}
                            </label>
                        </div>
                        <div class="form-row">
                            <label class="field">
                                <span class="field-label-row">priority ${this._hint('hint_priority')}</span>
                                <input type="number" .value=${String(rule.priority ?? 100)}
                                    @input=${(e) => this._updateRule(idx, 'priority', Number(e.target.value) || 100)} />
                            </label>
                            <label class="field">
                                <span class="field-label-row">exclusive_group ${this._hint('hint_exclusive_group')}</span>
                                <input .value=${rule.exclusive_group || ''}
                                    @input=${(e) => this._updateRule(idx, 'exclusive_group', e.target.value)} />
                            </label>
                            <label class="field">
                                <span class="field-label-row">quantity_from ${this._hint('hint_quantity_from')}</span>
                                ${this._selectWithEmpty(QUANTITY_SOURCES, rule.quantity_from || 'const:1',
                                    (v) => this._updateRule(idx, 'quantity_from', v))}
                            </label>
                        </div>

                        ${this._renderMatchSection(rule, idx)}
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderMatchSection(rule, idx) {
        const match = rule.match || {};
        const attrs = match.attribute_equals || {};
        const attrEntries = Object.entries(attrs);

        return html`
            <div class="match-section">
                <div class="match-title">${this._t('rules_match_section')}</div>
                <div class="form-row">
                    <label class="field">
                        <span class="field-label-row">operation_name_prefix ${this._hint('hint_match_op_prefix')}</span>
                        ${this._selectWithEmpty(OPERATION_PREFIXES, match.operation_name_prefix || '',
                            (v) => this._updateRuleMatch(idx, 'operation_name_prefix', v))}
                    </label>
                    <label class="field">
                        <span class="field-label-row">operation_name_equals ${this._hint('hint_match_op_equals')}</span>
                        ${this._selectWithEmpty(OPERATION_NAMES, match.operation_name_equals || '',
                            (v) => this._updateRuleMatch(idx, 'operation_name_equals', v))}
                    </label>
                </div>
                <div class="form-row" style="margin-top: var(--space-2);">
                    <label class="field">
                        <span class="field-label-row">service_name_equals ${this._hint('hint_match_service')}</span>
                        ${this._selectWithEmpty(SERVICE_NAMES, match.service_name_equals || '',
                            (v) => this._updateRuleMatch(idx, 'service_name_equals', v))}
                    </label>
                    <label class="field">
                        <span class="field-label-row">event_type_equals ${this._hint('hint_match_event_type')}</span>
                        ${this._selectWithEmpty(EVENT_TYPES, match.event_type_equals || '',
                            (v) => this._updateRuleMatch(idx, 'event_type_equals', v))}
                    </label>
                </div>

                <div style="margin-top: var(--space-3);">
                    <div class="match-title"><span class="field-label-row">attribute_equals ${this._hint('hint_match_attrs')}</span></div>
                    ${attrEntries.map(([k, v]) => html`
                        <div class="kv-row">
                            ${this._selectWithEmpty(KNOWN_ATTR_KEYS, k,
                                (newKey) => this._updateRuleAttr(idx, k, newKey, v))}
                            <input placeholder="value" .value=${String(v)}
                                @input=${(e) => this._updateRuleAttr(idx, k, k, e.target.value)} />
                            ${this._iconBtn('trash', {
                                variant: 'danger', size: 'sm',
                                onClick: () => this._removeRuleAttr(idx, k),
                            })}
                        </div>
                    `)}
                    ${this._iconBtn('plus', {
                        size: 'sm',
                        title: this._t('rules_attr_add'),
                        onClick: () => this._addRuleAttr(idx),
                    })}
                </div>
            </div>
        `;
    }

    // ── Company prices ──

    _renderCompanyPricesSection() {
        return html`
            <div class="section">
                <h2 class="section-title">${this._t('section_company_prices')} ${this._hint('hint_company_prices')}</h2>
                ${this._cPriceError ? html`<div class="err">${this._cPriceError}</div>` : ''}
                <div style="display: flex; gap: var(--space-2); align-items: end; max-width: 32rem; margin-bottom: var(--space-3);">
                    <label class="field" style="flex: 1;">
                        ${this._t('company_price_id_label')}
                        <input .value=${this._cPriceCompanyId}
                            @input=${(e) => { this._cPriceCompanyId = e.target.value; }} />
                    </label>
                    ${this._iconBtn('search', {
                        variant: 'primary',
                        title: this._t('load_company_prices'),
                        disabled: this._cPriceLoading,
                        onClick: () => this._loadCompanyPrices(),
                    })}
                </div>

                ${this._cPriceOverrideRows.length > 0 || this._cPriceCompanyId ? html`
                    ${this._renderPriceTable(
                        this._cPriceOverrideRows,
                        (i, f, v) => {
                            const rows = [...this._cPriceOverrideRows];
                            rows[i] = { ...rows[i], [f]: f === 'price' ? Number(v) || 0 : v };
                            this._cPriceOverrideRows = rows;
                        },
                        (i) => { this._cPriceOverrideRows = this._cPriceOverrideRows.filter((_, j) => j !== i); },
                        () => { this._cPriceOverrideRows = [...this._cPriceOverrideRows, { category: '', resource: '', price: 0 }]; },
                    )}

                    <div class="toolbar">
                        ${this._iconBtn('save', {
                            variant: 'primary',
                            title: this._t('save_company_override'),
                            onClick: () => this._saveCompanyPrices(),
                        })}
                    </div>
                ` : ''}
            </div>
        `;
    }

    // ── Usage report ──

    _cellUsageCompany(row) {
        const cid = row.company_id ?? '';
        const name = row.company_name;
        if (name) {
            return html`
                <div>${name}</div>
                <div class="muted">${_shortCompanyIdHint(cid)}</div>
            `;
        }
        return cid;
    }

    _renderUsageSection() {
        const rows = this._usageRows;
        const hasSpan = rows.some(r => r.metadata?.span_id);
        const hasRule = rows.some(r => r.metadata?.rule_id);
        const colCount = 6 + (hasSpan ? 1 : 0) + (hasRule ? 1 : 0);

        const totalCost = rows.reduce((s, r) => s + (Number(r.cost) || 0), 0);
        const totalQty = rows.reduce((s, r) => s + (Number(r.quantity) || 0), 0);

        return html`
            <div class="section">
                <h2 class="section-title">${this._t('section_usage')} ${this._hint('hint_usage_section')}</h2>
                ${this._usageError ? html`<div class="err">${this._usageError}</div>` : ''}

                <div class="usage-filters-bar">
                    <div class="usage-filters-row">
                        ${this._renderUsageSuggest(
                            'company',
                            html`${this._t('filter_company')} ${this._hint('hint_filter_company')}`,
                        )}
                        ${this._renderUsageSuggest(
                            'usage_type',
                            html`${this._t('filter_usage_type')} ${this._hint('hint_filter_usage_type')}`,
                        )}
                        ${this._renderUsageSuggest(
                            'resource_name',
                            html`${this._t('filter_resource')} ${this._hint('hint_filter_resource')}`,
                        )}
                        <label class="field usage-filter-datetime">
                            <span class="field-label-row">${this._t('filter_from')} ${this._hint('hint_filter_from')}</span>
                            <platform-date-picker
                                mode="datetime"
                                value-format="iso"
                                hide-trigger-icon
                                .value=${this._uFrom || null}
                                @change=${(e) => { this._uFrom = e.target.value || ''; }}
                            ></platform-date-picker>
                        </label>
                        <label class="field usage-filter-datetime">
                            <span class="field-label-row">${this._t('filter_to')} ${this._hint('hint_filter_to')}</span>
                            <platform-date-picker
                                mode="datetime"
                                value-format="iso"
                                hide-trigger-icon
                                .value=${this._uTo || null}
                                @change=${(e) => { this._uTo = e.target.value || ''; }}
                            ></platform-date-picker>
                        </label>
                        <label class="field usage-filter-limit">
                            <span class="field-label-row">${this._t('filter_limit')} ${this._hint('hint_filter_limit')}</span>
                            <input type="number" min="1" max="5000" .value=${String(this._uLimit)}
                                @input=${(e) => { this._uLimit = Number(e.target.value) || 200; }} />
                        </label>
                        <div class="usage-filters-submit">
                            ${this._iconBtn('search', {
                                variant: 'primary',
                                title: `${this._t('apply')}. ${this._t('usage_facet_hint')}`,
                                disabled: this._usageLoading,
                                onClick: () => { this._uOffset = 0; void this._loadUsage(); },
                            })}
                            <span
                                class="usage-filters-hint"
                                title=${this._t('usage_facet_hint')}
                            >${this._t('usage_facet_hint')}</span>
                        </div>
                    </div>
                </div>

                <div class="table-wrap" style="margin-top: var(--space-3);">
                    <table class="usage-table">
                        <thead>
                            <tr>
                                <th>${this._t('col_time')}</th>
                                <th>${this._t('col_company')}</th>
                                <th>${this._t('col_resource')}</th>
                                <th>${this._t('col_quantity')}</th>
                                <th>${this._t('col_cost')}</th>
                                <th>${this._t('col_type')}</th>
                                ${hasSpan ? html`<th>${this._t('col_span')}</th>` : ''}
                                ${hasRule ? html`<th>${this._t('col_rule')}</th>` : ''}
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.length === 0
                                ? html`<tr><td colspan="${colCount}">${this._t('empty')}</td></tr>`
                                : rows.map((row) => html`
                                    <tr>
                                        <td>${row.timestamp ?? ''}</td>
                                        <td>${this._cellUsageCompany(row)}</td>
                                        <td>${row.resource_name ?? ''}</td>
                                        <td>${row.quantity ?? ''}</td>
                                        <td>${row.cost ?? ''}</td>
                                        <td>${row.usage_type ?? ''}</td>
                                        ${hasSpan ? html`<td>${row.metadata?.span_id ?? ''}</td>` : ''}
                                        ${hasRule ? html`<td>${row.metadata?.rule_id ?? ''}</td>` : ''}
                                    </tr>
                                `)}
                        </tbody>
                        ${rows.length > 0 ? html`
                            <tfoot>
                                <tr>
                                    <td colspan="3">${this._t('usage_totals')}</td>
                                    <td>${totalQty}</td>
                                    <td>${totalCost.toFixed(6)}</td>
                                    <td colspan="${1 + (hasSpan ? 1 : 0) + (hasRule ? 1 : 0)}"></td>
                                </tr>
                            </tfoot>
                        ` : ''}
                    </table>
                </div>

                ${rows.length > 0 || this._uOffset > 0 ? html`
                    <div class="pagination">
                        ${this._iconBtn('chevron-left', {
                            size: 'sm',
                            title: this._t('usage_prev'),
                            disabled: this._uOffset === 0,
                            onClick: () => this._usagePrevPage(),
                        })}
                        <span>${this._t('usage_page_info', { from: this._uOffset + 1, to: this._uOffset + rows.length })}</span>
                        ${this._iconBtn('chevron-right', {
                            size: 'sm',
                            title: this._t('usage_next'),
                            disabled: rows.length < this._uLimit,
                            onClick: () => this._usageNextPage(),
                        })}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('billing-admin-page', BillingAdminPage);
