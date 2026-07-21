/**
 * Сегмент выбора языка isolated code runners.
 * Brand-логотипы через iconSrc на platform-segmented-control (img + iconFallback).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-segmented-control.js';
import {
    flowCodeLanguageSegmentItems,
    normalizeFlowCodeLanguage,
} from '../../_helpers/flows-code-languages.js';

export class FlowsCodeLanguageSegment extends PlatformElement {
    static properties = {
        value: { type: String },
        density: { type: String },
        fullWidth: { type: Boolean, attribute: 'full-width', reflect: true },
        ariaLabel: { type: String, attribute: 'aria-label' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                max-width: 100%;
                min-width: 0;
            }
            :host([full-width]) {
                display: flex;
                width: 100%;
            }
            platform-segmented-control {
                max-width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.value = 'python';
        this.density = 'compact';
        this.fullWidth = false;
        this.ariaLabel = '';
    }

    _onChange(e) {
        const next = normalizeFlowCodeLanguage(e.detail.value);
        this.value = next;
        this.emit('change', { value: next });
    }

    render() {
        const current = normalizeFlowCodeLanguage(this.value);
        return html`
            <platform-segmented-control
                icon-only
                density=${this.density}
                ?full-width=${this.fullWidth}
                .value=${current}
                .items=${flowCodeLanguageSegmentItems({ iconOnly: true })}
                aria-label=${this.ariaLabel}
                @change=${this._onChange}
            ></platform-segmented-control>
        `;
    }
}

customElements.define('flows-code-language-segment', FlowsCodeLanguageSegment);
