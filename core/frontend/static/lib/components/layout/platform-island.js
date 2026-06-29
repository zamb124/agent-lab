/**
 * PlatformIsland — унифицированный glass-контейнер для контента
 * 
 * На мобильных устройствах Island занимает весь экран без закруглений.
 * Бургер-меню рендерится через page-header компонент внутри страниц.
 */
import { html } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { islandHostStyles, islandStyles } from '../../styles/shared/island.styles.js';
import '../glass-spinner.js';

export class PlatformIsland extends PlatformElement {
    static properties = {
        variant: { type: String, reflect: true },
        padding: { type: String, reflect: true },
        headerGlow: { type: Boolean, attribute: 'header-glow' },
        /** На мобилке с padding="none": только нижний safe-area (контент не уходит под home indicator). Sync чат без этого. */
        safeBottom: { type: Boolean, attribute: 'safe-bottom' },
        /** У .island-content overflow:hidden — скролл только у внутренних областей (иначе iOS при фокусе в input прокручивает весь слот вверх). */
        contentNoScroll: { type: Boolean, attribute: 'content-no-scroll' },
        loading: { type: Boolean, reflect: true },
        _scrolling: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        islandHostStyles,
        islandStyles,
    ];

    constructor() {
        super();
        this.variant = 'default';
        this.padding = 'md';
        this.headerGlow = true;
        this.safeBottom = false;
        this.contentNoScroll = false;
        this.loading = false;
        this._scrolling = false;
        this._scrollEndTimer = null;
        this._onIslandScroll = this._handleIslandScroll.bind(this);
        this._islandEl = null;
    }

    firstUpdated() {
        this._islandEl = this.renderRoot.querySelector('.island');
        if (this._islandEl) {
            this._islandEl.addEventListener('scroll', this._onIslandScroll, { capture: true, passive: true });
        }
    }

    disconnectedCallback() {
        if (this._islandEl) {
            this._islandEl.removeEventListener('scroll', this._onIslandScroll, { capture: true });
            this._islandEl = null;
        }
        if (this._scrollEndTimer !== null) {
            clearTimeout(this._scrollEndTimer);
            this._scrollEndTimer = null;
        }
        super.disconnectedCallback();
    }

    _handleIslandScroll() {
        if (!this._scrolling) {
            this._scrolling = true;
        }
        if (this._scrollEndTimer !== null) {
            clearTimeout(this._scrollEndTimer);
        }
        this._scrollEndTimer = setTimeout(() => {
            this._scrollEndTimer = null;
            this._scrolling = false;
        }, 120);
    }

    render() {
        return html`
            <div class="island ${this._scrolling ? 'is-scrolling' : ''}">
                <div class="island-surface" aria-hidden="true">
                    ${this.headerGlow ? html`<div class="island-header-glow"></div>` : ''}
                </div>
                ${this.loading ? html`
                    <div class="island-loading-overlay">
                        <glass-spinner size="lg"></glass-spinner>
                    </div>
                ` : ''}
                <div class="island-content ${this.loading ? 'busy' : ''}">
                    <slot></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-island', PlatformIsland);
