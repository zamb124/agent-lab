/**
 * Сервис уведомлений (toast)
 */
import { AppEvents } from '../lib/utils/types.js';

let toastIdCounter = 0;

export class NotifyService {
    constructor() {
        /** @type {Array<import('../core/types.js').Toast>} */
        this.toasts = [];
        /** @type {Function|null} */
        this._updateCallback = null;
    }

    /**
     * Установить callback для обновления UI
     * @param {Function} callback
     */
    setUpdateCallback(callback) {
        this._updateCallback = callback;
    }

    /**
     * Показать уведомление
     * @param {'success'|'error'|'warning'|'info'} type
     * @param {string} message
     * @param {number} duration
     */
    show(type, message, duration = 3000) {
        const id = `toast-${++toastIdCounter}`;
        
        const toast = {
            id,
            type,
            message,
            duration,
        };

        this.toasts.push(toast);
        this._notify();

        // Автоудаление
        if (duration > 0) {
            setTimeout(() => this.remove(id), duration);
        }

        // Глобальное событие
        window.dispatchEvent(new CustomEvent(AppEvents.TOAST_SHOW, {
            detail: toast
        }));

        return id;
    }

    /**
     * Удалить уведомление
     * @param {string} id
     */
    remove(id) {
        const index = this.toasts.findIndex(t => t.id === id);
        if (index !== -1) {
            this.toasts.splice(index, 1);
            this._notify();
        }
    }

    /**
     * Очистить все уведомления
     */
    clear() {
        this.toasts = [];
        this._notify();
    }

    /**
     * Вызвать callback для обновления UI
     */
    _notify() {
        this._updateCallback?.([...this.toasts]);
    }

    // Удобные методы

    success(message, duration = 3000) {
        return this.show('success', message, duration);
    }

    error(message, duration = 5000) {
        return this.show('error', message, duration);
    }

    warning(message, duration = 4000) {
        return this.show('warning', message, duration);
    }

    info(message, duration = 3000) {
        return this.show('info', message, duration);
    }
}


