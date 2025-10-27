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
        const showTime = Date.now();
        
        // Проверяем тип duration
        console.log(`🔔 [${showTime}] Показываем нотификацию (${type}): "${message}" на ${duration}ms`);
        console.log(`   Duration тип: ${typeof duration}, значение: ${duration}`);
        
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
        closeBtn.addEventListener('click', () => {
            const elapsed = Date.now() - showTime;
            console.log(`🔕 Пользователь закрыл нотификацию: ${id} (прошло ${elapsed}ms)`);
            this.hide(id);
        });
        
        this.container.appendChild(notification);
        this.notifications.set(id, {
            element: notification,
            showTime: showTime
        });
        
        // Принудительный reflow для анимации
        notification.offsetHeight;
        
        // Добавляем класс show чтобы нотификация осталась видимой после анимации
        requestAnimationFrame(() => {
            notification.classList.add('show');
        });
        
        if (duration > 0) {
            console.log(`⏱️ Установлен таймер на ${duration}ms для нотификации ${id}`);
            const timerId = setTimeout(() => {
                const elapsed = Date.now() - showTime;
                console.log(`⏰ Таймер сработал через ${elapsed}ms (ожидалось ${duration}ms), скрываем нотификацию ${id}`);
                this.hide(id);
            }, duration);
            
            // Сохраняем таймер чтобы можно было отменить
            this.notifications.get(id).timerId = timerId;
        }
        
        return id;
    }
    
    hide(id) {
        const notificationData = this.notifications.get(id);
        if (!notificationData) {
            console.log(`⚠️ Попытка скрыть несуществующую нотификацию: ${id}`);
            return;
        }
        
        const elapsed = Date.now() - notificationData.showTime;
        console.log(`👋 Скрываем нотификацию: ${id} (была видна ${elapsed}ms)`);
        
        // Отменяем таймер если есть
        if (notificationData.timerId) {
            clearTimeout(notificationData.timerId);
        }
        
        const notification = notificationData.element;
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            notification.remove();
            this.notifications.delete(id);
            console.log(`🗑️ Нотификация удалена: ${id}`);
        }, 300);
    }
    
    clear() {
        console.log(`🧹 Очищаем все нотификации (всего: ${this.notifications.size})`);
        this.notifications.forEach((notificationData, id) => {
            this.hide(id);
        });
    }
}

const notificationManager = new NotificationManager();

export function showNotification(message, type = NOTIFICATION_TYPES.INFO, duration = 5000) {
    console.log(`📢 showNotification вызван: message="${message}", type=${type}, duration=${duration} (тип: ${typeof duration})`);
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

