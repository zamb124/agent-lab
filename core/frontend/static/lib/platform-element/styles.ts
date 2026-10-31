/**
 * Базовые стили для PlatformElement
 */
import { css } from 'lit';

export const baseStyles = css`
    :host {
        box-sizing: border-box;
        font-family: var(--font-sans);
        font-feature-settings: var(--font-feature-sans);
    }

    /*
     * reset.css (button/input font: inherit) не действует внутри Shadow DOM.
     * Без font: inherit UA stylesheet задаёт button font-family (Arial) поверх platform tokens.
     * color: inherit на :host button запрещён: специфичность (0,1,1) перебивает
     * .btn-primary / .cta-btn (0,1,0) и в light theme даёт тёмный --text-primary на violet CTA.
     * Цвет кнопки — только variant-токены (--platform-btn-*-text) или локальный class.
     *
     * :host input (0,1,1) сильнее класса .title-input (0,1,0): локальный
     * font-size/weight на input нужно писать как :host input.title-input, иначе
     * shorthand font: inherit съест размер заголовка страницы.
     */
    :host button {
        font: inherit;
    }

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
        transition: color var(--motion-duration-micro) var(--motion-ease-standard);
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

