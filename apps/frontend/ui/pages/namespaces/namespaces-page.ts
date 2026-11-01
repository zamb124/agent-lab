/**
 * Console namespaces page — admin list of company_workspace + personal.
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-user-chip.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { ResourceController } from '@platform/lib/base/use-resource.js';

const FACTORY = 'frontend/namespaces';

export class FrontendNamespacesPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        frontendIslandPageBodyStyles,
        css`
            :host { display: block; }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: flex-end;
                margin-bottom: var(--space-4);
            }
            .filters {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                margin-bottom: var(--space-3);
            }
            .filter-tag {
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .filter-tag[aria-pressed="true"] {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            .grid {
                display: grid;
                gap: var(--space-3);
            }
            .card {
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .card-title {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }
            .meta {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: center;
            }
            .kind {
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .crm-link {
                color: var(--accent);
                text-decoration: none;
                font-size: var(--text-sm);
            }
            .crm-link:hover {
                text-decoration: underline;
            }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    static override properties: PropertyDeclarations = {
        _kindFilter: { state: true },
    }
    declare _kindFilter: string;
;

    constructor() {
        super();
        this._kindFilter = 'all';
    }
    private _namespaces!: ResourceController;


    override connectedCallback(): void {
        super.connectedCallback();
        this._namespaces = this.useResource(FACTORY, { autoload: true });
    }

    _setFilter(kind: string) {
        this._kindFilter = kind;
        const query = kind === 'all' ? { limit: 200, offset: 0 } : { limit: 200, offset: 0, kind };
        this._namespaces.load(query);
    }

    _items() {
        const rawItems = this._namespaces.items;
        const items = Array.isArray(rawItems) ? rawItems : [];
        if (this._kindFilter === 'all') return items;
        return items.filter((item) => item.kind === this._kindFilter);
    }

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        const loading = Boolean(this._namespaces?.loading);
        const items = this._items();

        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                title=${t('namespaces_page.title')}
                subtitle=${t('namespaces_page.subtitle')}
            >
                <button
                    slot="actions"
                    class="btn btn-primary"
                    type="button"
                    @click=${() => this.openModal('frontend.namespace_create')}
                >
                    <platform-icon name="plus" size="16"></platform-icon>
                    ${t('namespaces_page.create')}
                </button>
            </page-header>

            <div class="filters">
                ${['all', 'company_workspace', 'personal'].map((kind) => html`
                    <button
                        type="button"
                        class="filter-tag"
                        aria-pressed=${this._kindFilter === kind ? 'true' : 'false'}
                        @click=${() => this._setFilter(kind)}
                    >${t(`namespaces_page.filter_${kind}`)}</button>
                `)}
            </div>

            ${loading
                ? html`<platform-empty-state loading></platform-empty-state>`
                : items.length === 0
                  ? html`<platform-empty-state icon="folder" title=${t('namespaces_page.empty')}></platform-empty-state>`
                  : nothing}

            <div class="grid">
                ${items.map((item) => html`
                    <div class="card">
                        <div class="card-title">${item.description || item.name}</div>
                        <div class="meta">
                            <span class="kind">${item.kind}</span>
                            <span>${item.name}</span>
                            ${item.owner_user_id ? html`
                                <platform-user-chip .userId=${item.owner_user_id}></platform-user-chip>
                            ` : nothing}
                            ${item.is_default ? html`<span>${t('namespaces_page.default')}</span>` : nothing}
                            ${item.kind === 'company_workspace' ? html`
                                <a
                                    class="crm-link"
                                    href=${`/crm/namespaces/${encodeURIComponent(item.name)}`}
                                >${t('namespaces_page.open_crm')}</a>
                            ` : nothing}
                        </div>
                    </div>
                `)}
            </div>
        `;
    }
}

customElements.define('frontend-namespaces-page', FrontendNamespacesPage);
