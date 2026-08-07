import { LitElement, css, html } from '../../lit-shim.js';
import { flowUIEditorChromeTokens } from './editor-chrome.styles.js';

/**
 * The authoring grid as the author actually gets it: columns and baseline rows
 * are drawn from the same geometry the gesture commits with, positioned over the
 * real content box of the page grid — not over the whole artboard.
 */
export class FlowUILayoutGridOverlay extends LitElement {
    static properties = {
        geometry: { attribute: false },
        visible: { type: Boolean },
    };

    static styles = [
        flowUIEditorChromeTokens,
        css`
            :host {
                position: absolute;
                inset: 0;
                pointer-events: none;
                z-index: 10;
            }
            .col {
                position: absolute;
                background: var(--flow-ui-editor-grid-col);
                border-inline: 1px solid var(--flow-ui-editor-grid-edge);
                box-sizing: border-box;
            }
            .row-line {
                position: absolute;
                height: 1px;
                background: var(--flow-ui-editor-grid-row-edge);
            }
        `,
    ];

    constructor() {
        super();
        this.geometry = null;
        this.visible = false;
    }

    render() {
        const geometry = this.geometry;
        if (!this.visible || !geometry) return html``;
        const { contentRect, columns, columnStep, columnWidth, rowStep } = geometry;
        const rows = Math.max(
            geometry.rowTracks.length,
            Math.ceil(contentRect.height / rowStep),
            1,
        );
        return html`
            ${Array.from({ length: columns }, (_, index) => html`<div
                class="col"
                title=${`Column ${index + 1}`}
                style=${`left:${contentRect.x + index * columnStep}px;top:${contentRect.y}px;`
                    + `width:${columnWidth}px;height:${contentRect.height}px`}
            ></div>`)}
            ${Array.from({ length: rows }, (_, index) => html`<div
                class="row-line"
                style=${`left:${contentRect.x}px;top:${contentRect.y + geometry.rowOffset(index + 1)}px;`
                    + `width:${contentRect.width}px`}
            ></div>`)}
        `;
    }
}

if (!customElements.get('flow-ui-layout-grid-overlay')) {
    customElements.define('flow-ui-layout-grid-overlay', FlowUILayoutGridOverlay);
}
