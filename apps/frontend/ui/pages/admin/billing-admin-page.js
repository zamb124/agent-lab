/**
 * Админка биллинга: прайс-лист, правила settlement, отчёт usage (только system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { BaseService } from '@platform/lib/services/BaseService.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';

const api = new BaseService('/frontend');
const USAGE_FACET_DEBOUNCE_MS = 300;
const BILLING_COMPANY_SUGGEST_DEBOUNCE_MS = 280;

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
    'llm:*',
    'embedding:*',
    'livekit:room_create', 'livekit:egress_composite', 'livekit:egress_segmented',
];

const QUANTITY_SOURCES = [
    'const:1',
    'attr:platform.billing.quantity',
    'attr:platform.llm.total_tokens',
];

const OPERATION_PREFIXES = [
    'llm.',
    'flows.llm_resource.',
    'flows.llm.',
    'rag.embed',
    'core.files.reader',
    'livekit.',
    'sync.',
    'flows.external_api',
    'flows.mcp',
    'flows.channel',
    'flows.llm',
    'flows.tools',
    'livekit.room',
    'livekit.egress',
];

const OPERATION_NAMES = [
    'flows.llm.invoke_task',
    'flows.llm_resource.complete', 'flows.llm_resource.chat', 'flows.llm_resource.chat_with_tools',
    'flows.tools.ocr_vision',
    'flows.external_api.call',
    'flows.mcp.call_tool',
    'flows.channel.execute_action',
    'rag.embed.batch',
    'sync.stt.transcribe_audio_message',
    'sync.stt.transcribe_video_message',
    'sync.calls.finalize_recording',
    'core.files.reader.image',
    'livekit.room.create',
    'livekit.egress.room_composite_s3',
    'livekit.egress.track_composite_segmented',
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
            :host {
                display: block;
                color: var(--text-primary);
            }

            .muted {
                color: var(--text-secondary);
            }

            :host-context([data-theme="light"]) .muted,
            :host-context([data-theme="light"]) .billing-scope-compact .scope-active-line {
                color: rgba(30, 41, 59, 0.88);
            }

            :host-context([data-theme="light"]) .billing-scope-compact .scope-active-id {
                color: rgba(30, 41, 59, 0.62);
            }

            :host-context([data-theme="light"]) .billing-co-root .scope-banner-title {
                color: rgba(30, 41, 59, 0.72);
            }

            :host-context([data-theme="light"]) .billing-co-empty {
                color: rgba(30, 41, 59, 0.72);
            }

            :host-context([data-theme="light"]) .billing-section-meta.muted {
                color: rgba(30, 41, 59, 0.82);
            }

            :host-context([data-theme="light"]) .usage-table .muted {
                color: rgba(30, 41, 59, 0.72);
            }

            :host-context([data-theme="light"]) .billing-readonly-catalog-toggle .muted {
                color: rgba(30, 41, 59, 0.72);
            }

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

            .toolbar.toolbar-tight {
                margin-top: 0;
                margin-bottom: var(--space-2);
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
            }

            .toolbar.toolbar-compact {
                gap: var(--space-1);
            }

            .toolbar.toolbar-compact .icon-btn {
                width: 32px;
                height: 32px;
            }

            .price-override-block {
                margin-top: 0;
                margin-bottom: var(--space-3);
                padding-top: 0;
                border-top: none;
            }

            .billing-section-head-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }

            .billing-section-head-row > .section-title,
            .billing-section-head-row > h2.section-title {
                margin: 0;
                flex: 1 1 auto;
                min-width: 0;
            }

            .billing-section-head-row .toolbar {
                margin: 0;
                flex-shrink: 0;
            }

            .section-title--inline {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }

            .section-title--inline .section-title__text {
                margin: 0;
            }

            .override-subtitle {
                margin: 0 0 var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
            }

            .billing-company-prices-sub-head .billing-company-prices-sub-title {
                margin-bottom: 0;
                flex: 1 1 auto;
                min-width: 0;
            }

            .billing-section-meta {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
            }

            .price-table thead th {
                vertical-align: middle;
            }

            .price-table thead th .field-label-row {
                min-height: 24px;
            }

            .billing-prices-company-subsection {
                margin-top: var(--space-3);
                padding-top: var(--space-3);
                border-top: 1px solid var(--border-subtle);
            }

            .billing-fold-chevron {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                margin: 0;
                padding: 0;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
            }

            .billing-fold-chevron:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }

            .billing-section-head-fold {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .billing-section-head-fold .section-title {
                margin: 0;
                flex: 1;
                min-width: 0;
                font-size: var(--text-base);
            }

            .billing-readonly-catalog-toggle {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                margin: 0 0 var(--space-2);
                padding: var(--space-2) var(--space-3);
                text-align: left;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
            }

            .billing-readonly-catalog-toggle:hover {
                background: var(--glass-tint-medium);
            }

            .billing-readonly-catalog-toggle .muted {
                font-weight: var(--font-normal);
                font-size: var(--text-xs);
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

            /* Price tables */
            .price-catalog-wrap {
                max-height: min(24rem, 55vh);
                overflow: auto;
                margin-bottom: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                position: relative;
                isolation: isolate;
                background: var(--glass-solid-subtle);
            }
            table.price-catalog-table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-xs);
            }
            .price-catalog-table th,
            .price-catalog-table td {
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                text-align: left;
                color: var(--text-primary);
            }
            .price-catalog-table th {
                position: sticky;
                top: 0;
                z-index: 3;
                background: var(--glass-solid-strong);
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
                font-size: var(--text-xs);
                box-shadow: 0 1px 0 var(--border-subtle);
            }
            .price-catalog-table tbody tr:nth-child(even) {
                background: var(--glass-solid-subtle);
            }
            .price-catalog-table td.num {
                text-align: right;
                font-variant-numeric: tabular-nums;
                font-family: var(--font-mono, ui-monospace, monospace);
            }
            .price-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: var(--space-1);
                table-layout: fixed;
            }
            .price-table th,
            .price-table td {
                padding: var(--space-1) var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-xs);
                color: var(--text-primary);
                overflow: hidden;
                vertical-align: middle;
            }
            .price-table th {
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
            }
            .price-table td:nth-child(1),
            .price-table th:nth-child(1) {
                width: 28%;
            }
            .price-table td:nth-child(2),
            .price-table th:nth-child(2) {
                width: 44%;
            }
            .price-table td:nth-child(3),
            .price-table th:nth-child(3) {
                width: 22%;
            }
            .price-table td:last-child {
                width: 36px;
                text-align: center;
            }
            .price-table input,
            .price-table select {
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                padding: var(--space-1) var(--space-2);
                min-height: 32px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-xs);
            }

            /* Rules */
            .rule-card {
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-2);
                background: var(--glass-solid-subtle);
            }
            .rule-header-static {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }
            .rule-header-static .rule-summary {
                flex: 1;
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-primary);
                min-width: 0;
            }
            .rule-header-static .rule-id-label {
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
            }
            .rule-header-static .rule-resource-label {
                color: var(--text-secondary);
            }
            .rule-body {
                padding: var(--space-2);
                display: grid;
                gap: var(--space-2);
            }
            .rule-body .form-row {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
                gap: var(--space-2);
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
                padding: var(--space-1) var(--space-2);
                min-height: 32px;
                box-sizing: border-box;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
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

            .billing-page-intro {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }
            .billing-co-root.billing-scope-compact {
                flex: 0 0 auto;
                width: 100%;
                max-width: 22rem;
                position: relative;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md, 8px);
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.12));
                border-left-width: 4px;
                border-left-color: var(--accent-primary, var(--primary, #22c55e));
                background: var(--surface-elevated, var(--surface-secondary, rgba(255, 255, 255, 0.04)));
            }
            .billing-co-root .scope-banner-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin: 0 0 var(--space-1);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .billing-co-trigger {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-1);
                width: 100%;
                padding: var(--space-1) var(--space-2);
                min-height: 34px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-xs);
                cursor: pointer;
                text-align: left;
            }
            .billing-co-trigger-text {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .billing-co-panel {
                position: absolute;
                left: 0;
                right: 0;
                top: calc(100% + var(--space-1));
                z-index: 20;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-strong);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            }
            .billing-co-search {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-1) var(--space-2);
                margin-bottom: var(--space-2);
                min-height: 32px;
                font-size: var(--text-xs);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .billing-co-list {
                list-style: none;
                margin: 0;
                padding: 0;
                max-height: 12rem;
                overflow-y: auto;
            }
            .billing-co-item {
                display: block;
                width: 100%;
                padding: var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xs);
                text-align: left;
                cursor: pointer;
            }
            .billing-co-item:hover {
                background: var(--glass-tint-medium);
            }
            .billing-co-empty {
                padding: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .billing-scope-compact .scope-active-line {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
            }
            .billing-scope-compact .scope-active-id {
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: 10px;
                color: var(--text-tertiary);
                word-break: break-all;
                display: block;
                margin-top: 2px;
            }
            .billing-page-intro-header {
                width: 100%;
                min-width: 0;
            }
            .billing-page-intro-header page-header {
                margin-bottom: 0;
            }
            .billing-admin-tabs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin: var(--space-3) 0 var(--space-2);
            }
            .billing-admin-tab {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .billing-admin-tab:hover {
                background: var(--glass-tint-medium);
            }
            .billing-admin-tab[aria-selected='true'] {
                border-color: var(--accent-primary, var(--border-strong));
                background: var(--glass-tint-strong, var(--glass-tint-medium));
            }
            .billing-companies-table-wrap {
                overflow-x: auto;
                margin-top: var(--space-2);
            }
            .billing-companies-table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-xs);
            }
            .billing-companies-table th,
            .billing-companies-table td {
                padding: var(--space-2);
                text-align: left;
                border-bottom: 1px solid var(--border-default);
            }
            .billing-companies-table th {
                color: var(--text-secondary);
                font-weight: 600;
            }
            .billing-companies-table .num {
                text-align: right;
                font-variant-numeric: tabular-nums;
            }
        `,
    ];

    static properties = {
        _billingTab: { type: String, state: true },
        _companiesOverviewItems: { type: Array, state: true },
        _companiesOverviewLoading: { type: Boolean, state: true },
        _companiesOverviewError: { type: String, state: true },
        _companiesOverviewHasMore: { type: Boolean, state: true },
        _companiesOverviewOffset: { type: Number, state: true },

        _effectivePrices: { type: Object, state: true },
        _overrideRows: { type: Array, state: true },
        _pricesError: { type: String, state: true },
        _pricesLoading: { type: Boolean, state: true },

        _rulesDoc: { type: Object, state: true },
        _rulesError: { type: String, state: true },
        _rulesLoading: { type: Boolean, state: true },

        _billingTargetCompanyId: { type: String, state: true },
        _billingCompanyInput: { type: String, state: true },
        _billingCompanyOptions: { type: Array, state: true },
        _billingCompanyResolveError: { type: String, state: true },
        _billingPickerOpen: { type: Boolean, state: true },
        _billingPickerQuery: { type: String, state: true },
        _billingCompanyDisplayName: { type: String, state: true },
        _billingCompanyDisplaySlug: { type: String, state: true },
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


        _usageFacetOpen: { type: String, state: true },
        _usageFacetItems: { type: Object, state: true },

        _billingReadonlyCatalogExpanded: { type: Boolean, state: true },
        _settlementRulesExpanded: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this._billingTab = 'companies';
        this._companiesOverviewItems = [];
        this._companiesOverviewLoading = false;
        this._companiesOverviewError = '';
        this._companiesOverviewHasMore = false;
        this._companiesOverviewOffset = 0;

        this._effectivePrices = {};
        this._overrideRows = [];
        this._pricesError = '';
        this._pricesLoading = false;

        this._rulesDoc = { version: 1, application_mode: 'first_win', rules: [] };
        this._rulesError = '';
        this._rulesLoading = false;

        this._billingTargetCompanyId = '';
        this._billingCompanyInput = '';
        this._billingCompanyOptions = [];
        this._billingCompanyResolveError = '';
        this._billingPickerOpen = false;
        this._billingPickerQuery = '';
        this._billingCompanyDisplayName = '';
        this._billingCompanyDisplaySlug = '';
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

        this._pickCompany = '';
        this._pickUsageType = '';
        this._pickResource = '';
        this._usageFacetOpen = '';
        this._usageFacetItems = { company: [], usage_type: [], resource_name: [] };
        this._usageFacetDebounce = {};
        this._billingPickerSuggestTimer = 0;

        this._billingReadonlyCatalogExpanded = false;
        this._settlementRulesExpanded = false;
        this._usageOnDocClick = (e) => {
            if (this._billingPickerOpen) {
                const pathPicker = e.composedPath();
                const hitPicker = pathPicker.some(
                    (n) => n instanceof HTMLElement && n.classList?.contains('billing-co-root'),
                );
                if (!hitPicker) {
                    this._billingPickerOpen = false;
                }
            }
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
        void this._fetchBillingCompanySuggestInitial();
        if (this._billingTab === 'companies') {
            void this._loadCompaniesOverview(true);
        }
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._usageOnDocClick);
        Object.values(this._usageFacetDebounce).forEach((id) => clearTimeout(id));
        if (this._billingPickerSuggestTimer) {
            clearTimeout(this._billingPickerSuggestTimer);
            this._billingPickerSuggestTimer = 0;
        }
        super.disconnectedCallback();
    }

    _t(key, params = {}) {
        return this.i18n.t(`platform_billing_page.${key}`, params);
    }

    _billingSectionTitleSuffix() {
        const cid = (this._billingTargetCompanyId || '').trim();
        if (!cid) {
            return '';
        }
        const name = (this._billingCompanyDisplayName || '').trim();
        const slug = (this._billingCompanyDisplaySlug || '').trim();
        if (slug && name) {
            return ` — ${name} (${slug})`;
        }
        if (slug) {
            return ` — ${slug}`;
        }
        if (name) {
            return ` — ${name}`;
        }
        return ` — ${cid}`;
    }

    _effectiveCatalogRows() {
        const ep = this._effectivePrices;
        if (!ep || typeof ep !== 'object') {
            return [];
        }
        const rows = [];
        for (const [cat, resources] of Object.entries(ep)) {
            if (!resources || typeof resources !== 'object') {
                continue;
            }
            for (const [res, price] of Object.entries(resources)) {
                rows.push({ category: cat, resource: res, price: Number(price) });
            }
        }
        rows.sort((a, b) => {
            const c = a.category.localeCompare(b.category);
            if (c !== 0) {
                return c;
            }
            return a.resource.localeCompare(b.resource);
        });
        return rows;
    }

    _filteredBillingPickerOptions() {
        const q = (this._billingPickerQuery || '').trim().toLowerCase();
        const items = Array.isArray(this._billingCompanyOptions) ? this._billingCompanyOptions : [];
        if (!q) {
            return items;
        }
        return items.filter((item) => {
            if (!_usageFacetItemIsObject(item)) {
                return String(item).toLowerCase().includes(q);
            }
            const v = String(item.value || '').toLowerCase();
            const l = String(item.label || '').toLowerCase();
            return v.includes(q) || l.includes(q);
        });
    }

    _scheduleBillingCompanySuggestFromPicker() {
        if (this._billingPickerSuggestTimer) {
            clearTimeout(this._billingPickerSuggestTimer);
        }
        this._billingPickerSuggestTimer = window.setTimeout(() => {
            this._billingPickerSuggestTimer = 0;
            void this._fetchBillingCompanySuggestForQuery(this._billingPickerQuery);
        }, BILLING_COMPANY_SUGGEST_DEBOUNCE_MS);
    }

    async _selectBillingCompanyFromList(item) {
        if (!item || typeof item !== 'object' || !item.value) {
            return;
        }
        const cid = String(item.value).trim();
        const lbl = String(item.label || cid);
        this._billingTargetCompanyId = cid;
        this._billingPickerOpen = false;
        this._billingPickerQuery = '';
        this._billingCompanyResolveError = '';
        const m = /^(.+?)\s+\(([^)]+)\)\s*$/.exec(lbl);
        if (m) {
            this._billingCompanyDisplayName = m[1].trim();
            this._billingCompanyDisplaySlug = m[2].trim();
            this._billingCompanyInput = this._billingCompanyDisplaySlug;
        } else {
            this._billingCompanyDisplayName = lbl;
            this._billingCompanyDisplaySlug = '';
            this._billingCompanyInput = cid.length <= 36 ? cid : lbl;
        }
        this._uCompany = cid;
        await Promise.all([this._loadSettlementRules(), this._loadCompanyPrices()]);
    }

    async _applyBillingPickerManual() {
        const raw = (this._billingPickerQuery || '').trim();
        if (!raw) {
            return;
        }
        this._billingCompanyInput = raw;
        await this._applyBillingCompanyFromInput();
        if ((this._billingTargetCompanyId || '').trim()) {
            this._billingPickerOpen = false;
            this._billingPickerQuery = '';
        }
    }

    async _loadDefaultSettlementRulesTemplate() {
        const cid = (this._billingTargetCompanyId || '').trim();
        if (!cid) {
            this._rulesError = this._t('billing_company_required');
            return;
        }
        if (!window.confirm(this._t('confirm_replace_rules_default'))) {
            return;
        }
        this._rulesError = '';
        try {
            const data = await api.get('/api/platform-billing/default-settlement-rules');
            const doc = data.document;
            if (!doc || typeof doc !== 'object') {
                throw new Error(this._t('rules_template_invalid'));
            }
            this._rulesDoc = doc;
            this.success(this._t('rules_template_loaded'));
        } catch (e) {
            const msg = e && typeof e.message === 'string' ? e.message : String(e);
            this._rulesError = msg;
        }
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
        return this._priceResources(category);
    }

    get _settlementResourceNameOptions() {
        return [...SETTLEMENT_RESOURCE_NAMES_BASE].sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: 'base' }),
        );
    }

    async _fetchBillingCompanySuggestInitial() {
        await this._fetchBillingCompanySuggestForQuery('');
    }

    async _fetchBillingCompanySuggestForQuery(qRaw) {
        try {
            const params = { limit: 20 };
            const trimmed = (qRaw || '').trim();
            if (trimmed) {
                params.q = trimmed;
            }
            const data = await api.get('/api/platform-billing/facets/billing-companies', params);
            const items = Array.isArray(data.items) ? data.items : [];
            this._billingCompanyOptions = items;
        } catch {
            this._billingCompanyOptions = [];
        }
    }

    async _applyBillingCompanyFromInput() {
        const raw = (this._billingCompanyInput || '').trim();
        this._billingCompanyResolveError = '';
        if (!raw) {
            this._billingTargetCompanyId = '';
            this._billingCompanyDisplayName = '';
            this._billingCompanyDisplaySlug = '';
            this._uCompany = '';
            this._rulesDoc = { version: 1, application_mode: 'first_win', rules: [] };
            this._cPriceOverrideRows = [];
            return;
        }
        try {
            const resolved = await api.get('/api/platform-billing/company-resolve', { q: raw });
            const cid = resolved.company_id;
            if (!cid) {
                throw new Error(this._t('billing_company_resolve_failed'));
            }
            this._billingTargetCompanyId = cid;
            this._billingCompanyDisplayName = resolved.name ? String(resolved.name) : '';
            this._billingCompanyDisplaySlug = resolved.subdomain ? String(resolved.subdomain).trim() : '';
            const slug = this._billingCompanyDisplaySlug;
            this._billingCompanyInput = slug || cid;
            this._uCompany = cid;
            await Promise.all([this._loadSettlementRules(), this._loadCompanyPrices()]);
        } catch (e) {
            const msg = e && typeof e.message === 'string' ? e.message : String(e);
            this._billingCompanyResolveError = msg;
            this._billingTargetCompanyId = '';
            this._billingCompanyDisplayName = '';
            this._billingCompanyDisplaySlug = '';
            this._rulesDoc = { version: 1, application_mode: 'first_win', rules: [] };
            this._cPriceOverrideRows = [];
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

    async _loadCompaniesOverview(reset = false) {
        const pageSize = 50;
        if (reset) {
            this._companiesOverviewOffset = 0;
            this._companiesOverviewItems = [];
            this._companiesOverviewHasMore = false;
        }
        this._companiesOverviewLoading = true;
        this._companiesOverviewError = '';
        try {
            const data = await api.get('/api/platform-billing/companies-billing-overview', {
                limit: pageSize,
                offset: this._companiesOverviewOffset,
            });
            const chunk = Array.isArray(data.items) ? data.items : [];
            this._companiesOverviewItems = reset ? chunk : [...this._companiesOverviewItems, ...chunk];
            this._companiesOverviewHasMore = Boolean(data.has_more);
            this._companiesOverviewOffset = this._companiesOverviewItems.length;
        } catch (e) {
            this._companiesOverviewError = e && typeof e.message === 'string' ? e.message : String(e);
        } finally {
            this._companiesOverviewLoading = false;
        }
    }

    _onSelectBillingTab(tab) {
        if (this._billingTab === tab) {
            return;
        }
        this._billingTab = tab;
        if (tab === 'companies' && this._companiesOverviewItems.length === 0 && !this._companiesOverviewLoading) {
            void this._loadCompaniesOverview(true);
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
        const cid = (this._billingTargetCompanyId || '').trim();
        if (!cid) {
            this._rulesError = '';
            this._rulesDoc = { version: 1, application_mode: 'first_win', rules: [] };
            return;
        }
        this._rulesLoading = true;
        this._rulesError = '';
        try {
            const data = await api.get(
                `/api/platform-billing/settlement-rules/${encodeURIComponent(cid)}`,
            );
            const doc = data.document ?? { version: 1, application_mode: 'first_win', rules: [] };
            this._rulesDoc = doc;
        } catch (e) {
            this._rulesError = e.message;
        } finally {
            this._rulesLoading = false;
        }
    }

    async _saveSettlementRules() {
        const cid = (this._billingTargetCompanyId || '').trim();
        if (!cid) {
            this._rulesError = this._t('billing_company_required');
            return;
        }
        this._rulesError = '';
        const payload = {
            version: this._rulesDoc.version || 1,
            application_mode: this._rulesDoc.application_mode || 'first_win',
            rules: (this._rulesDoc.rules || []).map(_cleanRule),
        };
        try {
            await api.put(`/api/platform-billing/settlement-rules/${encodeURIComponent(cid)}`, payload);
            await this._loadSettlementRules();
            this.success(this._t('saved_ok'));
        } catch (e) {
            this._rulesError = e.message;
        }
    }

    _addRule() {
        const rules = [...(this._rulesDoc.rules || []), _emptyRule()];
        this._rulesDoc = { ...this._rulesDoc, rules };
    }

    _removeRule(idx) {
        const rules = (this._rulesDoc.rules || []).filter((_, i) => i !== idx);
        this._rulesDoc = { ...this._rulesDoc, rules };
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
        const cid = (this._billingTargetCompanyId || '').trim();
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
        const cid = (this._billingTargetCompanyId || '').trim();
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
        return html`<platform-help-hint .text=${this._t(key)}></platform-help-hint>`;
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
            <div class="billing-page-intro">
                <div class="billing-page-intro-header">
                    <page-header title=${this._t('title')} subtitle="">
                        <platform-help-hint
                            slot="actions"
                            .text=${this._t('hint_billing_page_about')}
                            label=${this._t('title')}
                        ></platform-help-hint>
                    </page-header>
                </div>
            </div>

            <div class="billing-admin-tabs" role="tablist" aria-label=${this._t('tabs_region_label')}>
                <button
                    type="button"
                    class="billing-admin-tab"
                    role="tab"
                    aria-selected=${this._billingTab === 'companies'}
                    @click=${() => this._onSelectBillingTab('companies')}
                >
                    ${this._t('tab_companies')}
                </button>
                <button
                    type="button"
                    class="billing-admin-tab"
                    role="tab"
                    aria-selected=${this._billingTab === 'prices'}
                    @click=${() => this._onSelectBillingTab('prices')}
                >
                    ${this._t('tab_prices_rules')}
                </button>
                <button
                    type="button"
                    class="billing-admin-tab"
                    role="tab"
                    aria-selected=${this._billingTab === 'usage'}
                    @click=${() => this._onSelectBillingTab('usage')}
                >
                    ${this._t('tab_usage')}
                </button>
            </div>

            ${this._billingTab === 'companies' ? this._renderCompaniesOverviewSection() : ''}
            ${this._billingTab === 'prices'
                ? html`
                      <div class="billing-page-intro" style="margin-top:0;">
                          ${this._renderBillingCompanyScopeCompact()}
                      </div>
                      ${this._renderPricesSection()}
                      ${this._renderSettlementRulesSection()}
                  `
                : ''}
            ${this._billingTab === 'usage' ? this._renderUsageSection() : ''}
        `;
    }

    _renderCompaniesOverviewSection() {
        const rows = this._companiesOverviewItems;
        return html`
            <div class="section" aria-label=${this._t('tab_companies')}>
                <div class="billing-section-head-row">
                    <h2 class="section-title section-title--inline">
                        <span class="section-title__text">${this._t('companies_overview_heading')}</span>
                    </h2>
                    <div class="toolbar toolbar-tight toolbar-compact">
                        ${this._iconBtn('refresh', {
                            title: this._t('reload'),
                            disabled: this._companiesOverviewLoading,
                            onClick: () => this._loadCompaniesOverview(true),
                        })}
                    </div>
                </div>
                ${this._companiesOverviewError
                    ? html`<div class="err">${this._companiesOverviewError}</div>`
                    : ''}
                ${this._companiesOverviewLoading && rows.length === 0
                    ? html`<div>${this._t('loading')}</div>`
                    : ''}
                ${rows.length === 0 && !this._companiesOverviewLoading && !this._companiesOverviewError
                    ? html`<p class="muted">${this._t('empty')}</p>`
                    : ''}
                ${rows.length > 0
                    ? html`
                          <div class="billing-companies-table-wrap">
                              <table class="billing-companies-table">
                                  <thead>
                                      <tr>
                                          <th>${this._t('col_company_id')}</th>
                                          <th>${this._t('col_name')}</th>
                                          <th>${this._t('col_subdomain')}</th>
                                          <th>${this._t('col_status')}</th>
                                          <th>${this._t('col_tariff')}</th>
                                          <th class="num">${this._t('col_balance')}</th>
                                          <th class="num">${this._t('col_monthly_budget')}</th>
                                          <th class="num">${this._t('col_spent_month')}</th>
                                      </tr>
                                  </thead>
                                  <tbody>
                                      ${rows.map(
                                          (r) => html`
                                              <tr>
                                                  <td><code>${r.company_id}</code></td>
                                                  <td>${r.name ?? ''}</td>
                                                  <td>${r.subdomain ?? '—'}</td>
                                                  <td>${r.status ?? ''}</td>
                                                  <td>${r.tariff_plan ?? ''}</td>
                                                  <td class="num">${r.balance}</td>
                                                  <td class="num">${r.monthly_budget}</td>
                                                  <td class="num">${r.current_month_spent}</td>
                                              </tr>
                                          `,
                                      )}
                                  </tbody>
                              </table>
                          </div>
                          ${this._companiesOverviewHasMore
                              ? html`
                                    <div style="margin-top:var(--space-3);">
                                        <platform-button
                                            variant="secondary"
                                            ?disabled=${this._companiesOverviewLoading}
                                            @click=${() => this._loadCompaniesOverview(false)}
                                        >
                                            ${this._t('companies_load_more')}
                                        </platform-button>
                                    </div>
                                `
                              : ''}
                      `
                    : ''}
            </div>
        `;
    }

    _renderBillingCompanyScopeCompact() {
        const activeId = (this._billingTargetCompanyId || '').trim();
        const triggerText = activeId
            ? (this._billingSectionTitleSuffix().replace(/^ — /, '') || activeId)
            : this._t('billing_company_pick_placeholder');
        const options = this._filteredBillingPickerOptions();
        return html`
            <div class="billing-co-root billing-scope-compact" role="region" aria-label=${this._t('billing_scope_region_label')}>
                <h2 class="scope-banner-title" style="display:flex;align-items:center;gap:var(--space-1);flex-wrap:wrap;">
                    ${this._t('billing_scope_banner_title')}
                    ${this._hint('hint_billing_company_pick')}
                </h2>
                <button
                    type="button"
                    class="billing-co-trigger"
                    @click=${(e) => {
                        e.stopPropagation();
                        const next = !this._billingPickerOpen;
                        this._billingPickerOpen = next;
                        if (next) {
                            this._billingPickerQuery = '';
                            void this._fetchBillingCompanySuggestForQuery('');
                        }
                    }}
                >
                    <span class="billing-co-trigger-text">${triggerText}</span>
                    <platform-icon name="chevron-down" size="14"></platform-icon>
                </button>
                ${this._billingPickerOpen
                    ? html`
                        <div class="billing-co-panel" @click=${(e) => e.stopPropagation()}>
                            <input
                                type="search"
                                class="billing-co-search"
                                placeholder=${this._t('billing_company_search_placeholder')}
                                .value=${this._billingPickerQuery}
                                @input=${(e) => {
                                    this._billingPickerQuery = e.target.value;
                                    this._scheduleBillingCompanySuggestFromPicker();
                                }}
                                @keydown=${(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        void this._applyBillingPickerManual();
                                    }
                                }}
                            />
                            <ul class="billing-co-list">
                                ${options.length === 0
                                    ? html`<li class="billing-co-empty">${this._t('billing_company_list_empty')}</li>`
                                    : options.map(
                                          (item) => html`
                                              <li>
                                                  <button
                                                      type="button"
                                                      class="billing-co-item"
                                                      @click=${() => this._selectBillingCompanyFromList(item)}
                                                  >
                                                      ${_usageFacetItemIsObject(item) ? item.label : item}
                                                  </button>
                                              </li>
                                          `,
                                      )}
                            </ul>
                        </div>
                    `
                    : ''}
                ${this._billingCompanyResolveError
                    ? html`<div class="err" style="margin-top: var(--space-2);">${this._billingCompanyResolveError}</div>`
                    : ''}
                ${activeId
                    ? html`<div class="scope-active-line">
                        <span>${this._t('billing_scope_active_label')}</span>
                        <span class="scope-active-id" title=${activeId}>id: ${activeId}</span>
                    </div>`
                    : html`<p class="muted scope-active-line">${this._t('billing_scope_none_hint')}</p>`}
            </div>
        `;
    }

    // ── Price catalog ──

    _renderEffectiveCatalogScrollable() {
        const rows = this._effectiveCatalogRows();
        if (rows.length === 0) {
            return html`<p class="muted" style="margin:0;">${this._t('price_catalog_empty')}</p>`;
        }
        return html`
            <div class="price-catalog-wrap">
                <table class="price-catalog-table">
                    <thead>
                        <tr>
                            <th>${this._t('price_col_category')}</th>
                            <th>${this._t('price_col_resource')}</th>
                            <th style="text-align:right">${this._t('price_col_price')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(
                            (row) => html`
                                <tr>
                                    <td>${row.category}</td>
                                    <td><code>${row.resource}</code></td>
                                    <td class="num">${row.price}</td>
                                </tr>
                            `,
                        )}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderPriceTable(rows, onUpdate, onRemove) {
        return html`
            <table class="price-table">
                <thead>
                    <tr>
                        <th>
                            <span class="field-label-row">${this._t('price_col_category')} ${this._hint('hint_price_category')}</span>
                        </th>
                        <th>
                            <span class="field-label-row">${this._t('price_col_resource')} ${this._hint('hint_price_resource')}</span>
                        </th>
                        <th>
                            <span class="field-label-row">${this._t('price_col_price')} ${this._hint('hint_price_price')}</span>
                        </th>
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
        `;
    }

    _renderPricesSection() {
        const catalogRows = this._effectiveCatalogRows();
        const catalogCount = catalogRows.length;
        return html`
            <div class="section">
                <div class="billing-section-head-row" aria-label=${this._t('section_prices')}>
                    <h2 class="section-title section-title--inline">
                        <span class="section-title__text">${this._t('section_prices')}</span>
                        ${this._hint('hint_prices_section')}
                    </h2>
                    <div class="toolbar toolbar-tight toolbar-compact">
                        ${this._iconBtn('plus', {
                            title: this._t('price_add_row'),
                            onClick: () => this._addOverrideRow(),
                        })}
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
                </div>
                ${this._pricesError ? html`<div class="err">${this._pricesError}</div>` : ''}
                ${this._pricesLoading
                    ? html`<div>${this._t('loading')}</div>`
                    : html`
                        <div class="price-override-block">
                            <h3 class="override-subtitle">
                                ${this._t('section_prices_override_only')}
                                ${this._hint('hint_prices_override_only')}
                            </h3>
                            ${this._renderPriceTable(
                                this._overrideRows,
                                (i, f, v) => this._updateOverrideRow(i, f, v),
                                (i) => this._removeOverrideRow(i),
                            )}
                        </div>

                        <button
                            type="button"
                            class="billing-readonly-catalog-toggle"
                            aria-expanded=${this._billingReadonlyCatalogExpanded}
                            title=${this._billingReadonlyCatalogExpanded
                                ? this._t('billing_collapse')
                                : this._t('billing_expand')}
                            @click=${() => {
                                this._billingReadonlyCatalogExpanded = !this._billingReadonlyCatalogExpanded;
                            }}
                        >
                            <platform-icon
                                name=${this._billingReadonlyCatalogExpanded ? 'chevron-down' : 'chevron-right'}
                                size="16"
                            ></platform-icon>
                            <span>${this._t('billing_readonly_catalog_title')}</span>
                            <span class="muted">${this._t('billing_readonly_catalog_rows', { count: catalogCount })}</span>
                        </button>
                        ${this._billingReadonlyCatalogExpanded ? this._renderEffectiveCatalogScrollable() : ''}

                        ${this._renderCompanyPricesSubsection()}
                    `}
            </div>
        `;
    }

    // ── Settlement rules ──

    _renderSettlementRulesSection() {
        const cid = (this._billingTargetCompanyId || '').trim();
        const disabled = !cid;
        const rulesCount = (this._rulesDoc.rules || []).length;
        return html`
            <div class="section">
                <div class="billing-section-head-fold">
                    <button
                        type="button"
                        class="billing-fold-chevron"
                        aria-expanded=${this._settlementRulesExpanded}
                        title=${this._settlementRulesExpanded
                            ? this._t('billing_collapse')
                            : this._t('billing_expand')}
                        @click=${() => {
                            this._settlementRulesExpanded = !this._settlementRulesExpanded;
                        }}
                    >
                        <platform-icon
                            name=${this._settlementRulesExpanded ? 'chevron-down' : 'chevron-right'}
                            size="18"
                        ></platform-icon>
                    </button>
                    <div style="flex:1;min-width:0;">
                        <h2 class="section-title section-title--inline">
                            <span class="section-title__text">
                                ${this._t('section_settlement_rules')}${this._billingSectionTitleSuffix()}
                            </span>
                            ${this._hint('hint_settlement_section')}
                            ${cid
                                ? html`<span class="billing-section-meta muted">${this._t('rules_count_badge', { count: rulesCount })}</span>`
                                : ''}
                        </h2>
                    </div>
                </div>
                ${this._rulesError ? html`<div class="err">${this._rulesError}</div>` : ''}
                ${disabled ? html`<div class="err">${this._t('billing_company_required')}</div>` : ''}
                ${this._rulesLoading
                    ? html`<div>${this._t('loading')}</div>`
                    : this._settlementRulesExpanded
                      ? html`
                            <div
                                class="toolbar toolbar-tight toolbar-compact"
                                style="margin-bottom:var(--space-2);"
                                aria-label=${this._t('section_settlement_rules')}
                            >
                                ${this._iconBtn('plus', {
                                    title: this._t('rules_add_rule'),
                                    disabled,
                                    onClick: () => this._addRule(),
                                })}
                                ${this._iconBtn('refresh', {
                                    title: this._t('reload'),
                                    disabled,
                                    onClick: () => this._loadSettlementRules(),
                                })}
                                <button
                                    type="button"
                                    class="icon-btn"
                                    ?disabled=${disabled}
                                    title=${this._t('rules_load_platform_default')}
                                    @click=${() => void this._loadDefaultSettlementRulesTemplate()}
                                >
                                    <platform-icon name="book-open" size="16"></platform-icon>
                                </button>
                                ${this._iconBtn('save', {
                                    variant: 'primary',
                                    title: this._t('save_rules'),
                                    disabled,
                                    onClick: () => this._saveSettlementRules(),
                                })}
                            </div>
                            ${this._renderRulesForm()}
                        `
                      : ''}
            </div>
        `;
    }

    _renderRulesForm() {
        const doc = this._rulesDoc;
        const rules = doc.rules || [];
        return html`
            <div style="display:flex;gap:var(--space-3);align-items:center;margin-bottom:var(--space-2);">
                <label class="field" style="margin:0;">
                    <span class="field-label-row">${this._t('rules_application_mode')} ${this._hint('hint_application_mode')}</span>
                    <select .value=${doc.application_mode || 'all_matching'}
                        @change=${(e) => { this._rulesDoc = { ...doc, application_mode: e.target.value }; }}>
                        <option value="all_matching">all_matching</option>
                        <option value="first_win">first_win</option>
                    </select>
                </label>
            </div>

            ${rules.map((rule, idx) => this._renderRuleCard(rule, idx))}
        `;
    }

    _renderRuleCard(rule, idx) {
        return html`
            <div class="rule-card">
                <div class="rule-header-static">
                    <div class="rule-summary">
                        <span class="rule-id-label">${rule.rule_id || this._t('rules_new')}</span>
                        <span class="rule-resource-label">${rule.resource_name || ''}</span>
                    </div>
                    <platform-switch
                        ?checked=${rule.enabled !== false}
                        size="sm"
                        @change=${(e) => { this._updateRule(idx, 'enabled', e.detail.value); }}
                    ></platform-switch>
                    <span @click=${() => this._removeRule(idx)}>
                        ${this._iconBtn('trash', { variant: 'danger', size: 'sm' })}
                    </span>
                </div>
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

    // ── Company prices (вложено в секцию «Каталог цен») ──

    _renderCompanyPricesSubsection() {
        const cid = (this._billingTargetCompanyId || '').trim();
        const disabled = !cid;
        return html`
            <div class="billing-prices-company-subsection">
                <div class="billing-section-head-row billing-company-prices-sub-head">
                    <h3 class="override-subtitle billing-company-prices-sub-title">
                        ${this._t('subsection_company_prices_title')}
                        ${this._billingSectionTitleSuffix()}
                        ${this._hint('hint_company_prices')}
                    </h3>
                    ${cid
                        ? html`
                              <div
                                  class="toolbar toolbar-tight toolbar-compact"
                                  aria-label=${this._t('subsection_company_prices_title')}
                              >
                                  ${this._iconBtn('plus', {
                                      title: this._t('price_add_row'),
                                      disabled: this._cPriceLoading,
                                      onClick: () => {
                                          this._cPriceOverrideRows = [
                                              ...this._cPriceOverrideRows,
                                              { category: '', resource: '', price: 0 },
                                          ];
                                      },
                                  })}
                                  ${this._iconBtn('refresh', {
                                      title: this._t('load_company_prices'),
                                      disabled: this._cPriceLoading,
                                      onClick: () => this._loadCompanyPrices(),
                                  })}
                                  ${this._iconBtn('save', {
                                      variant: 'primary',
                                      title: this._t('save_company_override'),
                                      disabled,
                                      onClick: () => this._saveCompanyPrices(),
                                  })}
                              </div>
                          `
                        : ''}
                </div>
                ${this._cPriceError ? html`<div class="err">${this._cPriceError}</div>` : ''}
                ${disabled ? html`<div class="err">${this._t('billing_company_required')}</div>` : ''}
                ${cid
                    ? this._renderPriceTable(
                          this._cPriceOverrideRows,
                          (i, f, v) => {
                              const rows = [...this._cPriceOverrideRows];
                              rows[i] = { ...rows[i], [f]: f === 'price' ? Number(v) || 0 : v };
                              this._cPriceOverrideRows = rows;
                          },
                          (i) => {
                              this._cPriceOverrideRows = this._cPriceOverrideRows.filter((_, j) => j !== i);
                          },
                      )
                    : ''}
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
                <h2 class="section-title section-title--inline">
                    <span class="section-title__text">${this._t('section_usage')}</span>
                    ${this._hint('hint_usage_section')}
                </h2>
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
                                title: this._t('apply'),
                                disabled: this._usageLoading,
                                onClick: () => { this._uOffset = 0; void this._loadUsage(); },
                            })}
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
