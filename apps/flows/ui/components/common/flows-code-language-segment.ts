/**
 * Сегмент выбора языка isolated code runners.
 * Brand-логотипы через iconSrc на platform-segmented-control (img + iconFallback).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-segmented-control.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import {
    flowCodeLanguageSegmentItems,
    normalizeFlowCodeLanguage,
} from '../../_helpers/flows-code-languages.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';

export class FlowsCodeLanguageSegment extends PlatformElement {
    static override properties: PropertyDeclarations = {
        value: { type: String },
        density: { type: String },
        fullWidth: { type: Boolean, attribute: 'full-width', reflect: true },
        ariaLabel: { type: String, attribute: 'aria-label' },
    }
    declare value: string;
    declare density: string;
    declare fullWidth: boolean;
    declare ariaLabel: string;
;

    static override styles: CSSResultGroup = [
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

    _onChange(e: CustomEvent) {
        const detail = e.detail;
        if (!isPlainObject(detail)) {
            throw new Error('flows-code-language-segment: change detail required');
        }
        const next = normalizeFlowCodeLanguage(detail.value);
        this.value = next;
        this.emit('change', { value: next });
    }

    override render(): TemplateResult {
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
