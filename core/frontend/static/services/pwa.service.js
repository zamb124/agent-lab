/**
 * PWA Service - управление Service Worker и Push Notifications
 */
import { AppEvents } from '../lib/utils/types.js';

const STORAGE_WEB_PUSH_ENDPOINT = 'humanitec_web_push_endpoint';
const STORAGE_IOS_DEVICE_TOKEN = 'humanitec_ios_device_token_posted';

export class PWAService {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.swRegistration = null;
        this.pushSubscription = null;
        this._deferredPrompt = null;
        this._updateAvailable = false;
        this._swPushMessageListenerAttached = false;

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

            if (!this._swPushMessageListenerAttached) {
                this._swPushMessageListenerAttached = true;
                navigator.serviceWorker.addEventListener('message', (event) => {
                    const d = event.data;
                    console.log('[PWA] Message from SW:', d);
                    if (d?.type !== 'humanitec-web-push' || !d.payload) {
                        return;
                    }
                    const p = d.payload;
                    const title = typeof p.title === 'string' ? p.title.trim() : '';
                    const body = typeof p.message === 'string' ? p.message.trim() : '';
                    const message = [title, body].filter(Boolean).join(' — ');
                    if (!message) {
                        return;
                    }
                    window.dispatchEvent(
                        new CustomEvent(AppEvents.TOAST_SHOW, {
                            detail: { type: 'info', message, duration: 5000 },
                        })
                    );
                });
            }

            return true;
        } catch (error) {
            console.error('[PWA] Ошибка регистрации SW:', error);
            return false;
        }
    }

    /**
     * Единая регистрация офлайн-push: нативный iOS (APNs токен) или Web Push (VAPID).
     */
    async ensurePushRegistration() {
        if (typeof window === 'undefined') {
            return null;
        }
        if (await this._shouldUseIosNativePush()) {
            return this._ensureIosNativePushRegistration();
        }
        return this._ensureWebPushRegistration();
    }

    /**
     * iOS в Capacitor: плагин APNs, не Web Push в WKWebView.
     * Мост WKWebView может быть доступен до полного заполнения Capacitor.isNativePlatform().
     */
    async _shouldUseIosNativePush() {
        const { isCapacitorNativePlatform, isStandaloneOrNativeAppShell } = await import(
            '../lib/utils/native-app-shell.js'
        );
        if (!this._isIOS()) {
            return false;
        }
        if (isCapacitorNativePlatform() && window.Capacitor?.getPlatform?.() === 'ios') {
            return true;
        }
        if (window.webkit?.messageHandlers?.bridge && isStandaloneOrNativeAppShell()) {
            return true;
        }
        return false;
    }

    async _ensureWebPushRegistration() {
        const initialized = await this.init();
        if (!initialized || !this.swRegistration) {
            return null;
        }
        if (!('PushManager' in window)) {
            console.warn('[PWA] Push API не поддерживается');
            return null;
        }
        if (this._isIOS() && !this.isInstalled()) {
            console.warn('[PWA] Push на iOS в Safari требует установки на Home Screen');
            return null;
        }

        await this.getExistingPushSubscription();
        if (this.pushSubscription) {
            const ep = this.pushSubscription.endpoint;
            if (sessionStorage.getItem(STORAGE_WEB_PUSH_ENDPOINT) === ep) {
                return this.pushSubscription;
            }
            const permission = Notification.permission;
            if (permission !== 'granted') {
                const p = await Notification.requestPermission();
                if (p !== 'granted') {
                    console.warn('[PWA] Разрешение на уведомления отклонено');
                    return null;
                }
            }
            try {
                await this._postWebVapidSubscription(this.pushSubscription);
                sessionStorage.setItem(STORAGE_WEB_PUSH_ENDPOINT, ep);
            } catch (e) {
                console.error('[PWA] Не удалось синхронизировать существующую push-подписку:', e);
            }
            return this.pushSubscription;
        }

        return this.subscribeToPush();
    }

    async _postWebVapidSubscription(pushSubscription) {
        const response = await fetch(`${this.baseUrl}/api/push/subscribe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                transport: 'web_vapid',
                endpoint: pushSubscription.endpoint,
                keys: {
                    p256dh: this._arrayBufferToBase64(pushSubscription.getKey('p256dh')),
                    auth: this._arrayBufferToBase64(pushSubscription.getKey('auth')),
                },
                platform: this._detectPlatform(),
            }),
        });
        if (!response.ok) {
            throw new Error(`subscribe failed: ${response.status}`);
        }
    }

    async _ensureIosNativePushRegistration() {
        let PushNotifications;
        try {
            ({ PushNotifications } = await import('@capacitor/push-notifications'));
        } catch (e) {
            console.warn('[PWA] @capacitor/push-notifications недоступен', e);
            return null;
        }

        let perm = await PushNotifications.checkPermissions();
        if (perm.receive !== 'granted') {
            perm = await PushNotifications.requestPermissions();
        }
        if (perm.receive !== 'granted') {
            console.warn('[PWA] Нативные push: нет разрешения');
            return null;
        }

        return new Promise((resolve) => {
            let settled = false;
            const timeout = setTimeout(() => {
                if (!settled) {
                    settled = true;
                    console.warn('[PWA] Таймаут регистрации APNs');
                    resolve(null);
                }
            }, 15000);

            const done = (value) => {
                if (settled) {
                    return;
                }
                settled = true;
                clearTimeout(timeout);
                resolve(value);
            };

            void PushNotifications.addListener('registration', async (tokenEvent) => {
                const token = tokenEvent?.value;
                if (!token) {
                    done(null);
                    return;
                }
                if (sessionStorage.getItem(STORAGE_IOS_DEVICE_TOKEN) === token) {
                    done(token);
                    return;
                }
                try {
                    const r = await fetch(`${this.baseUrl}/api/push/subscribe`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            transport: 'ios_apns',
                            endpoint: '',
                            keys: { device_token: token },
                            platform: 'ios_native',
                        }),
                    });
                    if (!r.ok) {
                        console.error('[PWA] Ошибка сохранения APNs токена:', r.status);
                        done(null);
                        return;
                    }
                    sessionStorage.setItem(STORAGE_IOS_DEVICE_TOKEN, token);
                    done(token);
                } catch (err) {
                    console.error('[PWA] Сеть при регистрации APNs:', err);
                    done(null);
                }
            });

            void PushNotifications.addListener('registrationError', (err) => {
                console.error('[PWA] registrationError APNs:', err);
                done(null);
            });

            PushNotifications.register().catch((e) => {
                console.error('[PWA] PushNotifications.register:', e);
                done(null);
            });
        });
    }

    /**
     * Подписка на Push уведомления (Web Push / VAPID)
     */
    async subscribeToPush() {
        if (!this.swRegistration) {
            console.warn('[PWA] SW не зарегистрирован');
            return null;
        }

        if (!('PushManager' in window)) {
            console.warn('[PWA] Push API не поддерживается');
            return null;
        }

        if (this._isIOS() && !this.isInstalled()) {
            console.warn('[PWA] Push на iOS требует установки на Home Screen');
            return null;
        }

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            console.warn('[PWA] Разрешение на уведомления отклонено');
            return null;
        }

        try {
            const response = await fetch(`${this.baseUrl}/api/push/vapid-public-key`);
            if (!response.ok) {
                throw new Error('Failed to get VAPID key');
            }
            const body = await response.json();
            const publicKey = body?.publicKey;
            if (typeof publicKey !== 'string' || publicKey.trim() === '') {
                throw new Error('[PWA] Сервер вернул пустой VAPID publicKey (настройте push.vapid_public_key)');
            }

            this.pushSubscription = await this.swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this._urlBase64ToUint8Array(publicKey),
            });

            await this._postWebVapidSubscription(this.pushSubscription);
            sessionStorage.setItem(STORAGE_WEB_PUSH_ENDPOINT, this.pushSubscription.endpoint);

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
            sessionStorage.removeItem(STORAGE_WEB_PUSH_ENDPOINT);

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
     * Конвертация VAPID ключа (base64url или одна строка из PEM без заголовков).
     */
    _urlBase64ToUint8Array(base64String) {
        if (typeof base64String !== 'string') {
            throw new TypeError('[PWA] VAPID publicKey: ожидается строка');
        }
        let s = base64String.trim().replace(/^\uFEFF/, '');
        s = s.replace(/[\u200B-\u200D\uFEFF\u00AD\u2060]/g, '');
        if (s.includes('-----BEGIN')) {
            const lines = s.split(/\r?\n/).map((line) => line.trim());
            s = lines
                .filter((line) => line.length > 0 && !line.startsWith('-----'))
                .join('');
        }
        s = s.replace(/\s/g, '');
        if (s.length === 0 || !/^[A-Za-z0-9+/=_-]+$/.test(s)) {
            const bad = s.match(/[^A-Za-z0-9+/=_-]/u);
            const hint = bad
                ? `U+${bad[0].codePointAt(0).toString(16)}`
                : 'empty';
            throw new Error(
                `[PWA] VAPID publicKey: ожидается base64 или base64url (A-Za-z0-9, +, /, -, _, padding =). Проблема: ${hint}. Проверьте push.vapid_public_key.`,
            );
        }
        const padding = '='.repeat((4 - (s.length % 4)) % 4);
        const base64 = (s + padding).replace(/-/g, '+').replace(/_/g, '/');
        let rawData;
        try {
            rawData = window.atob(base64);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            throw new Error(
                `[PWA] VAPID publicKey: неверный base64 (${msg}). Ожидается одна строка base64url как в выводе web-push / vapidkeys.`,
            );
        }
        return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
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
