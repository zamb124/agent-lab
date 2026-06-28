/**
 * Базовые стили для PlatformElement
 */
import { css } from '../../assets/js/lit/lit.min.js';

export const baseStyles = css`
    :host {
        box-sizing: border-box;
    }
    
    :host *, :host *::before, :host *::after {
        box-sizing: inherit;
    }
    
    :host([hidden]) {
        display: none !important;
    }

    /*
     * Ссылки внутри Shadow DOM не наследуют reset.css у document.
     * Исключаем .btn и marketing-download-link — иначе accent-текст сливается с primary-фоном кнопки-ссылки.
     */
    :host a:any-link:not(.btn):not([class*='marketing-download-link']) {
        color: var(--accent);
        text-decoration: none;
        transition: color var(--duration-fast) var(--easing-default);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-link']):hover {
        color: var(--accent-hover);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-link']):visited {
        color: var(--accent);
    }

    :host a:any-link:not(.btn):not([class*='marketing-download-link']):active {
        color: var(--accent-active);
    }
`;

export { formStyles } from '../styles/shared/form.styles.js';
export { modalStyles, modalUtilityStyles, modalShellStyles } from '../styles/shared/modal.styles.js';
export { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';

