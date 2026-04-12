/**
 * Модалка подтверждения для flows: тег `confirm-modal`, хелпер `confirm`.
 * Реализация — `PlatformConfirmModal` в core.
 */
import {
    PlatformConfirmModal,
    platformConfirm,
} from '@platform/lib/components/platform-confirm-modal.js';

export class ConfirmModal extends PlatformConfirmModal {}

if (!customElements.get('confirm-modal')) {
    customElements.define('confirm-modal', ConfirmModal);
}

/**
 * @param {string} message
 * @param {Record<string, unknown>} [options]
 * @returns {Promise<boolean|string|void>}
 */
export async function confirm(message, options = {}) {
    let modal = document.querySelector('confirm-modal');
    if (!modal) {
        modal = document.createElement('confirm-modal');
        document.body.appendChild(modal);
    }
    return modal.confirm({ message, ...options });
}

export { PlatformConfirmModal, platformConfirm };
