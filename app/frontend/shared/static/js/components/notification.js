/**
 * Единая система уведомлений
 */

const NOTIFICATION_TYPES = {
    SUCCESS: 'success',
    ERROR: 'error',
    DANGER: 'danger',
    WARNING: 'warning',
    INFO: 'info'
};

const ICON_MAP = {
    'success': 'bi-check-circle-fill',
    'error': 'bi-exclamation-circle-fill',
    'danger': 'bi-exclamation-circle-fill',
    'warning': 'bi-exclamation-triangle-fill',
    'info': 'bi-info-circle-fill'
};

class NotificationManager {
    constructor() {
        this.container = null;
        this.notifications = new Map();
        this.init();
    }
    
    init() {
        this.container = document.querySelector('.notifications-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'notifications-container';
            document.body.appendChild(this.container);
        }
    }
    
    show(message, type = NOTIFICATION_TYPES.INFO, duration = 5000) {
        const id = `notification_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.setAttribute('data-notification-id', id);
        notification.innerHTML = `
            <i class="bi ${ICON_MAP[type] || ICON_MAP['info']} notification-icon"></i>
            <div class="notification-content">
                <p class="notification-message">${message}</p>
            </div>
            <button class="notification-close" aria-label="Закрыть">
                <i class="bi bi-x"></i>
            </button>
        `;
        
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => this.hide(id));
        
        this.container.appendChild(notification);
        this.notifications.set(id, notification);
        
        if (duration > 0) {
            setTimeout(() => this.hide(id), duration);
        }
        
        return id;
    }
    
    hide(id) {
        const notification = this.notifications.get(id);
        if (!notification) return;
        
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            notification.remove();
            this.notifications.delete(id);
        }, 300);
    }
    
    clear() {
        this.notifications.forEach((notification, id) => {
            this.hide(id);
        });
    }
}

const notificationManager = new NotificationManager();

export function showNotification(message, type = NOTIFICATION_TYPES.INFO, duration = 5000) {
    return notificationManager.show(message, type, duration);
}

export function hideNotification(id) {
    notificationManager.hide(id);
}

export function clearNotifications() {
    notificationManager.clear();
}

export { NOTIFICATION_TYPES };
export default notificationManager;

