/**
 * FlowsListPage — обёртка над `<flows-sidebar>`. Используется как левая
 * колонка для маршрутов flow_chat / list. На отдельном «маршруте списка»
 * рендерится вместе с `<flows-empty-state>`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class FlowsListPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: contents;
            }
        `,
    ];

    render() {
        return html`<flows-sidebar></flows-sidebar>`;
    }
}

customElements.define('flows-list-page', FlowsListPage);
