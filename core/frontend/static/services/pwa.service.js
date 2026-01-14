/**
 * PWA Service - управление Service Worker и Push Notifications
 */

export class PWAService {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.swRegistration = null;
        this.pushSubscription = null;
        this._deferredPrompt = null;
        this._updateAvailable = false;
        
        // Слушаем beforeinstallprompt для A2HS
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this._deferredPrompt = e;
            this._dispatchEvent('pwa-install-available');
        });
        
        // Слушаем успешную установку
        window.addEventListener('appinstalled', () => {
            this._deferredPrompt = null;
            this._dispatchEvent('pwa-installed');
        });
    }

    /**
     * Инициализация PWA - регистрация Service Worker
     */
    async init() {
        if (!('serviceWorker' in navigator)) {
            console.warn('[PWA] Service Worker не поддерживается');
            return false;
        }

        try {
            this.swRegistration = await navigator.serviceWorker.register('/sw.js', {
                scope: '/'
            });
            console.log('[PWA] Service Worker зарегистрирован');

            // Проверка обновлений
            this.swRegistration.addEventListener('updatefound', () => {
                const newWorker = this.swRegistration.installing;
                if (newWorker) {
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            this._updateAvailable = true;
                            this._dispatchEvent('pwa-update-available');
                        }
                    });
                }
            });

            // Слушаем сообщения от SW
            navigator.serviceWorker.addEventListener('message', (event) => {
                console.log('[PWA] Message from SW:', event.data);
            });

            return true;
        } catch (error) {
            console.error('[PWA] Ошибка регистрации SW:', error);
            return false;
        }
    }

    /**
     * Подписка на Push уведомления
     */
    async subscribeToPush() {
        if (!this.swRegistration) {
            console.warn('[PWA] SW не зарегистрирован');
            return null;
        }

        // Проверяем поддержку Push API
        if (!('PushManager' in window)) {
            console.warn('[PWA] Push API не поддерживается');
            return null;
        }

        // Проверяем iOS ограничения
        if (this._isIOS() && !this.isInstalled()) {
            console.warn('[PWA] Push на iOS требует установки на Home Screen');
            return null;
        }

        // Запрашиваем разрешение
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            console.warn('[PWA] Разрешение на уведомления отклонено');
            return null;
        }

        try {
            // Получаем VAPID ключ с сервера
            const response = await fetch(`${this.baseUrl}/api/push/vapid-public-key`);
            if (!response.ok) {
                throw new Error('Failed to get VAPID key');
            }
            const { publicKey } = await response.json();

            // Подписываемся на push
            this.pushSubscription = await this.swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this._urlBase64ToUint8Array(publicKey)
            });

            // Отправляем подписку на сервер
            await fetch(`${this.baseUrl}/api/push/subscribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    endpoint: this.pushSubscription.endpoint,
                    keys: {
                        p256dh: this._arrayBufferToBase64(this.pushSubscription.getKey('p256dh')),
                        auth: this._arrayBufferToBase64(this.pushSubscription.getKey('auth'))
                    },
                    platform: this._detectPlatform()
                })
            });

            console.log('[PWA] Push подписка создана');
            return this.pushSubscription;

        } catch (error) {
            console.error('[PWA] Ошибка подписки на push:', error);
            return null;
        }
    }

    /**
     * Отписка от Push уведомлений
     */
    async unsubscribeFromPush() {
        if (!this.pushSubscription) {
            return;
        }

        try {
            await this.pushSubscription.unsubscribe();
            
            await fetch(`${this.baseUrl}/api/push/unsubscribe?endpoint=${encodeURIComponent(this.pushSubscription.endpoint)}`, {
                method: 'DELETE',
                credentials: 'include'
            });
            
            this.pushSubscription = null;
            console.log('[PWA] Push подписка удалена');
        } catch (error) {
            console.error('[PWA] Ошибка отписки:', error);
        }
    }

    /**
     * Проверка существующей push подписки
     */
    async getExistingPushSubscription() {
        if (!this.swRegistration) {
            return null;
        }
        
        try {
            this.pushSubscription = await this.swRegistration.pushManager.getSubscription();
            return this.pushSubscription;
        } catch (error) {
            console.error('[PWA] Ошибка получения подписки:', error);
            return null;
        }
    }

    /**
     * Проверка - установлено ли приложение
     */
    isInstalled() {
        // Проверка display-mode
        if (window.matchMedia('(display-mode: standalone)').matches) {
            return true;
        }
        // iOS Safari
        if (window.navigator.standalone === true) {
            return true;
        }
        return false;
    }

    /**
     * Можно ли установить приложение
     */
    canInstall() {
        return !this.isInstalled() && this._deferredPrompt !== null;
    }

    /**
     * Показать prompt установки
     */
    async promptInstall() {
        if (!this._deferredPrompt) {
            return false;
        }
        
        this._deferredPrompt.prompt();
        const { outcome } = await this._deferredPrompt.userChoice;
        this._deferredPrompt = null;
        
        return outcome === 'accepted';
    }

    /**
     * Есть ли доступное обновление
     */
    hasUpdate() {
        return this._updateAvailable;
    }

    /**
     * Применить обновление (перезагрузка)
     */
    applyUpdate() {
        if (this.swRegistration?.waiting) {
            this.swRegistration.waiting.postMessage('skipWaiting');
        }
        window.location.reload();
    }

    /**
     * Проверка поддержки push уведомлений
     */
    isPushSupported() {
        return 'PushManager' in window && 'serviceWorker' in navigator;
    }

    /**
     * Проверка разрешения на уведомления
     */
    getNotificationPermission() {
        if (!('Notification' in window)) {
            return 'unsupported';
        }
        return Notification.permission;
    }

    /**
     * Определение платформы
     */
    _detectPlatform() {
        const ua = navigator.userAgent;
        if (/iPad|iPhone|iPod/.test(ua)) return 'ios';
        if (/android/i.test(ua)) return 'android';
        return 'desktop';
    }

    /**
     * Проверка iOS
     */
    _isIOS() {
        return /iPad|iPhone|iPod/.test(navigator.userAgent);
    }

    /**
     * Конвертация VAPID ключа
     */
    _urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
    }

    /**
     * Конвертация ArrayBuffer в Base64
     */
    _arrayBufferToBase64(buffer) {
        return btoa(String.fromCharCode(...new Uint8Array(buffer)));
    }

    /**
     * Dispatch события
     */
    _dispatchEvent(name, detail = {}) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }
}

// Синглтон
let _pwaService = null;

export function getPWAService(baseUrl = '') {
    if (!_pwaService) {
        _pwaService = new PWAService(baseUrl);
    }
    return _pwaService;
}
