/**
 * Страница управления правилами произношения TTS компании.
 *
 * Маршрут: company-pronunciation-rules (parent: company-voice-providers)
 * Данные: frontend/company_pronunciation_rules_load
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';

const KIND_OPTIONS = [
    { value: 'alias', label: 'Алиас' },
    { value: 'regex', label: 'Regex' },
    { value: 'stress', label: 'Ударение (+)' },
];

const PROVIDER_OPTIONS = [
    { value: 'litserve', label: 'Silero (litserve)' },
    { value: 'cloud_ru', label: 'Cloud.ru' },
    { value: 'yandex', label: 'Yandex SpeechKit' },
    { value: 'sber', label: 'Sber SmartSpeech' },
    { value: 'mock', label: 'Mock (тесты)' },
];

const KIND_ICON = { alias: 'edit', regex: 'settings', stress: 'microphone' };
const KIND_CLASS = { alias: 'kind-alias', regex: 'kind-regex', stress: 'kind-stress' };

function _emptyDraft() {
    return {
        kind: 'alias',
        pattern: '',
        replacement: '',
        language: 'ru',
        case_sensitive: false,
        word_boundary: true,
        enabled: true,
        note: '',
    };
}

class CompanyPronunciationRulesPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static styles = [
        frontendIslandPageBodyStyles,
        css`
            :host { display: block; }

            .card {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-5);
                margin-bottom: var(--space-4);
            }

            .card-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .card-title .count {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
            }

            .fields-grid {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .fields-grid.two-col { grid-template-columns: 1fr 1fr; }

            .toggles-row {
                display: flex;
                gap: var(--space-6);
                margin-bottom: var(--space-4);
                flex-wrap: wrap;
            }

            .actions-row {
                display: flex;
                gap: var(--space-2);
            }

            /* ── Rules list ─────────────────────────── */
            .rules-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .rule-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: background 0.12s;
            }

            .rule-item:hover { background: var(--glass-solid-strong); }
            .rule-item.rule-disabled { opacity: 0.45; }
            .rule-item.rule-editing { border-color: var(--accent); }

            .kind-badge {
                display: inline-flex;
                align-items: center;
                gap: 3px;
                padding: 3px 8px;
                border-radius: var(--radius-md);
                font-size: 11px;
                font-weight: var(--font-semibold);
                flex-shrink: 0;
                min-width: 76px;
            }

            .kind-alias { background: #dbeafe; color: #1e40af; }
            .kind-regex { background: #fef3c7; color: #92400e; }
            .kind-stress { background: #d1fae5; color: #065f46; }

            .rule-mono {
                font-family: monospace;
                font-size: var(--text-sm);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
            }

            .rule-pattern { color: var(--text-secondary); background: var(--glass-solid-medium); }
            .rule-replacement { color: var(--text-primary); font-weight: var(--font-medium); }

            .rule-arrow { color: var(--text-tertiary); flex-shrink: 0; font-size: var(--text-sm); }

            .rule-lang {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
                background: var(--glass-solid-medium);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
            }

            .rule-actions {
                display: flex;
                gap: var(--space-1);
                flex-shrink: 0;
                margin-left: auto;
            }

            .empty-state {
                text-align: center;
                padding: var(--space-8) var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            /* ── Test section ─────────────────────── */
            .test-result {
                margin-top: var(--space-4);
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
            }

            .test-result.result-changed {
                border-color: #22c55e;
                background: #f0fdf4;
            }

            .result-block { margin-bottom: var(--space-3); }
            .result-block:last-child { margin-bottom: 0; }

            .result-label {
                font-size: 11px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .result-code {
                font-family: monospace;
                font-size: var(--text-sm);
                color: var(--text-primary);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-strong);
                border-radius: var(--radius-md);
                white-space: pre-wrap;
                word-break: break-all;
                border: 1px solid var(--glass-border-subtle);
            }

            .no-change-note {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
        `,
    ];

    static properties = {
        _draft: { state: true },
        _editId: { state: true },
        _testText: { state: true },
        _testProvider: { state: true },
        _testResult: { state: true },
    };

    constructor() {
        super();
        this._loadOp   = this.useOp('frontend/company_pronunciation_rules_load');
        this._createOp = this.useOp('frontend/company_pronunciation_rule_create');
        this._updateOp = this.useOp('frontend/company_pronunciation_rule_update');
        this._deleteOp = this.useOp('frontend/company_pronunciation_rule_delete');
        this._testOp   = this.useOp('frontend/company_pronunciation_rule_test');
        this._slice    = this.select(s => s.frontendCompanyPronunciationRulesLoad);
        this._auth     = this.select(s => s.auth);
        this._draft      = _emptyDraft();
        this._editId     = null;
        this._testText   = '';
        this._testProvider = 'litserve';
        this._testResult = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._reload();
    }

    _activeCompanyId() {
        const auth = this._auth.value;
        if (!auth) return null;
        const cid = auth.activeCompanyId;
        if (typeof cid !== 'string' || cid.length === 0) return null;
        return cid;
    }

    async _reload() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        await this._loadOp.run({ company_id });
    }

    _getItems() {
        const slice = this._slice.value;
        if (!slice || !Array.isArray(slice.items)) return [];
        return slice.items;
    }

    _setDraft(field, value) {
        this._draft = { ...this._draft, [field]: value };
    }

    _startEdit(item) {
        this._editId = item.id;
        this._draft = {
            kind:           item.kind,
            pattern:        item.pattern,
            replacement:    item.replacement,
            language:       typeof item.language === 'string' ? item.language : '',
            case_sensitive: item.case_sensitive === true,
            word_boundary:  item.word_boundary !== false,
            enabled:        item.enabled !== false,
            note:           typeof item.note === 'string' ? item.note : '',
        };
    }

    _cancelEdit() {
        this._editId = null;
        this._draft = _emptyDraft();
    }

    async _save() {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const pattern = this._draft.pattern.trim();
        const replacement = this._draft.replacement.trim();
        if (!pattern || !replacement) return;

        const lang = this._draft.language.trim();
        const note = this._draft.note.trim();

        const base = {
            company_id,
            kind:           this._draft.kind,
            pattern,
            replacement,
            language:       lang.length > 0 ? lang : null,
            case_sensitive: this._draft.case_sensitive,
            word_boundary:  this._draft.word_boundary,
            enabled:        this._draft.enabled,
            note:           note.length > 0 ? note : null,
        };

        const result = this._editId
            ? await this._updateOp.run({ ...base, rule_id: this._editId })
            : await this._createOp.run(base);

        if (result) {
            this._editId = null;
            this._draft = _emptyDraft();
            await this._reload();
        }
    }

    async _delete(ruleId) {
        const company_id = this._activeCompanyId();
        if (!company_id) return;
        const result = await this._deleteOp.run({ company_id, rule_id: ruleId });
        if (result) {
            await this._reload();
        }
    }

    async _runTest() {
        const company_id = this._activeCompanyId();
        if (!company_id || !this._testText) return;
        this._testResult = null;
        const result = await this._testOp.run({
            company_id,
            text:     this._testText,
            provider: this._testProvider,
        });
        if (result) {
            this._testResult = result;
        }
    }

    render() {
        const company_id = this._activeCompanyId();
        if (!company_id) {
            return html`
                <platform-breadcrumbs></platform-breadcrumbs>
                <page-header .title=${this.t('pronunciation_rules_page.title')}></page-header>
                <div class="card">
                    <p style="color:var(--text-secondary);margin:0">
                        ${this.t('pronunciation_rules_page.empty_no_company')}
                    </p>
                </div>
            `;
        }
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                .title=${this.t('pronunciation_rules_page.title')}
                .subtitle=${this.t('pronunciation_rules_page.subtitle')}
            ></page-header>
            ${this._renderForm()}
            ${this._renderRules()}
            ${this._renderTest()}
        `;
    }

    _renderForm() {
        const d = this._draft;
        const isEdit   = Boolean(this._editId);
        const isBusy   = this._createOp.busy || this._updateOp.busy;
        const canSave  = d.pattern.trim().length > 0 && d.replacement.trim().length > 0 && !isBusy;

        return html`
            <div class="card">
                <h3 class="card-title">
                    <platform-icon name="${isEdit ? 'edit' : 'plus'}" size="16"></platform-icon>
                    ${isEdit
                        ? this.t('pronunciation_rules_page.form_edit')
                        : this.t('pronunciation_rules_page.form_add')}
                </h3>

                <div class="fields-grid">
                    <platform-field
                        type="enum"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_kind')}"
                        .value=${d.kind}
                        .config=${{ values: KIND_OPTIONS }}
                        @change=${e => this._setDraft('kind', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_pattern')}"
                        .value=${d.pattern}
                        placeholder="Хуманитик"
                        @change=${e => this._setDraft('pattern', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_replacement')}"
                        .value=${d.replacement}
                        placeholder="хуманитэк"
                        @change=${e => this._setDraft('replacement', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="fields-grid two-col">
                    <platform-field
                        type="string"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_language')}"
                        .value=${d.language}
                        placeholder="ru"
                        .hint=${this.t('pronunciation_rules_page.hint_language')}
                        @change=${e => this._setDraft('language', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="text"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_note')}"
                        .value=${d.note}
                        placeholder="${this.t('pronunciation_rules_page.placeholder_note')}"
                        @change=${e => this._setDraft('note', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="toggles-row">
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_word_boundary')}"
                        .value=${d.word_boundary}
                        .hint=${this.t('pronunciation_rules_page.hint_word_boundary')}
                        @change=${e => this._setDraft('word_boundary', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_case_sensitive')}"
                        .value=${d.case_sensitive}
                        @change=${e => this._setDraft('case_sensitive', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.field_enabled')}"
                        .value=${d.enabled}
                        @change=${e => this._setDraft('enabled', e.detail.value)}
                    ></platform-field>
                </div>

                <div class="actions-row">
                    <glass-button ?disabled=${!canSave} @click=${this._save}>
                        ${isBusy
                            ? html`<glass-spinner size="sm"></glass-spinner>`
                            : html`<platform-icon name="${isEdit ? 'check' : 'plus'}" size="14"></platform-icon>`}
                        ${isEdit
                            ? this.t('pronunciation_rules_page.btn_update')
                            : this.t('pronunciation_rules_page.btn_add')}
                    </glass-button>
                    ${isEdit ? html`
                        <glass-button variant="ghost" @click=${this._cancelEdit}>
                            ${this.t('pronunciation_rules_page.btn_cancel')}
                        </glass-button>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _renderRules() {
        const items     = this._getItems();
        const isLoading = this._loadOp.busy;
        const isDeleting = this._deleteOp.busy;

        return html`
            <div class="card">
                <h3 class="card-title">
                    <platform-icon name="database" size="16"></platform-icon>
                    ${this.t('pronunciation_rules_page.section_rules')}
                    ${items.length > 0
                        ? html`<span class="count">(${items.length})</span>`
                        : nothing}
                </h3>

                ${isLoading
                    ? html`<glass-spinner></glass-spinner>`
                    : items.length === 0
                        ? html`
                            <div class="empty-state">
                                <div style="margin-bottom:var(--space-2)">
                                    <platform-icon name="microphone" size="28"></platform-icon>
                                </div>
                                ${this.t('pronunciation_rules_page.empty')}
                            </div>
                        `
                        : html`
                            <div class="rules-list">
                                ${items.map(item => this._renderRule(item, isDeleting))}
                            </div>
                        `}
            </div>
        `;
    }

    _renderRule(item, isDeleting) {
        const isEditing = this._editId === item.id;
        return html`
            <div class="rule-item
                ${!item.enabled ? 'rule-disabled' : ''}
                ${isEditing ? 'rule-editing' : ''}
            ">
                <span class="kind-badge ${KIND_CLASS[item.kind] || 'kind-alias'}">
                    <platform-icon name="${KIND_ICON[item.kind] || 'edit'}" size="11"></platform-icon>
                    ${item.kind}
                </span>
                <span class="rule-mono rule-pattern">${item.pattern}</span>
                <span class="rule-arrow">→</span>
                <span class="rule-mono rule-replacement">${item.replacement}</span>
                ${item.language
                    ? html`<span class="rule-lang">${item.language}</span>`
                    : nothing}
                <span class="rule-actions">
                    <glass-button
                        size="sm"
                        variant="ghost"
                        title="${this.t('pronunciation_rules_page.btn_edit')}"
                        ?disabled=${Boolean(this._editId)}
                        @click=${() => this._startEdit(item)}
                    >
                        <platform-icon name="edit" size="14"></platform-icon>
                    </glass-button>
                    <glass-button
                        size="sm"
                        variant="ghost"
                        title="${this.t('pronunciation_rules_page.btn_delete')}"
                        ?disabled=${isDeleting}
                        @click=${() => this._delete(item.id)}
                    >
                        <platform-icon name="trash" size="14"></platform-icon>
                    </glass-button>
                </span>
            </div>
        `;
    }

    _renderTest() {
        const result   = this._testResult;
        const isBusy   = this._testOp.busy;

        return html`
            <div class="card">
                <h3 class="card-title">
                    <platform-icon name="settings" size="16"></platform-icon>
                    ${this.t('pronunciation_rules_page.test_title')}
                </h3>

                <div class="fields-grid two-col">
                    <platform-field
                        type="text"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.test_input')}"
                        .value=${this._testText}
                        placeholder="Хуманитик — платформа автоматизации"
                        @change=${e => { this._testText = e.detail.value; this._testResult = null; }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label="${this.t('pronunciation_rules_page.test_provider')}"
                        .value=${this._testProvider}
                        .config=${{ values: PROVIDER_OPTIONS }}
                        @change=${e => { this._testProvider = e.detail.value; this._testResult = null; }}
                    ></platform-field>
                </div>

                <glass-button
                    ?disabled=${!this._testText || isBusy}
                    @click=${this._runTest}
                >
                    ${isBusy
                        ? html`<glass-spinner size="sm"></glass-spinner>`
                        : html`<platform-icon name="check" size="14"></platform-icon>`}
                    ${this.t('pronunciation_rules_page.test_run')}
                </glass-button>

                ${result ? html`
                    <div class="test-result ${result.changed ? 'result-changed' : ''}">
                        <div class="result-block">
                            <div class="result-label">${this.t('pronunciation_rules_page.test_original')}</div>
                            <div class="result-code">${result.original}</div>
                        </div>
                        <div class="result-block">
                            <div class="result-label">${this.t('pronunciation_rules_page.test_transformed')}</div>
                            <div class="result-code">${result.transformed}</div>
                        </div>
                        ${!result.changed ? html`
                            <div class="no-change-note">
                                <platform-icon name="check" size="13"></platform-icon>
                                ${this.t('pronunciation_rules_page.test_no_change')}
                            </div>
                        ` : nothing}
                    </div>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('company-pronunciation-rules-page', CompanyPronunciationRulesPage);
