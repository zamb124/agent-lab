/**
 * Scoped overrides builder for PlatformVariable payload.scopes.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../platform-button.js';

const SCOPE_FIELDS = ['company_id', 'user_id', 'namespace', 'channel', 'var'];
const SCOPE_OPS = ['eq', 'in', 'exists'];

interface ScopeMatch {
    field?: string;
    op?: string;
    ref_key?: string | null;
    value?: unknown;
}

interface VariableScope {
    value_kind?: string;
    value?: unknown;
    expression?: string;
    priority?: number;
    match?: ScopeMatch[];
}

function scopeText(value: unknown): string {
    if (typeof value === 'string') return value;
    if (value === undefined || value === null) return '';
    return String(value);
}

function scopeMatches(scope: VariableScope): ScopeMatch[] {
    return Array.isArray(scope.match) ? scope.match : [];
}

function _emptyScope(): VariableScope {
    return {
        value_kind: 'static',
        value: '',
        expression: '',
        priority: 0,
        match: [{ field: 'namespace', op: 'eq', ref_key: null, value: '' }],
    };
}

export class PlatformVariableScopesEditor extends PlatformElement {
    static i18nNamespace = 'company_variables';

    static override properties: PropertyDeclarations = {
        scopes: { type: Array, attribute: false },
        readonly: { type: Boolean, reflect: true },
    };

    declare scopes: VariableScope[];
    declare readonly: boolean;

    static override styles: CSSResultGroup = css`
        :host { display: block; }
        .help {
            font-size: var(--text-sm);
            color: var(--text-secondary);
            margin-bottom: var(--space-3);
            line-height: 1.5;
        }
        .scope-card {
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-md);
            padding: var(--space-3);
            margin-bottom: var(--space-3);
        }
        .scope-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-2);
        }
        .scope-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: var(--space-2);
        }
        .actions { margin-top: var(--space-2); }
    `;

    constructor() {
        super();
        this.scopes = [];
        this.readonly = false;
    }

    _emit(scopes: VariableScope[]): void {
        this.dispatchEvent(new CustomEvent('change', {
            bubbles: true,
            composed: true,
            detail: { scopes },
        }));
    }

    _updateScope(index: number, patch: Partial<VariableScope>): void {
        const next = this.scopes.map((scope, scopeIndex) => (
            scopeIndex === index ? { ...scope, ...patch } : scope
        ));
        this._emit(next);
    }

    _removeScope(index: number): void {
        const next = this.scopes.filter((_, scopeIndex) => scopeIndex !== index);
        this._emit(next);
    }

    _addScope(): void {
        this._emit([...this.scopes, _emptyScope()]);
    }

    _updateMatch(scopeIndex: number, matchIndex: number, patch: Partial<ScopeMatch>): void {
        const scope = this.scopes[scopeIndex];
        if (!scope) {
            throw new Error('platform-variable-scopes-editor: scope index out of range');
        }
        const match = scopeMatches(scope).map((entry, entryIndex) => (
            entryIndex === matchIndex ? { ...entry, ...patch } : entry
        ));
        this._updateScope(scopeIndex, { match });
    }

    override render(): TemplateResult {
        return html`
            <p class="help">${this.t('help.scopes.intro')}</p>
            ${this.scopes.map((scope: VariableScope, scopeIndex: number) => html`
                <div class="scope-card">
                    <div class="scope-head">
                        <strong>${this.t('editor.section_scopes')} #${scopeIndex + 1}</strong>
                        ${this.readonly ? '' : html`
                            <platform-button danger @click=${() => this._removeScope(scopeIndex)}>
                                ${this.t('editor.scope_remove')}
                            </platform-button>
                        `}
                    </div>
                    <div class="scope-grid">
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('editor.scope_priority')}
                            .value=${scope.priority}
                            ?disabled=${this.readonly}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                const priority = Number(e.detail.value);
                                if (Number.isNaN(priority)) {
                                    throw new Error('platform-variable-scopes-editor: priority must be number');
                                }
                                this._updateScope(scopeIndex, { priority });
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('editor.scope_override_value')}
                            .value=${scope.value_kind === 'expression' ? scope.expression : scopeText(scope.value)}
                            ?disabled=${this.readonly}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                const raw = typeof e.detail.value === 'string' ? e.detail.value : '';
                                this._updateScope(scopeIndex, {
                                    value_kind: 'static',
                                    value: raw,
                                    expression: '',
                                });
                            }}
                        ></platform-field>
                    </div>
                    ${scopeMatches(scope).map((entry: ScopeMatch, matchIndex: number) => html`
                        <div class="scope-grid">
                            <platform-field
                                type="enum"
                                mode="edit"
                                .label=${this.t('editor.scope_match_field')}
                                .value=${entry.field}
                                .options=${SCOPE_FIELDS.map((field) => ({ value: field, label: field }))}
                                ?disabled=${this.readonly}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateMatch(scopeIndex, matchIndex, { field: typeof e.detail.value === 'string' ? e.detail.value : '' })}
                            ></platform-field>
                            <platform-field
                                type="enum"
                                mode="edit"
                                .label=${this.t('editor.scope_match_op')}
                                .value=${entry.op}
                                .options=${SCOPE_OPS.map((op) => ({ value: op, label: op }))}
                                ?disabled=${this.readonly}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateMatch(scopeIndex, matchIndex, { op: typeof e.detail.value === 'string' ? e.detail.value : '' })}
                            ></platform-field>
                            ${entry.field === 'var'
                                ? html`
                                    <platform-field
                                        type="string"
                                        mode="edit"
                                        .label=${this.t('editor.scope_match_ref_key')}
                                        .value=${entry.ref_key === undefined || entry.ref_key === null ? '' : entry.ref_key}
                                        ?disabled=${this.readonly}
                                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateMatch(scopeIndex, matchIndex, {
                                            ref_key: typeof e.detail.value === 'string' ? e.detail.value : '',
                                        })}
                                    ></platform-field>
                                `
                                : html`
                                    <platform-field
                                        type="string"
                                        mode="edit"
                                        .label=${this.t('editor.scope_match_value')}
                                        .value=${entry.value === null || entry.value === undefined ? '' : String(entry.value)}
                                        ?disabled=${this.readonly}
                                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._updateMatch(scopeIndex, matchIndex, {
                                            value: typeof e.detail.value === 'string' ? e.detail.value : '',
                                        })}
                                    ></platform-field>
                                `}
                        </div>
                    `)}
                </div>
            `)}
            ${this.readonly ? '' : html`
                <div class="actions">
                    <platform-button @click=${() => this._addScope()}>${this.t('editor.scope_add')}</platform-button>
                </div>
            `}
        `;
    }
}

customElements.define('platform-variable-scopes-editor', PlatformVariableScopesEditor);
