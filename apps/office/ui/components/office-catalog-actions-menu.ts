/**
 * office-catalog-actions-menu — kebab действий над каталогом в таблице/сетке.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class OfficeCatalogActionsMenu extends PlatformElement {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        menuOpen: { type: Boolean, attribute: 'menu-open', reflect: true },
        isOwner: { type: Boolean, attribute: 'is-owner', reflect: true },
        showMembers: { type: Boolean, attribute: 'show-members', reflect: true },
        canDelete: { type: Boolean, attribute: 'can-delete', reflect: true },
    }
    declare menuOpen: boolean;
    declare isOwner: boolean;
    declare showMembers: boolean;
    declare canDelete: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                position: relative;
                display: inline-flex;
            }
            .trigger {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 2rem;
                height: 2rem;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .trigger:hover,
            :host([menu-open]) .trigger {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .menu {
                position: absolute;
                top: calc(100% + 4px);
                right: 0;
                z-index: var(--platform-popover-z-index);
                min-width: 10rem;
                padding: var(--space-1);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
            }
            .item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .item:hover {
                background: var(--glass-solid-medium);
            }
            .item:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .item.danger {
                color: var(--error);
            }
        `,
    ];

    constructor() {
        super();
        this.menuOpen = false;
        this.isOwner = false;
        this.showMembers = false;
        this.canDelete = false;
        this._onDocClick = this._onDocClick.bind(this);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(document, 'click', this._onDocClick, true);
    }


    private _onDocClick(e: MouseEvent) {
        if (!this.menuOpen) return;
        const path = e.composedPath();
        if (path.includes(this)) return;
        this.menuOpen = false;
    }

    private _toggle(e: Event) {
        e.stopPropagation();
        this.menuOpen = !this.menuOpen;
    }

    private _emit(action: string) {
        this.menuOpen = false;
        this.emit('action', { action });
    }

    override render(): TemplateResult {
        return html`
            <button class="trigger" type="button" title=${this.t('list.colActions')} @click=${this._toggle}>
                <platform-icon name="more-vert" size="16"></platform-icon>
            </button>
            ${this.menuOpen ? html`
                <div class="menu" role="menu" @click=${(e: Event) => e.stopPropagation()}>
                    <button class="item" type="button" role="menuitem" @click=${() => this._emit('open')}>
                        <platform-icon name="folder" size="14"></platform-icon>
                        ${this.t('list.open')}
                    </button>
                    ${this.isOwner ? html`
                        <button class="item" type="button" role="menuitem" @click=${() => this._emit('edit')}>
                            <platform-icon name="edit" size="14"></platform-icon>
                            ${this.t('catalog_context_menu.edit')}
                        </button>
                        <button class="item" type="button" role="menuitem" @click=${() => this._emit('access')}>
                            <platform-icon name="link" size="14"></platform-icon>
                            ${this.t('catalog_context_menu.access')}
                        </button>
                    ` : ''}
                    ${this.showMembers ? html`
                        <button class="item" type="button" role="menuitem" @click=${() => this._emit('members')}>
                            <platform-icon name="users" size="14"></platform-icon>
                            ${this.t('catalogs.members')}
                        </button>
                    ` : ''}
                    ${this.isOwner ? html`
                        <button class="item" type="button" role="menuitem" @click=${() => this._emit('rag')}>
                            <platform-icon name="search" size="14"></platform-icon>
                            ${this.t('catalog_context_menu.rag')}
                        </button>
                    ` : ''}
                    <button class="item" type="button" role="menuitem" @click=${() => this._emit('create-subcatalog')}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('tree.newSubcatalog')}
                    </button>
                    ${this.isOwner ? html`
                        <button
                            class="item danger"
                            type="button"
                            role="menuitem"
                            ?disabled=${!this.canDelete}
                            @click=${() => { if (this.canDelete) this._emit('delete'); }}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                            ${this.t('catalog_context_menu.delete')}
                        </button>
                    ` : ''}
                </div>
            ` : ''}
        `;
    }
}

customElements.define('office-catalog-actions-menu', OfficeCatalogActionsMenu);
