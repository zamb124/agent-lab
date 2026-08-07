import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { buildFlowUIDataFlowMarks, flowUIBindingScope } from './data-flow-marks.js';
import { flowUIEditorChromeTokens } from './editor-chrome.styles.js';

export { buildFlowUIDataFlowMarks, flowUIBindingScope };

/**
 * Data-flow overlay: shows which components carry data and where it goes.
 *
 * Scopes are colour-coded so a flow developer reads a screen at a glance:
 *  - `input`  — user value that the flow receives (`/values/**` → `@state:ui_values.*`);
 *  - `content` — author data rendered on the screen (`/content/**`);
 *  - `system` — runtime projection (`/system/**`, tasks/agent);
 *  - `submit` — the control that starts a flow turn (`platform.ui.submit`).
 *
 * The overlay lives outside the production iframe and never mutates it.
 */
export class FlowUIDataFlowOverlay extends LitElement {
    static properties = {
        visible: { type: Boolean },
        bindings: { attribute: false },
    };

    static styles = [
        flowUIEditorChromeTokens,
        css`
        :host {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 18;
        }
        .mark {
            position: absolute;
            box-sizing: border-box;
            border-radius: 4px;
            border: 1px solid var(--accent);
            background: color-mix(in srgb, var(--accent) 8%, transparent);
        }
        .mark[data-scope='content'] {
            border-color: var(--info);
            background: color-mix(in srgb, var(--info) 8%, transparent);
        }
        .mark[data-scope='system'] {
            border-color: var(--warning);
            background: color-mix(in srgb, var(--warning) 8%, transparent);
            border-style: dashed;
        }
        .mark[data-scope='submit'] {
            border-color: var(--success);
            background: color-mix(in srgb, var(--success) 8%, transparent);
        }
        .tag {
            position: absolute;
            left: 0;
            bottom: 100%;
            max-width: 100%;
            padding: 1px 5px;
            border-radius: 3px 3px 0 0;
            background: var(--accent);
            color: var(--text-on-accent);
            font: 600 9px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .mark[data-scope='content'] .tag {
            background: var(--info);
            color: var(--text-on-accent);
        }
        .mark[data-scope='system'] .tag {
            background: var(--warning);
            color: var(--text-inverse);
        }
        .mark[data-scope='submit'] .tag {
            background: var(--success);
            color: var(--text-on-accent);
        }
    `];

    constructor() {
        super();
        this.visible = false;
        this.bindings = [];
    }

    render() {
        if (this.visible !== true) return nothing;
        const items = Array.isArray(this.bindings) ? this.bindings : [];
        return html`${items.map((item) => html`
            <div
                class="mark"
                data-scope=${item.scope}
                style=${`left:${item.rect.x}px;top:${item.rect.y}px;width:${item.rect.width}px;height:${item.rect.height}px`}
            >
                <span class="tag">${item.tag}</span>
            </div>
        `)}`;
    }
}

if (!customElements.get('flow-ui-data-flow-overlay')) {
    customElements.define('flow-ui-data-flow-overlay', FlowUIDataFlowOverlay);
}
