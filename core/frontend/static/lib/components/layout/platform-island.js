/**
 * PlatformIsland - унифицированный glass-контейнер для контента
 * 
 * На мобильных устройствах Island занимает весь экран без закруглений.
 * Бургер-меню рендерится через page-header компонент внутри страниц.
 */
import { html, css } from 'lit';
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
    }

    render() {
        return html`
            <div class="island">
                ${this.headerGlow ? html`<div class="island-header-glow"></div>` : ''}
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
