/**
 * ``<flow-ui-drawer-controls>`` — кнопки drawer в topbar ``<platform-flow-ui>``: развернуть/свернуть
 * и закрыть. Между ними — slot (share-меню хоста). События ``drawer-expand-toggle``/``drawer-close``
 * хост переводит в ``flow-ui-drawer-expand-toggle``/``flow-ui-drawer-close`` для ``<flow-ui-drawer>``.
 */

import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';
import { chromeIconButtonStyles } from './chrome-icon-button.styles.js';

export class FlowUIDrawerControls extends LitElement {
    declare expanded: boolean;
    declare showExpand: boolean;
    declare locale: string;
    declare platformUiOrigin: string;

    static override properties = {
        expanded: { type: Boolean },
        showExpand: { type: Boolean, attribute: 'show-expand' },
        locale: { type: String },
        platformUiOrigin: { type: String, attribute: 'platform-ui-origin' },
    };

    static override styles = [chromeIconButtonStyles, css`:host { display: contents; }`];

    constructor() {
        super();
        this.expanded = false;
        this.showExpand = true;
        this.locale = 'auto';
        this.platformUiOrigin = '';
    }

    _button(label: string, glyph: string, eventName: string, pressed: unknown = nothing) {
        return html`<button type="button" class="chrome-icon-btn" aria-pressed=${pressed} aria-label=${label} title=${label}
            @click=${() => this.dispatchEvent(new CustomEvent(eventName, { bubbles: true, composed: true }))}>${flowUIGlyph(glyph, 18, this.platformUiOrigin)}</button>`;
    }

    override render() {
        const locale = resolveFlowUILocale(this.locale);
        const expandLabel = flowUIText(locale, this.expanded ? 'collapse_aria' : 'expand_aria');
        return html`${this.showExpand
            ? this._button(expandLabel, this.expanded ? 'minimize' : 'chevron-up', 'drawer-expand-toggle', this.expanded ? 'true' : 'false')
            : nothing}
        <slot></slot>
        ${this._button(flowUIText(locale, 'close_aria'), 'close', 'drawer-close')}`;
    }
}

if (!customElements.get('flow-ui-drawer-controls')) customElements.define('flow-ui-drawer-controls', FlowUIDrawerControls);
