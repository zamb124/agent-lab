/**
 * <cosmic-rail> — левая моно-рельса прогресса скролла (аналог температурной
 * шкалы quantumwallet.tech): тики, шеврон-маркер, readout `DEPTH nnn%` и
 * номер активной главы `CH n/N`. На узких экранах скрыта.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';

const TICK_COUNT = 24;

export class CosmicRail extends PlatformElement {
    static override properties: PropertyDeclarations = {
        progress: { type: Number, attribute: false },
        chapterIndex: { type: Number, attribute: false },
        chapterCount: { type: Number, attribute: false },
        chapterLabel: { type: String, attribute: false },
    };

    declare progress: number;
    declare chapterIndex: number;
    declare chapterCount: number;
    declare chapterLabel: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                position: fixed;
                left: var(--space-5);
                top: 0;
                bottom: 0;
                z-index: 40;
                width: 48px;
                pointer-events: none;
                display: block;
                font-family: var(--font-mono);
                color: var(--marketing-cosmic-label);
            }
            .rail-track {
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 1px;
                background: var(--marketing-cosmic-line);
            }
            .rail-fill {
                position: absolute;
                left: 0;
                top: 0;
                width: 1px;
                background: var(--marketing-cosmic-cyan);
                transform-origin: top;
                box-shadow: 0 0 8px var(--marketing-cosmic-cyan);
            }
            .rail-tick {
                position: absolute;
                left: 0;
                width: 7px;
                height: 1px;
                background: var(--marketing-cosmic-line-strong);
            }
            .rail-tick--major {
                width: 13px;
                background: var(--marketing-cosmic-label);
            }
            .rail-marker {
                position: absolute;
                left: -4px;
                width: 0;
                height: 0;
                border-top: 5px solid transparent;
                border-bottom: 5px solid transparent;
                border-left: 6px solid var(--marketing-cosmic-ink);
                transform: translateY(-50%);
            }
            .rail-readout {
                position: absolute;
                left: 16px;
                transform: translateY(-50%);
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.06em;
                white-space: nowrap;
            }
            .rail-chapter {
                position: absolute;
                left: 16px;
                bottom: var(--space-6);
                font-size: 11px;
                letter-spacing: 0.08em;
                white-space: nowrap;
                opacity: 0.85;
            }
            .rail-chapter-label {
                display: block;
                color: var(--marketing-cosmic-cyan);
                margin-top: 4px;
                max-width: 200px;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            @media (max-width: 900px) {
                :host { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this.progress = 0;
        this.chapterIndex = 0;
        this.chapterCount = 0;
        this.chapterLabel = '';
    }

    override render(): TemplateResult {
        const pct = Math.round(this.progress * 100);
        const pctLabel = String(pct).padStart(3, '0');
        const ticks = [];
        for (let i = 0; i <= TICK_COUNT; i++) {
            const major = i % 6 === 0;
            ticks.push(html`
                <span
                    class="rail-tick ${major ? 'rail-tick--major' : ''}"
                    style="top: ${(i / TICK_COUNT) * 100}%"
                ></span>
            `);
        }
        const markerTop = `${(this.progress * 100).toFixed(2)}%`;
        return html`
            <div class="rail-track"></div>
            <div class="rail-fill" style="height: ${markerTop}"></div>
            ${ticks}
            <div class="rail-marker" style="top: ${markerTop}"></div>
            <div class="rail-readout" style="top: ${markerTop}">DEPTH ${pctLabel}%</div>
            <div class="rail-chapter">
                CH ${this.chapterIndex + 1}/${this.chapterCount}
                <span class="rail-chapter-label">${this.chapterLabel}</span>
            </div>
        `;
    }
}

customElements.define('cosmic-rail', CosmicRail);
