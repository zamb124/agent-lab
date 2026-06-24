/**
 * office-file-actions-menu — kebab-меню действий над документом.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class OfficeFileActionsMenu extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        menuOpen: { type: Boolean, attribute: 'menu-open', reflect: true },
    };

    static styles = [
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
                z-index: var(--z-popover, 1100);
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
            .item.danger {
                color: var(--danger);
            }
        `,
    ];

    constructor() {
        super();
        this.menuOpen = false;
        this._onDocClick = this._onDocClick.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocClick, true);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onDocClick, true);
    }

    _onDocClick(e) {
        if (!this.menuOpen) return;
        const path = e.composedPath();
        if (path.includes(this)) return;
        this.menuOpen = false;
    }

    _toggle(e) {
        e.stopPropagation();
        this.menuOpen = !this.menuOpen;
    }

    _emit(action) {
        this.menuOpen = false;
        this.emit('action', { action });
    }

    render() {
        return html`
            <button class="trigger" type="button" title=${this.t('list.colActions')} @click=${this._toggle}>
                <platform-icon name="more-vert" size="16"></platform-icon>
            </button>
            ${this.menuOpen ? html`
                <div class="menu" role="menu" @click=${(e) => e.stopPropagation()}>
                    <button class="item" type="button" role="menuitem" @click=${() => this._emit('open')}>
                        <platform-icon name="external-link" size="14"></platform-icon>
                        ${this.t('list.open')}
                    </button>
                    <button class="item" type="button" role="menuitem" @click=${() => this._emit('rename')}>
                        <platform-icon name="edit" size="14"></platform-icon>
                        ${this.t('list.rename')}
                    </button>
                    <button class="item" type="button" role="menuitem" @click=${() => this._emit('share')}>
                        <platform-icon name="link" size="14"></platform-icon>
                        ${this.t('access.menuShare')}
                    </button>
                    <button class="item danger" type="button" role="menuitem" @click=${() => this._emit('delete')}>
                        <platform-icon name="trash" size="14"></platform-icon>
                        ${this.t('list.delete')}
                    </button>
                </div>
            ` : ''}
        `;
    }
}

customElements.define('office-file-actions-menu', OfficeFileActionsMenu);
