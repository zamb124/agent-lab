/**
 * Навигация публичного сайта на узком экране.
 *
 * kind: 'wiki.public_tree'
 *
 * Дерево грузит страница сайта — у неё уже есть токен и выбранный узел, поэтому
 * лист получает готовые узлы и возвращает выбор наружу.
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '@platform/lib/components/platform-tree.js';

export class WikiPublicTreeSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'wiki.public_tree';
    static i18nNamespace = 'wiki';

    static properties = {
        ...PlatformBottomSheet.properties,
        /** Узлы `platform-tree`, собранные страницей сайта. */
        nodes: { attribute: false },
        selectedId: { attribute: false },
        /** `(wikiPageId: string) => void` — переход делает страница. */
        onSelect: { attribute: false },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            platform-tree {
                display: block;
                width: 100%;
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
        this.nodes = [];
        this.selectedId = '';
        this.onSelect = null;
        this.snap = 'full';
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('public.site_nav');
    }

    _onSelect(event) {
        if (typeof this.onSelect !== 'function') {
            throw new Error('wiki-public-tree-sheet: требуется onSelect');
        }
        this.onSelect(event.detail.id);
        this.close();
    }

    renderBody() {
        if (this.nodes.length === 0) {
            return html`<div class="empty">${this.t('sidebar.empty')}</div>`;
        }
        return html`
            <platform-tree
                .nodes=${this.nodes}
                selected-id=${this.selectedId}
                aria-label=${this.t('public.site_nav')}
                @tree-select=${this._onSelect}
            ></platform-tree>
        `;
    }
}

customElements.define('wiki-public-tree-sheet', WikiPublicTreeSheet);
registerBottomSheetKind(WikiPublicTreeSheet.bottomSheetKind, 'wiki-public-tree-sheet');
