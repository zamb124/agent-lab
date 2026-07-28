/**
 * Боковая панель страницы на узком экране.
 *
 * kind: 'wiki.outline'
 *
 * Лист — второй хозяин `<wiki-page-panel>`: на мобиле правая колонка скрыта, а
 * оглавление, ссылки, комментарии и история нужны те же самые. Прокрутку к
 * заголовку делает страница, поэтому цель оглавления уходит наружу через `onPick`.
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '../wiki-page-panel.js';

export class WikiOutlineSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'wiki.outline';
    static i18nNamespace = 'wiki';

    static properties = {
        ...PlatformBottomSheet.properties,
        pageId: { attribute: false },
        /** Активная вкладка панели — та же, что на широком экране. */
        tab: { attribute: false },
        /** `{ level, text, pos }[]` из `platform-rich-editor.getOutline()`. */
        outline: { attribute: false },
        /** `(pos: number) => void` — прокрутка на стороне страницы. */
        onPick: { attribute: false },
        /** `(tab: string) => void` — страница запоминает выбранную вкладку. */
        onTabChange: { attribute: false },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            wiki-page-panel {
                max-height: 60vh;
            }
        `,
    ];

    constructor() {
        super();
        this.pageId = '';
        this.tab = 'outline';
        this.outline = [];
        this.onPick = null;
        this.onTabChange = null;
        this.snap = 'half';
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('panel.title');
    }

    _onPick(event) {
        if (typeof this.onPick !== 'function') {
            throw new Error('wiki-outline-sheet: требуется onPick');
        }
        this.onPick(event.detail);
        this.close();
    }

    _onTabChange(event) {
        if (typeof this.onTabChange !== 'function') {
            throw new Error('wiki-outline-sheet: требуется onTabChange');
        }
        this.tab = event.detail.tab;
        this.onTabChange(this.tab);
    }

    renderBody() {
        return html`
            <wiki-page-panel
                embedded
                page-id=${this.pageId}
                tab=${this.tab}
                .outline=${this.outline}
                @outline-pick=${this._onPick}
                @panel-tab-change=${this._onTabChange}
            ></wiki-page-panel>
        `;
    }
}

customElements.define('wiki-outline-sheet', WikiOutlineSheet);
registerBottomSheetKind(WikiOutlineSheet.bottomSheetKind, 'wiki-outline-sheet');
