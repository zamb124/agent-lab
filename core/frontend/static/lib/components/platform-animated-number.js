/**
 * platform-animated-number — плавная смена числового значения.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';

const DEFAULT_DURATION_MS = 400;

function _easeOutCubic(t) {
    return 1 - ((1 - t) ** 3);
}

export class PlatformAnimatedNumber extends PlatformElement {
    static properties = {
        value: { type: Number },
        locale: { type: String },
        durationMs: { type: Number },
        maximumFractionDigits: { type: Number },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
                font-variant-numeric: tabular-nums;
            }
            .value {
                display: inline-block;
                transition: opacity var(--duration-fast) var(--easing-default);
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

    disconnectedCallback() {
        this._cancelAnimation();
        super.disconnectedCallback();
    }

    updated(changed) {
        if (changed.has('value')) {
            this._animateTo(this.value);
        }
    }

    firstUpdated() {
        this._displayValue = this.value;
    }

    _cancelAnimation() {
        if (this._animationFrameId !== null) {
            window.cancelAnimationFrame(this._animationFrameId);
            this._animationFrameId = null;
        }
    }

    _animateTo(nextValue) {
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
        const step = (now) => {
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

    _formattedValue() {
        return formatPlatformNumber(Math.round(this._displayValue), this.locale, {
            maximumFractionDigits: this.maximumFractionDigits,
        });
    }

    render() {
        const animating = this._animationFrameId !== null;
        return html`
            <span class="value ${animating ? 'animating' : ''}">${this._formattedValue()}</span>
        `;
    }
}

customElements.define('platform-animated-number', PlatformAnimatedNumber);
