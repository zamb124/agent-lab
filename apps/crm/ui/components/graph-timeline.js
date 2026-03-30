import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class GraphTimeline extends PlatformElement {
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

            .slider.start {
                z-index: 2;
            }

            .slider.end {
                z-index: 1;
            }

            .slider.end::-webkit-slider-thumb {
                background: #f2c94c;
            }

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
                .sliders {
                    height: 160px;
                }

                .slider {
                    width: 160px;
                }
            }

            @media (max-width: 767px) {
                :host {
                    width: 48px;
                    padding: 4px;
                }

                .sliders {
                    height: 100px;
                }

                .slider {
                    width: 100px;
                }
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
        return new Date(ts).toLocaleDateString('ru-RU');
    }

    _onStartInput(e) {
        const value = Number(e.target.value);
        this.startPercent = Math.min(value, this.endPercent);
        this.emit('timeline-change', {
            startPercent: this.startPercent,
            endPercent: this.endPercent,
        });
    }

    _onEndInput(e) {
        const value = Number(e.target.value);
        this.endPercent = Math.max(value, this.startPercent);
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
            <span class="title">Timeline</span>
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
            <button class="reset-btn" type="button" title="Сброс timeline" @click=${this._reset}>
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v5h5"/></svg>
            </button>
        `;
    }
}

customElements.define('graph-timeline', GraphTimeline);
