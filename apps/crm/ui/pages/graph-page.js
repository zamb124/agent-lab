/**
 * GraphPage — маршрут единого graph workspace (3D и mind map).
 *
 * Host растягивается на весь слот `platform-island` (flex column, height:100%),
 * иначе на мобильном workspace схлопывается до `min-height` своих внутренних блоков.
 */

import { html, css } from 'lit';
import { CRMNamespacePage } from '../base/crm-namespace-page.js';
import '../components/crm-graph-workspace.js';

export class CRMGraphPage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static styles = [
        ...CRMNamespacePage.styles,
        css`
            :host {
                display: flex;
                flex: 1 1 auto;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
            }
            crm-graph-workspace {
                flex: 1 1 auto;
                min-height: 0;
                width: 100%;
            }
        `,
    ];

    render() {
        return html`<crm-graph-workspace></crm-graph-workspace>`;
    }
}

customElements.define('crm-graph-page', CRMGraphPage);
