import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { flowUIEditorChromeTokens } from './editor-chrome.styles.js';

/**
 * Rulers (tick marks), baseline rows and user guides. Guides are created by
 * dragging out of a ruler, moved by dragging, removed by dropping back onto
 * the ruler. Emits `guides-change` with the full guides list
 * (`{axis: 'x'|'y', offset: number}[]`); the host owns persistence.
 */
export class FlowUIRulersGuidesOverlay extends LitElement {
    static properties = {
        rulersVisible: { type: Boolean, attribute: 'rulers-visible' },
        baselineVisible: { type: Boolean, attribute: 'baseline-visible' },
        guidesVisible: { type: Boolean, attribute: 'guides-visible' },
        baseline: { type: Number },
        width: { type: Number },
        height: { type: Number },
        guides: { attribute: false },
        _dragGuide: { state: true },
    };

    static styles = [
        flowUIEditorChromeTokens,
        css`
        :host { position: absolute; inset: 0; z-index: 11; pointer-events: none; }
        .baseline {
            position: absolute; inset: 0;
            background-image: linear-gradient(
                to bottom,
                transparent calc(var(--step) - 1px),
                color-mix(in srgb, var(--accent) 10%, transparent) var(--step)
            );
            background-size: 100% var(--step);
            opacity: 0.55;
        }
        .ruler {
            position: absolute;
            background: color-mix(in srgb, var(--bg-elevated) 94%, transparent);
            color: var(--text-tertiary);
            font: 8px/1 ui-monospace, monospace;
            pointer-events: auto;
            overflow: hidden;
        }
        .ruler.top { left: 0; right: 0; top: 0; height: 16px; cursor: row-resize; }
        .ruler.left { left: 0; top: 0; bottom: 0; width: 16px; cursor: col-resize; }
        .tick { position: absolute; background: currentColor; opacity: .28; }
        .ruler.top .tick { bottom: 0; width: 1px; height: 4px; }
        .ruler.top .tick[data-major="true"] { height: 8px; opacity: .5; }
        .ruler.left .tick { right: 0; height: 1px; width: 4px; }
        .ruler.left .tick[data-major="true"] { width: 8px; opacity: .5; }
        .tick-label { position: absolute; opacity: .55; }
        .ruler.top .tick-label { bottom: 6px; transform: translateX(2px); }
        .ruler.left .tick-label { transform: translateY(2px) rotate(-90deg); transform-origin: left top; right: 6px; }
        .guide { position: absolute; pointer-events: auto; }
        .guide[data-axis="x"] { top: 0; bottom: 0; width: 5px; margin-left: -2px; cursor: col-resize; }
        .guide[data-axis="y"] { left: 0; right: 0; height: 5px; margin-top: -2px; cursor: row-resize; }
        .guide::after {
            content: '';
            position: absolute;
            background: var(--info);
            opacity: .55;
        }
        .guide[data-axis="x"]::after { top: 0; bottom: 0; left: 2px; width: 1px; }
        .guide[data-axis="y"]::after { left: 0; right: 0; top: 2px; height: 1px; }
    `];

    constructor() {
        super();
        this.rulersVisible = false;
        this.baselineVisible = false;
        this.guidesVisible = false;
        this.baseline = 8;
        this.width = 0;
        this.height = 0;
        this.guides = [];
        this._dragGuide = null;
        this._onPointerMove = (event) => this._dragMove(event);
        this._onPointerUp = (event) => this._dragEnd(event);
    }

    disconnectedCallback() {
        window.removeEventListener('pointermove', this._onPointerMove);
        window.removeEventListener('pointerup', this._onPointerUp);
        super.disconnectedCallback();
    }

    _emitGuides(guides) {
        this.dispatchEvent(new CustomEvent('guides-change', {
            bubbles: true,
            composed: true,
            detail: { guides },
        }));
    }

    _localPoint(event) {
        const box = this.getBoundingClientRect();
        const scaleX = this.width > 0 ? this.width / box.width : 1;
        const scaleY = this.height > 0 ? this.height / box.height : 1;
        return {
            x: (event.clientX - box.left) * scaleX,
            y: (event.clientY - box.top) * scaleY,
        };
    }

    _startFromRuler(event, axis) {
        if (!this.guidesVisible) return;
        event.preventDefault();
        const point = this._localPoint(event);
        this._dragGuide = { axis, offset: axis === 'x' ? point.x : point.y, index: -1 };
        window.addEventListener('pointermove', this._onPointerMove);
        window.addEventListener('pointerup', this._onPointerUp);
    }

    _startFromGuide(event, index) {
        event.preventDefault();
        event.stopPropagation();
        const guide = this.guides[index];
        if (!guide) return;
        this._dragGuide = { axis: guide.axis, offset: guide.offset, index };
        window.addEventListener('pointermove', this._onPointerMove);
        window.addEventListener('pointerup', this._onPointerUp);
    }

    _dragMove(event) {
        if (!this._dragGuide) return;
        const point = this._localPoint(event);
        this._dragGuide = {
            ...this._dragGuide,
            offset: Math.round(this._dragGuide.axis === 'x' ? point.x : point.y),
        };
    }

    _dragEnd(event) {
        window.removeEventListener('pointermove', this._onPointerMove);
        window.removeEventListener('pointerup', this._onPointerUp);
        const drag = this._dragGuide;
        this._dragGuide = null;
        if (!drag) return;
        const point = this._localPoint(event);
        const offset = Math.round(drag.axis === 'x' ? point.x : point.y);
        const limit = drag.axis === 'x' ? this.width : this.height;
        const removed = offset < 18 || (limit > 0 && offset > limit - 2);
        const next = this.guides.filter((_, index) => index !== drag.index);
        if (!removed) next.push({ axis: drag.axis, offset });
        this._emitGuides(next);
    }

    _ticks(limit, axis) {
        const ticks = [];
        for (let offset = 0; offset <= limit; offset += 50) {
            const major = offset % 100 === 0;
            const style = axis === 'x' ? `left:${offset}px` : `top:${offset}px`;
            ticks.push(html`<span class="tick" data-major=${major ? 'true' : 'false'} style=${style}></span>`);
            if (major && offset > 0) {
                ticks.push(html`<span class="tick-label" style=${style}>${offset}</span>`);
            }
        }
        return ticks;
    }

    render() {
        const showAnything = this.rulersVisible || this.baselineVisible || this.guidesVisible;
        if (!showAnything) return nothing;
        const guides = this.guidesVisible ? this.guides : [];
        const drag = this._dragGuide;
        return html`
            ${this.baselineVisible ? html`<div class="baseline" style=${`--step:${this.baseline}px`}></div>` : nothing}
            ${guides.map((guide, index) => (drag && drag.index === index ? nothing : html`
                <div
                    class="guide"
                    data-axis=${guide.axis}
                    style=${guide.axis === 'x' ? `left:${guide.offset}px` : `top:${guide.offset}px`}
                    @pointerdown=${(event) => this._startFromGuide(event, index)}
                ></div>
            `))}
            ${drag ? html`<div
                class="guide"
                data-axis=${drag.axis}
                style=${drag.axis === 'x' ? `left:${drag.offset}px` : `top:${drag.offset}px`}
            ></div>` : nothing}
            ${this.rulersVisible ? html`
                <div class="ruler top" @pointerdown=${(event) => this._startFromRuler(event, 'y')}>
                    ${this._ticks(this.width || 3000, 'x')}
                </div>
                <div class="ruler left" @pointerdown=${(event) => this._startFromRuler(event, 'x')}>
                    ${this._ticks(this.height || 3000, 'y')}
                </div>
            ` : nothing}
        `;
    }
}
if (!customElements.get('flow-ui-rulers-guides-overlay')) customElements.define('flow-ui-rulers-guides-overlay', FlowUIRulersGuidesOverlay);
