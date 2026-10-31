/**
 * CRMNamespacesPage — страница со всеми namespace компании.
 *
 * Маршрут: `/crm/namespaces` (parent: `settings`).
 *
 * Источники данных:
 *   - useResource('crm/namespaces', { autoload: true }) — список namespace.
 *
 * UI: page-header + кнопка «Создать пространство» → modal `crm.namespace`
 * (mode='create'); сетка карточек namespace с кнопками:
 *   - «Настройки» → navigate('namespace', { itemId: name }) — отдельная страница
 *     `namespace-detail-page` с полным редактированием namespace и его типов.
 *   - «Открыть» → setPlatformNamespaceSelection + navigate('notes').
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { setPlatformNamespaceSelection } from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import type {
    CSSResultGroup,
    TemplateResult,
} from 'lit';
import type {
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';

const NAMESPACES_NAME = 'crm/namespaces';

const CRM_INTEGRATION_ICON_BASE = '/crm/ui/static/assets/integrations';

/** URL круглой иконки провайдера; файл обязателен: assets/integrations/{provider_id}.svg */
function crmIntegrationIconHref(providerId: unknown): string {
    if (typeof providerId !== 'string' || providerId.length === 0) {
        throw new Error('crmIntegrationIconHref: providerId required');
    }
    return `${CRM_INTEGRATION_ICON_BASE}/${encodeURIComponent(providerId)}.svg`;
}

export class CRMNamespacesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .header-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
            }

            .toolbar {
                display: flex;
                gap: var(--space-2);
                padding: 0 var(--space-4) var(--space-3);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 0 var(--space-4) var(--space-4);
                overflow-y: auto;
            }

            platform-empty-state { margin-top: var(--space-8); }

            .grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            }

            .card {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface);
            }
            .card-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .card-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                margin: 0;
                flex: 1;
                min-width: 0;
            }
            .card-integrations {
                display: flex;
                flex-wrap: wrap;
                justify-content: flex-end;
                gap: 6px;
                flex-shrink: 0;
            }
            .integration-icon-wrap {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                overflow: hidden;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
            }
            .integration-icon {
                width: 70%;
                height: 70%;
                object-fit: contain;
                display: block;
            }
            .card-name {
                font-family: var(--font-mono);
                color: var(--text-primary);
            }
            .card-description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                white-space: pre-wrap;
                min-height: 1.4em;
            }
            .card-empty-description {
                color: var(--text-tertiary);
                font-style: italic;
            }
            .card-actions {
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
                margin-top: var(--space-2);
            }
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:not(.btn-primary):not(.btn-danger):hover { background: var(--crm-surface-muted); color: var(--text-primary); }
            .btn-primary {
                background: var(--accent);
                border-color: var(--accent);
                color: var(--platform-btn-primary-text);
            }
            .btn-primary:hover { filter: brightness(1.05); color: var(--platform-btn-primary-text); }
        `,
    ];

    private _namespaces: ResourceController;
    private _authSel: SelectController<AuthUser | null>;

    constructor() {
        super();
        this._namespaces = this.useResource(NAMESPACES_NAME, { autoload: true });
        this._authSel = this.select((s) => s.auth.user);
    }

    _onCreate() {
        this.openModal('crm.namespace', { mode: 'create' });
    }

    _onEdit(name: string) {
        this.navigate('namespace', { itemId: name });
    }

    _onOpenNamespace(name: string) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMNamespacesPage._onOpenNamespace: company_id required');
        }
        setPlatformNamespaceSelection(user.company_id, name);
        this.navigate('notes');
    }

    _connectedIntegrationBadges(ns: Record<string, unknown>) {
        const raw = ns.integration_badges;
        if (!Array.isArray(raw)) {
            throw new Error('CRMNamespacesPage: integration_badges required');
        }
        return raw.filter(
            (b) =>
                b
                && b.connected === true
                && typeof b.provider_id === 'string'
                && b.provider_id.length > 0,
        );
    }

    override render(): TemplateResult {
        const items = this._namespaces.items;
        const loading = this._namespaces.loading && items.length === 0;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${this.t('namespaces_page.title')}
                    subtitle=${this.t('namespaces_page.subtitle')}
                ></page-header>
            </div>
            <div class="toolbar">
                <button type="button" class="btn btn-primary" @click=${() => this._onCreate()}>
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this.t('namespaces_page.action_create')}
                </button>
            </div>
            <div class="body">
                ${loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                        ? html`<platform-empty-state
                            icon="folder"
                            title=${this.t('namespaces_page.empty_message')}
                        ></platform-empty-state>`
                        : html`
                            <div class="grid">
                                ${items.map((ns) => this._renderCard(ns))}
                            </div>
                        `}
            </div>
        `;
    }

    _renderCard(ns: Record<string, unknown>): TemplateResult {
        const description = typeof ns.description === 'string' && ns.description.length > 0
            ? ns.description
            : '';
        const badges = this._connectedIntegrationBadges(ns);
        const nsName = typeof ns.name === 'string' ? ns.name : '';
        return html`
            <article class="card">
                <div class="card-header">
                    <h3 class="card-title">
                        <platform-icon name="folder" size="14"></platform-icon>
                        <span class="card-name">${nsName}</span>
                    </h3>
                    ${badges.length > 0
                        ? html`
                            <div
                                class="card-integrations"
                                aria-label=${this.t('namespaces_page.integrations_connected')}
                            >
                                ${badges.map(
                                    (b) => html`
                                        <span class="integration-icon-wrap" title=${b.provider_id}>
                                            <img
                                                class="integration-icon"
                                                src=${crmIntegrationIconHref(b.provider_id)}
                                                alt=""
                                                loading="lazy"
                                                decoding="async"
                                            />
                                        </span>
                                    `,
                                )}
                            </div>
                        `
                        : nothing}
                </div>
                ${description.length > 0
                    ? html`<p class="card-description">${description}</p>`
                    : html`<p class="card-description card-empty-description">${this.t('namespaces_page.empty_description')}</p>`}
                <div class="card-actions">
                    <button type="button" class="btn btn-primary" @click=${() => this._onEdit(nsName)}>
                        <platform-icon name="settings" size="12"></platform-icon>
                        ${this.t('namespaces_page.action_settings')}
                    </button>
                    <button type="button" class="btn" @click=${() => this._onOpenNamespace(nsName)}>
                        <platform-icon name="arrow-right" size="12"></platform-icon>
                        ${this.t('namespaces_page.action_open')}
                    </button>
                </div>
            </article>
        `;
    }
}

customElements.define('crm-namespaces-page', CRMNamespacesPage);
