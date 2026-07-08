/**
 * Базовые стили для PlatformElement
 */
import { css } from '../../assets/js/lit/lit.min.js';

export const baseStyles = css`
    :host {
        box-sizing: border-box;
        font-family: var(--font-sans);
        font-feature-settings: var(--font-feature-sans);
    }

    /*
     * reset.css (button/input font: inherit) не действует внутри Shadow DOM.
     * Без этого UA stylesheet задаёт button font-family (Arial) поверх platform tokens.
     */
    :host button,
    :host input,
    :host textarea,
    :host select {
        font: inherit;
        color: inherit;
    }
    
    :host *, :host *::before, :host *::after {
        box-sizing: inherit;
    }
    
    :host([hidden]) {
        display: none !important;
    }

    /*
     * Ссылки внутри Shadow DOM не наследуют reset.css у document.
     * Исключаем .btn и marketing-download-* — иначе accent-текст сливается с primary-фоном CTA.
     */
    :host a:any-link:not(.btn):not([class*='marketing-download-']) {
        color: var(--accent);
        text-decoration: none;
        transition: color var(--duration-fast) var(--easing-default);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-']):hover {
        color: var(--accent-hover);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-']):visited {
        color: var(--accent);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-']):active {
        color: var(--accent-active);
    }
`;

export { formStyles } from '../styles/shared/form.styles.js';
export { modalStyles, modalUtilityStyles, modalShellStyles } from '../styles/shared/modal.styles.js';
export { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';

