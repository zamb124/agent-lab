/**
 * Выбор доски — Linear-style project switcher.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class WorktrackerBoardPicker extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        boards: { type: Array },
        activeBoardId: { type: String, attribute: 'active-board-id' },
        menuOpen: { type: Boolean, attribute: 'menu-open', reflect: true },
        loading: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: relative;
                display: inline-flex;
                min-width: 0;
            }
            .trigger {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                max-width: min(320px, 100%);
                padding: var(--space-1) var(--space-2);
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-tight);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .trigger:hover,
            :host([menu-open]) .trigger {
                background: var(--glass-solid-subtle);
                border-color: var(--glass-border-subtle);
            }
            .trigger-name {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .chevron {
                flex-shrink: 0;
                color: var(--text-tertiary);
            }
            .menu {
                position: absolute;
                top: calc(100% + 6px);
                left: 0;
                z-index: var(--z-popover, 1100);
                min-width: 220px;
                max-width: min(360px, 90vw);
                max-height: min(420px, 60vh);
                overflow-y: auto;
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
            .item.active {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .item.create {
                color: var(--text-secondary);
                border-top: 1px solid var(--glass-border-subtle);
                margin-top: var(--space-1);
                border-radius: 0 0 var(--radius-md) var(--radius-md);
            }
            .empty-label {
                padding: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.boards = [];
        this.activeBoardId = '';
        this.menuOpen = false;
        this.loading = false;
        this._onDocClick = this._onDocClick.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocClick);
    }

    disconnectedCallback() {
        document.removeEventListener('click', this._onDocClick);
        super.disconnectedCallback();
    }

    _onDocClick(event) {
        if (!this.menuOpen) {
            return;
        }
        const path = event.composedPath();
        if (path.includes(this)) {
            return;
        }
        this.menuOpen = false;
    }

    _activeBoard() {
        if (!Array.isArray(this.boards)) {
            return null;
        }
        return this.boards.find((board) => board.board_id === this.activeBoardId) || null;
    }

    _toggleOpen(event) {
        event.stopPropagation();
        this.menuOpen = !this.menuOpen;
    }

    _selectBoard(boardId, event) {
        event.stopPropagation();
        this.menuOpen = false;
        this.emit('board-select', { board_id: boardId });
    }

    _requestCreate(event) {
        event.stopPropagation();
        this.menuOpen = false;
        this.emit('create-board');
    }

    render() {
        const activeBoard = this._activeBoard();
        const label = activeBoard && typeof activeBoard.name === 'string'
            ? activeBoard.name
            : this.t('board_picker.placeholder');
        const boards = Array.isArray(this.boards) ? this.boards : [];

        return html`
            <button type="button" class="trigger" @click=${this._toggleOpen} ?disabled=${this.loading}>
                <platform-icon name="list-check" size="18"></platform-icon>
                <span class="trigger-name">${label}</span>
                <platform-icon class="chevron" name="chevron-down" size="16"></platform-icon>
            </button>
            ${this.menuOpen ? html`
                <div class="menu" @click=${(e) => e.stopPropagation()}>
                    ${boards.length === 0 ? html`
                        <div class="empty-label">${this.t('board_picker.empty')}</div>
                    ` : boards.map((board) => html`
                        <button
                            type="button"
                            class="item ${board.board_id === this.activeBoardId ? 'active' : ''}"
                            @click=${(e) => this._selectBoard(board.board_id, e)}
                        >
                            <platform-icon name="list-check" size="16"></platform-icon>
                            <span>${board.name}</span>
                        </button>
                    `)}
                    <button type="button" class="item create" @click=${this._requestCreate}>
                        <platform-icon name="plus" size="16"></platform-icon>
                        <span>${this.t('board_picker.create')}</span>
                    </button>
                </div>
            ` : null}
        `;
    }
}

customElements.define('worktracker-board-picker', WorktrackerBoardPicker);
