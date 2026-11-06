/**
 * <cosmic-scope> — корневой контейнер космических публичных страниц:
 * монтирует фиксированную `<cosmic-scene>` и `<cosmic-rail>`, владеет
 * CosmicScrollController (Lenis + главы + пины), даёт тёмный scope-палитру
 * `.cosmic-scope` поверх slotted-контента.
 *
 * Разметка глав — на дочерних `<section>`: `data-cosmic-chapter`
 * (обязателен), `data-cosmic-hue` (0..360), `data-cosmic-label` (текст
 * «экрана» agent core и рельсы), `data-cosmic-pin` (sticky-траверс).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CosmicScrollController } from './cosmic-scroll.js';
import { CosmicScene } from './cosmic-scene.js';
import { CosmicRail } from './cosmic-rail.js';
import type { CSSResultGroup, TemplateResult } from 'lit';

export class CosmicScope extends PlatformElement {
    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: relative;
                background: var(--marketing-cosmic-bg);
                color: var(--marketing-cosmic-text);
                color-scheme: dark;
            }
            /* CSS-неbula под WebGL-сценой: видна до инициализации WebGL
               и остаётся единственным фоном, когда сцена скрыта. */
            .cosmic-underlay {
                position: fixed;
                inset: 0;
                z-index: 0;
                pointer-events: none;
                background:
                    radial-gradient(ellipse 90% 60% at 70% 10%, var(--marketing-cosmic-nebula-a), transparent 60%),
                    radial-gradient(ellipse 70% 50% at 20% 90%, var(--marketing-cosmic-nebula-b), transparent 65%),
                    var(--marketing-cosmic-bg);
            }
            /* Свет от курсора: фиксированный слой над контентом, следует
               за pointer через --cursor-x/--cursor-y. Выключен на touch
               и при prefers-reduced-motion. */
            .cosmic-spotlight {
                position: fixed;
                inset: 0;
                z-index: 2;
                pointer-events: none;
                mix-blend-mode: screen;
                background:
                    radial-gradient(
                        520px circle at var(--cursor-x, 50%) var(--cursor-y, 50%),
                        rgba(61, 220, 255, 0.10),
                        rgba(61, 220, 255, 0.035) 42%,
                        transparent 68%
                    );
                opacity: var(--cosmic-spotlight-opacity, 0);
                transition: opacity 0.5s ease;
            }
            @media (pointer: coarse), (prefers-reduced-motion: reduce) {
                .cosmic-spotlight { display: none; }
            }
            .cosmic-content {
                position: relative;
                z-index: 1;
                /* Космическая палитра поверх semantic-токенов: slotted-секции
                   читают их через наследование в flattened-дереве. */
                --marketing-page-bg: transparent;
                --marketing-hero-bg: transparent;
                --marketing-header-bg: rgba(3, 5, 8, 0.55);
                --marketing-benefits-band-bg: transparent;
                --marketing-benefits-band-border: var(--marketing-cosmic-line);
                --marketing-hero-title-gradient: linear-gradient(
                    180deg,
                    var(--marketing-cosmic-text) 30%,
                    rgba(233, 241, 251, 0.55)
                );
                --text-primary: var(--marketing-cosmic-text);
                --text-secondary: var(--marketing-cosmic-muted);
                --text-tertiary: var(--marketing-cosmic-label);
                --text-disabled: var(--marketing-cosmic-label);
                --accent: var(--marketing-cosmic-cyan);
                --accent-hover: var(--marketing-cosmic-text);
                --accent-subtle: rgba(61, 220, 255, 0.12);
                --glass-bg-subtle: var(--marketing-cosmic-glass);
                --glass-bg-medium: var(--marketing-cosmic-glass);
                --glass-bg-strong: var(--marketing-cosmic-panel-bg);
                --glass-solid-subtle: var(--marketing-cosmic-glass);
                --glass-solid-medium: var(--marketing-cosmic-panel-bg);
                --glass-solid-strong: rgba(6, 11, 19, 0.92);
                --glass-border-subtle: var(--marketing-cosmic-line);
                --glass-border-medium: var(--marketing-cosmic-panel-border);
                --glass-border-strong: var(--marketing-cosmic-panel-border-strong);
                --glass-border-glow: rgba(61, 220, 255, 0.45);
                --glass-tint-subtle: transparent;
                --glass-inner-glow-subtle: inset 0 1px 0 rgba(140, 180, 220, 0.08);
                --glass-inner-glow-medium: inset 0 1px 0 rgba(140, 180, 220, 0.12);
                --glass-inner-glow-strong: inset 0 1px 1px rgba(140, 180, 220, 0.16);
                --glass-shadow-medium: var(--marketing-cosmic-panel-shadow);
                --glass-shadow-strong: var(--marketing-cosmic-panel-shadow);
                --glass-shadow-ultra: var(--marketing-cosmic-panel-shadow);
                --hover-glow: 0 0 0 4px rgba(61, 220, 255, 0.16);
                --platform-btn-primary-bg: var(--marketing-cosmic-cyan);
                --platform-btn-primary-bg-hover: var(--marketing-cosmic-text);
                --platform-btn-primary-text: var(--marketing-cosmic-bg);
                --platform-btn-secondary-bg: var(--marketing-cosmic-glass);
                --platform-btn-secondary-bg-hover: var(--marketing-cosmic-glass-strong);
                --platform-btn-secondary-text: var(--marketing-cosmic-text);
                --marketing-product-accent: var(--marketing-cosmic-cyan);
                --marketing-product-accent-subtle: rgba(61, 220, 255, 0.12);
                --text-on-accent: var(--marketing-cosmic-bg);
                --marketing-shot-border: var(--marketing-cosmic-panel-border);
                --marketing-shot-shadow: var(--marketing-cosmic-panel-shadow);
                --accent-gradient: linear-gradient(180deg, var(--marketing-cosmic-cyan), var(--marketing-cosmic-blue));
                --bg-primary: var(--marketing-cosmic-bg);
                --bg-elevated: rgba(6, 11, 19, 0.94);
                --bg-gradient: none;
                --glass-tint-strong: var(--marketing-cosmic-glass-strong);
                --platform-btn-primary-shadow-hover: 0 0 16px rgba(61, 220, 255, 0.45);
                --platform-btn-secondary-border: var(--marketing-cosmic-panel-border);
            }
        `,
    ];

    private _controller: CosmicScrollController | null = null;

    override firstUpdated(): void {
        const scene = this.renderRoot.querySelector('cosmic-scene');
        const rail = this.renderRoot.querySelector('cosmic-rail');
        if (!(scene instanceof CosmicScene)) {
            throw new Error('cosmic-scope: <cosmic-scene> missing');
        }
        if (!(rail instanceof CosmicRail)) {
            throw new Error('cosmic-scope: <cosmic-rail> missing');
        }
        const controller = new CosmicScrollController(this, scene, rail);
        this._controller = controller;
        void controller.start();
        this._bindSpotlight();
    }

    private _bindSpotlight(): void {
        const fine = window.matchMedia('(pointer: fine)').matches;
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!fine || reduced) return;
        let raf = 0;
        this.useDomEvent<PointerEvent>(window, 'pointermove', (e) => {
            if (raf !== 0) return;
            const x = e.clientX;
            const y = e.clientY;
            raf = requestAnimationFrame(() => {
                raf = 0;
                this.style.setProperty('--cursor-x', `${x}px`);
                this.style.setProperty('--cursor-y', `${y}px`);
                this.style.setProperty('--cosmic-spotlight-opacity', '1');
            });
        }, { passive: true });
    }

    override disconnectedCallback(): void {
        if (this._controller !== null) {
            this._controller.stop();
            this._controller = null;
        }
        super.disconnectedCallback();
    }

    /** Якорная навигация — Lenis scrollTo или нативный scroll при reduced-motion. */
    scrollToSection(target: HTMLElement): void {
        if (this._controller === null) {
            throw new Error('cosmic-scope: scroll controller not started');
        }
        this._controller.scrollToSection(target);
    }

    override render(): TemplateResult {
        return html`
            <div class="cosmic-underlay"></div>
            <cosmic-scene></cosmic-scene>
            <div class="cosmic-spotlight"></div>
            <cosmic-rail></cosmic-rail>
            <div class="cosmic-content"><slot></slot></div>
        `;
    }
}

customElements.define('cosmic-scope', CosmicScope);
