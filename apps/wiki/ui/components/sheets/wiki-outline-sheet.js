/**
 * Оглавление страницы на узком экране.
 *
 * kind: 'wiki.outline'
 *
 * Заголовки приходят из открытого редактора: на мобиле правая колонка скрыта,
 * а оглавление остаётся главным способом перемещаться по длинной странице.
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';

export class WikiOutlineSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'wiki.outline';
    static i18nNamespace = 'wiki';

    static properties = {
        ...PlatformBottomSheet.properties,
        /** `{ level, text, pos }[]` из `platform-rich-editor.getOutline()`. */
        outline: { attribute: false },
        /** `(pos: number) => void` — прокрутка на стороне страницы. */
        onPick: { attribute: false },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            .item {
                display: block;
                width: 100%;
                padding: var(--space-2) 0;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-family: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }

            .item:hover {
                color: var(--wiki-accent);
            }

            .empty {
                padding: var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.outline = [];
        this.onPick = null;
        this.snap = 'half';
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('page.outline');
    }

    _onPick(pos) {
        if (typeof this.onPick !== 'function') {
            throw new Error('wiki-outline-sheet: требуется onPick');
        }
        this.onPick(pos);
        this.close();
    }

    renderBody() {
        if (this.outline.length === 0) {
            return html`<div class="empty">${this.t('page.outline_empty')}</div>`;
        }
        return html`
            ${this.outline.map((item) => html`
                <button
                    class="item"
                    type="button"
                    data-wiki-outline-pos=${item.pos}
                    style=${`padding-left:${(item.level - 1) * 12}px`}
                    @click=${() => this._onPick(item.pos)}
                >${item.text}</button>
            `)}
        `;
    }
}

customElements.define('wiki-outline-sheet', WikiOutlineSheet);
registerBottomSheetKind(WikiOutlineSheet.bottomSheetKind, 'wiki-outline-sheet');
