/**
 * graph-timeline — вертикальный ползунок временного диапазона графа.
 *
 * Композиционный child-компонент: эмитит `timeline-change`
 * (detail = { startPercent, endPercent }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { clampTimelinePercents } from '../utils/crm-timeline-range.js';

export class CRMGraphTimeline extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        minTimestamp: { type: Number },
        maxTimestamp: { type: Number },
        startPercent: { type: Number },
        endPercent: { type: Number },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                align-items: center;
                width: 56px;
                padding: 8px 4px;
                gap: 8px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 14px;
                backdrop-filter: blur(6px);
                pointer-events: none;
            }

            .title {
                font-size: 9px;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }

            .sliders {
                position: relative;
                width: 28px;
                height: 220px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .track {
                position: absolute;
                width: 3px;
                height: 100%;
                border-radius: 2px;
                background: var(--glass-border-subtle);
            }

            .track-active {
                position: absolute;
                width: 3px;
                border-radius: 2px;
                background: var(--accent);
                opacity: 0.55;
            }

            .slider {
                position: absolute;
                width: 220px;
                height: 28px;
                margin: 0;
                transform: rotate(-90deg);
                transform-origin: center center;
                background: transparent;
                pointer-events: none;
                -webkit-appearance: none;
                appearance: none;
            }

            .slider::-webkit-slider-runnable-track {
                background: transparent;
                height: 4px;
            }

            .slider::-webkit-slider-thumb {
                pointer-events: auto;
                -webkit-appearance: none;
                appearance: none;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: #7fd6ff;
                cursor: pointer;
                border: 2px solid rgba(255, 255, 255, 0.6);
                margin-top: -6px;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
            }

            .slider.start { z-index: 2; }
            .slider.end { z-index: 1; }
            .slider.end::-webkit-slider-thumb { background: #f2c94c; }

            .date-label {
                font-size: 8px;
                color: var(--text-tertiary);
                text-align: center;
                line-height: 1.2;
            }

            .reset-btn {
                width: 24px;
                height: 24px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: 6px;
                background: var(--glass-solid-subtle);
                color: var(--text-tertiary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                pointer-events: auto;
                transition: background 0.14s;
            }

            .reset-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            @media (max-width: 1199px) {
                .sliders { height: 160px; }
                .slider { width: 160px; }
            }

            @media (max-width: 767px) {
                :host { width: 48px; padding: 4px; }
                .sliders { height: 100px; }
                .slider { width: 100px; }
            }
        `,
    ];

    constructor() {
        super();
        this.minTimestamp = 0;
        this.maxTimestamp = 0;
        this.startPercent = 0;
        this.endPercent = 100;
    }

    _formatDate(ts) {
        if (!ts) return '';
        return new Date(ts).toLocaleDateString();
    }

    _timelineSpanOk() {
        return (
            typeof this.minTimestamp === 'number'
            && typeof this.maxTimestamp === 'number'
            && Number.isFinite(this.minTimestamp)
            && Number.isFinite(this.maxTimestamp)
            && this.maxTimestamp > this.minTimestamp
        );
    }

    _onStartInput(e) {
        let start = Math.min(Number(e.target.value), this.endPercent);
        let end = this.endPercent;
        if (this._timelineSpanOk()) {
            const c = clampTimelinePercents(start, end, this.minTimestamp, this.maxTimestamp);
            start = c.startPercent;
            end = c.endPercent;
        }
        this.startPercent = Math.max(0, start);
        this.endPercent = Math.min(100, end);
        this.emit('timeline-change', {
            startPercent: this.startPercent,
            endPercent: this.endPercent,
        });
    }

    _onEndInput(e) {
        let start = this.startPercent;
        let end = Math.max(Number(e.target.value), this.startPercent);
        if (this._timelineSpanOk()) {
            const c = clampTimelinePercents(start, end, this.minTimestamp, this.maxTimestamp);
            start = c.startPercent;
            end = c.endPercent;
        }
        this.startPercent = Math.max(0, start);
        this.endPercent = Math.min(100, end);
        this.emit('timeline-change', {
            startPercent: this.startPercent,
            endPercent: this.endPercent,
        });
    }

    _reset() {
        this.startPercent = 0;
        this.endPercent = 100;
        this.emit('timeline-change', { startPercent: 0, endPercent: 100 });
    }

    render() {
        return html`
            <span class="title">${this.t('graph.timeline_title')}</span>
            <span class="date-label">${this._formatDate(this.maxTimestamp)}</span>
            <div class="sliders">
                <div class="track"></div>
                <div
                    class="track-active"
                    style="top:${100 - this.endPercent}%;bottom:${this.startPercent}%"
                ></div>
                <input
                    class="slider start"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    .value=${String(this.startPercent)}
                    @input=${this._onStartInput}
                />
                <input
                    class="slider end"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    .value=${String(this.endPercent)}
                    @input=${this._onEndInput}
                />
            </div>
            <span class="date-label">${this._formatDate(this.minTimestamp)}</span>
            <button class="reset-btn" type="button" title=${this.t('graph.timeline_reset')} @click=${this._reset}>
                <platform-icon name="refresh" size="16"></platform-icon>
            </button>
        `;
    }
}

customElements.define('crm-graph-timeline', CRMGraphTimeline);
