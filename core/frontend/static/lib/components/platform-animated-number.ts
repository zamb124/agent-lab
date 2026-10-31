/**
 * platform-animated-number — плавная смена числового значения.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';

const DEFAULT_DURATION_MS = 400;

function _easeOutCubic(t: number): number {
    return 1 - ((1 - t) ** 3);
}

export class PlatformAnimatedNumber extends PlatformElement {
    static override properties: PropertyDeclarations = {
        value: { type: Number },
        locale: { type: String },
        durationMs: { type: Number },
        maximumFractionDigits: { type: Number },
    };

    declare value: number;
    declare locale: string;
    declare durationMs: number;
    declare maximumFractionDigits: number;

    _displayValue: number;
    _animationFrameId: number | null;
    _animationStartMs: number;
    _animationFrom: number;
    _animationTo: number;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
                font-variant-numeric: tabular-nums;
            }
            .value {
                display: inline-block;
                transition: opacity var(--motion-duration-micro) var(--motion-ease-standard);
            }
            .value.animating {
                opacity: 0.92;
            }
        `,
    ];

    constructor() {
        super();
        this.value = 0;
        this.locale = 'en';
        this.durationMs = DEFAULT_DURATION_MS;
        this.maximumFractionDigits = 0;
        this._displayValue = 0;
        this._animationFrameId = null;
        this._animationStartMs = 0;
        this._animationFrom = 0;
        this._animationTo = 0;
    }

    override disconnectedCallback(): void {
        this._cancelAnimation();
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('value')) {
            this._animateTo(this.value);
        }
    }

    override firstUpdated(): void {
        this._displayValue = this.value;
    }

    _cancelAnimation(): void {
        if (this._animationFrameId !== null) {
            window.cancelAnimationFrame(this._animationFrameId);
            this._animationFrameId = null;
        }
    }

    _animateTo(nextValue: number): void {
        if (typeof nextValue !== 'number' || !Number.isFinite(nextValue)) {
            throw new Error('platform-animated-number: value must be finite number');
        }
        this._cancelAnimation();
        this._animationFrom = this._displayValue;
        this._animationTo = nextValue;
        if (this._animationFrom === this._animationTo) {
            return;
        }
        this._animationStartMs = performance.now();
        const step = (now: number): void => {
            const elapsed = now - this._animationStartMs;
            const progress = Math.min(elapsed / this.durationMs, 1);
            const eased = _easeOutCubic(progress);
            this._displayValue = this._animationFrom + ((this._animationTo - this._animationFrom) * eased);
            this.requestUpdate();
            if (progress < 1) {
                this._animationFrameId = window.requestAnimationFrame(step);
            } else {
                this._displayValue = this._animationTo;
                this._animationFrameId = null;
                this.requestUpdate();
            }
        };
        this._animationFrameId = window.requestAnimationFrame(step);
    }

    _formattedValue(): string {
        return formatPlatformNumber(Math.round(this._displayValue), this.locale, {
            maximumFractionDigits: this.maximumFractionDigits,
        });
    }

    override render(): TemplateResult {
        const animating = this._animationFrameId !== null;
        return html`
            <span class="value ${animating ? 'animating' : ''}">${this._formattedValue()}</span>
        `;
    }
}

customElements.define('platform-animated-number', PlatformAnimatedNumber);
