/**
 * Base styles для PlatformElement
 */
import { css } from 'lit';

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
`;

export { formStyles } from '../styles/shared/form.styles.js';
export { modalStyles, modalUtilityStyles, modalShellStyles } from '../styles/shared/modal.styles.js';
export { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';

