/**
 * Settings page — настройки компании.
 *
 * Состав:
 *   - Профиль компании (имя, monthly_budget, metadata JSON).
 *   - AI providers (capabilities + custom OpenAI-compatible providers) — рендерится
 *     поверх единого core-компонента <platform-llm-config-editor>.
 *
 * Все взаимодействие с AI-настройками — через resource-операции
 * apps/frontend/ui/events/resources/settings.resource.js.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/llm/llm-config-editor.js';
import '@platform/lib/components/llm/llm-context-editor.js';

const INTEGRATION_LIST = Object.freeze([
    { id: 'crm', route: '/crm' },
    { id: 'flows', route: '/flows' },
    { id: 'rag', route: '/rag' },
    { id: 'sync', route: '/sync' },
]);

export class FrontendSettingsPage extends PlatformPage {
    static styles = [
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
                font-size: var(--text-md);
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
                font-size: var(--text-md);
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
        `,
        frontendIslandPageBodyStyles,
    ];

    static properties = {
        _activeTab: { state: true },
        _name: { state: true },
        _monthlyBudget: { state: true },
        _metadataJson: { state: true },
        _metadataError: { state: true },
        _capabilityDrafts: { state: true },
        _llmContextDraft: { state: true },
    };

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
        this._loaded = false;
        this._aiLoaded = false;
        this._lastSeededCompanyRef = null;
        this._lastSeededAiRef = null;
        this._activeTab = 'company';
        this._name = '';
        this._monthlyBudget = 0;
        this._metadataJson = '{}';
        this._metadataError = '';
        this._capabilityDrafts = {};
        this._llmContextDraft = {};
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._load.run();
        }
        if (!this._aiLoaded) {
            this._aiLoaded = true;
            this._aiLoad.run();
        }
        const company = this._load.lastResult;
        if (company && company !== this._lastSeededCompanyRef) {
            this._lastSeededCompanyRef = company;
            this._seedDraft(company);
        }
        const ai = this._aiLoad.lastResult;
        if (ai && ai !== this._lastSeededAiRef) {
            this._lastSeededAiRef = ai;
            this._seedAiDraft(ai);
        }
    }

    _seedDraft(company) {
        this._name = company.name || '';
        this._monthlyBudget = Number(company.monthly_budget || 0);
        const metadata = company.metadata || {};
        this._metadataJson = JSON.stringify(metadata, null, 2);
    }

    _seedAiDraft(data) {
        const ctx = data && typeof data === 'object' && data.llm_context && typeof data.llm_context === 'object'
            ? data.llm_context
            : {};
        this._llmContextDraft = ctx.config && typeof ctx.config === 'object' && !Array.isArray(ctx.config)
            ? { ...ctx.config }
            : {};
    }

    _setTab(tab) {
        this._activeTab = tab;
    }

    _save() {
        let metadata = null;
        const trimmed = (this._metadataJson || '').trim();
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
            } catch {
                this._metadataError = this.t('settings_page.metadata_invalid');
                return;
            }
        }
        const body = {
            name: this._name.trim(),
            monthly_budget: this._monthlyBudget,
        };
        if (metadata !== null) body.metadata = metadata;
        this._update.run(body);
    }

    _renderTabs() {
        const tabs = [
            { id: 'company', label: this.t('settings_page.tab_company') },
            { id: 'ai_providers', label: this.t('settings_page.tab_ai_providers') },
            { id: 'security', label: this.t('settings_page.tab_security') },
            { id: 'integrations', label: this.t('settings_page.tab_integrations') },
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

    _renderCompanyTab(company) {
        const saving = this._update.busy;
        return html`
            <div class="two-col">
                <section>
                    <h3>${this.t('settings_page.section_company')}</h3>
                    <div class="info-grid">
                        <dt>${this.t('settings_page.company_id')}</dt><dd>${company.company_id || ''}</dd>
                        <dt>${this.t('settings_page.company_status')}</dt><dd>${company.status || ''}</dd>
                        <dt>${this.t('settings_page.company_owner')}</dt><dd>${company.owner_user_id ? html`<platform-user-chip user-id=${company.owner_user_id} size="sm"></platform-user-chip>` : ''}</dd>
                        <dt>${this.t('settings_page.tariff_plan')}</dt><dd>${company.tariff_plan || ''}</dd>
                        <dt>${this.t('settings_page.created_at')}</dt><dd>${company.created_at ? new Date(company.created_at).toLocaleString() : ''}</dd>
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
                            @change=${(e) => {
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
                            .value=${company.subdomain || ''}
                        ></platform-field>
                        <platform-field
                            type="integer"
                            mode="edit"
                            label=${this.t('settings_page.label_monthly_budget')}
                            .value=${this._monthlyBudget}
                            @change=${(e) => {
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
                        @change=${(e) => {
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

    _capabilityDraft(cap) {
        return this._capabilityDrafts[cap.capability] || {
            provider: cap.provider || (cap.platform_default_provider || ''),
            api_key: '',
            base_url: cap.base_url || '',
            model: cap.model || '',
        };
    }

    _onCapabilityChange(capName, e) {
        if (!e.detail || !e.detail.config) return;
        this._capabilityDrafts = {
            ...this._capabilityDrafts,
            [capName]: { ...e.detail.config },
        };
    }

    _saveCapability(capability) {
        const draft = this._capabilityDrafts[capability];
        if (!draft || !draft.provider) {
            return;
        }
        const body = { capability, provider: draft.provider };
        if (draft.api_key) body.api_key = draft.api_key;
        if (draft.base_url) body.base_url = draft.base_url;
        if (draft.model) body.model = draft.model;
        if (draft.folder_id) body.folder_id = draft.folder_id;
        if (draft.extra_request_headers) body.extra_request_headers = draft.extra_request_headers;
        if (Array.isArray(draft.fallback_models) && draft.fallback_models.length > 0) {
            body.fallback_models = draft.fallback_models;
        }
        this._capPut.run(body);
    }

    _clearCapability(capability) {
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

    _renderLlmContextCard(data) {
        const info = data && typeof data === 'object' && data.llm_context && typeof data.llm_context === 'object'
            ? data.llm_context
            : {};
        const configured = info.configured === true;
        return html`
            <section>
                <h3>${this.t('settings_page.ai_providers.section_context')}</h3>
                <div class="section-help">${this.t('settings_page.ai_providers.section_context_help')}</div>
                <div class="context-card">
                    <platform-llm-context-editor
                        .config=${this._llmContextDraft}
                        .profiles=${Array.isArray(info.profiles) ? info.profiles : []}
                        .budgets=${Array.isArray(info.budgets) ? info.budgets : []}
                        .clearable=${configured || Object.keys(this._llmContextDraft || {}).length > 0}
                        @change=${(e) => {
                            const cfg = e.detail && e.detail.config && typeof e.detail.config === 'object'
                                ? e.detail.config
                                : {};
                            this._llmContextDraft = { ...cfg };
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

    _renderCapabilityCard(cap, catalog) {
        const draft = this._capabilityDraft(cap);
        const providerCatalog = catalog[cap.capability] || [];
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
                    .platformModel=${cap.platform_default_model || ''}
                    .costOrigin=${cap.configured ? (draft.api_key || draft.base_url || (draft.provider || '').startsWith('custom:') ? 'company' : 'platform') : null}
                    .keyMasked=${cap.key_masked || null}
                    .clearable=${cap.configured}
                    @change=${(e) => this._onCapabilityChange(cap.capability, e)}
                    @clear-override=${() => this._clearCapability(cap.capability)}
                ></platform-llm-config-editor>
                <div class="actions">
                    <glass-button size="sm" @click=${() => this._saveCapability(cap.capability)}>
                        ${this.t('settings_page.ai_providers.save_capability')}
                    </glass-button>
                </div>
            </div>
        `;
    }

    _normalizeCustomProviderRow(raw) {
        if (!raw || typeof raw !== 'object') {
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

    _openCustomProviderEdit(raw) {
        const row = this._normalizeCustomProviderRow(raw);
        this.openModal('frontend.ai_custom_provider_create', { initialProvider: row });
    }

    _renderAiProvidersTab() {
        const data = this._aiLoad.lastResult;
        if (!data) {
            return html`<div class="empty"><glass-spinner></glass-spinner></div>`;
        }
        const capabilities = data.capabilities || [];
        const customProviders = data.custom_providers || [];
        const catalog = data.catalog || {};
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
                    ? html`<div class="empty">${this.t('settings_page.ai_providers.no_custom_providers')}</div>`
                    : html`
                          <div class="custom-provider-list">
                              ${customProviders.map((raw) => {
                                  const p = this._normalizeCustomProviderRow(raw);
                                  const title = p.label || p.id || '—';
                                  const ref = p.id ? `custom:${p.id}` : '—';
                                  const url = p.base_url || '—';
                                  const caps = p.capabilities.length ? p.capabilities.join(', ') : '—';
                                  const km = p.key_masked || '—';
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
                                                            @click=${() => this._customDelete.run({ id: p.id })}
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
                    ${capabilities.map((cap) => this._renderCapabilityCard(cap, catalog))}
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
                    <div class="empty">${this.t('settings_page.sessions_placeholder')}</div>
                </section>
                <section>
                    <h3>${this.t('settings_page.oauth_title')}</h3>
                    <div class="section-help">${this.t('settings_page.oauth_info')}</div>
                    <div class="empty">—</div>
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

    render() {
        const company = this._load.lastResult;
        if (!company) {
            return html`
                <page-header title=${this.t('settings_page.title')}></page-header>
                <div class="page-body">
                <div class="empty"><glass-spinner></glass-spinner></div>
                </div>
            `;
        }
        return html`
            <page-header title=${this.t('settings_page.title')}></page-header>
            <div class="page-body">
            ${this._renderTabs()}
            ${this._activeTab === 'company' ? this._renderCompanyTab(company) : ''}
            ${this._activeTab === 'ai_providers' ? this._renderAiProvidersTab() : ''}
            ${this._activeTab === 'security' ? this._renderSecurityTab() : ''}
            ${this._activeTab === 'integrations' ? this._renderIntegrationsTab() : ''}
            </div>
        `;
    }
}

customElements.define('frontend-settings-page', FrontendSettingsPage);
