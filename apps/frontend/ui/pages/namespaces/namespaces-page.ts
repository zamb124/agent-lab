/**
 * Console namespaces page — admin list of company_workspace + personal.
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-user-chip.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { ResourceController, FormController} from '@platform/lib/base/use-resource.js';

const FACTORY = 'frontend/namespaces';
const FORM = 'frontend/namespace_create_form';

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
            .create-panel {
                margin-bottom: var(--space-4);
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                display: grid;
                gap: var(--space-3);
                max-width: 32rem;
            }
            .actions {
                display: flex;
                gap: var(--space-2);
            }
            .crm-link {
                color: var(--accent);
                text-decoration: none;
                font-size: var(--text-sm);
            }
            .crm-link:hover {
                text-decoration: underline;
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        _kindFilter: { state: true },
        _showCreate: { state: true },
    }
    declare _kindFilter: string;
    declare _showCreate: boolean;
;

    constructor() {
        super();
        this._kindFilter = 'all';
        this._showCreate = false;
    }
    private _namespaces!: ResourceController;
    private _form!: FormController;


    override connectedCallback(): void {
        super.connectedCallback();
        this._namespaces = this.useResource(FACTORY, { autoload: true });
        this._form = this.useForm(FORM);
        this.useEvent(this._namespaces.resource.events.CREATED, () => {
            this._showCreate = false;
        });
    }

    _setFilter(kind: string) {
        this._kindFilter = kind;
        const query = kind === 'all' ? { limit: 200, offset: 0 } : { limit: 200, offset: 0, kind };
        this._namespaces.load(query);
    }

    _items() {
        const items = Array.isArray(this._namespaces?.items) ? (this._namespaces!.items as Array<Record<string, any>>) : [];
        if (this._kindFilter === 'all') return items;
        return items.filter((item) => item.kind === this._kindFilter);
    }

    _submitCreate(event: Event) {
        event.preventDefault();
        this._form.submit();
    }

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        const loading = Boolean(this._namespaces?.loading);
        const items = this._items();
        const draft = this._form?.draft ?? { name: '', description: '' };

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
                    @click=${() => { this._showCreate = !this._showCreate; }}
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

            ${this._showCreate ? html`
                <form class="create-panel" @submit=${this._submitCreate}>
                    <platform-field
                        type="string"
                        mode="edit"
                        name="name"
                        label=${t('namespaces_page.field_name')}
                        .value=${draft.name}
                        @change=${(e: CustomEvent) => this._form.setField('name', e.detail.value)}
                    ></platform-field>
                    <platform-field
                        type="text"
                        mode="edit"
                        name="description"
                        label=${t('namespaces_page.field_description')}
                        .value=${draft.description}
                        @change=${(e: CustomEvent) => this._form.setField('description', e.detail.value)}
                    ></platform-field>
                    <div class="actions">
                        <button class="btn btn-primary" type="submit" ?disabled=${this._form?.submitting}>
                            ${t('namespaces_page.save')}
                        </button>
                        <button class="btn" type="button" @click=${() => { this._showCreate = false; }}>
                            ${t('namespaces_page.cancel')}
                        </button>
                    </div>
                </form>
            ` : nothing}

            ${loading ? html`<glass-spinner></glass-spinner>` : nothing}

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
