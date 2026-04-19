/**
 * PWA effect.
 *
 * Слушает:
 *   ui/app/bootstrap_started               — установить window-listeners (beforeinstallprompt, appinstalled), запустить polling deployment version, прочитать notification permission.
 *   pwa/install/prompt_requested           — показать deferred prompt.
 *   pwa/push/permission_request_requested  — Notification.requestPermission().
 *   pwa/push/subscribe_requested           — выбор транспорта по платформе:
 *     - native iOS (Capacitor)     -> PushNotifications.register() -> POST /api/push/subscribe transport=ios_apns
 *     - native Android (Capacitor) -> PushNotifications.register() -> POST /api/push/subscribe transport=android_fcm
 *     - браузер / PWA              -> Service Worker + VAPID       -> POST /api/push/subscribe transport=web_vapid
 *   pwa/push/unsubscribe_requested         — отписаться (web: pushManager; native: реализуется отдельно).
 *   pwa/deployment_version/check_requested — GET /<base>/health и сравнить с текущей.
 */

import { CoreEvents } from '../contract.js';
import { httpRequest } from '../http.js';

const VERSION_POLL_MS = 60_000;

function _isCapacitorNative() {
    if (typeof window === 'undefined' || typeof window.Capacitor === 'undefined') {
        return false;
    }
    if (typeof window.Capacitor.isNativePlatform !== 'function') {
        return false;
    }
    return window.Capacitor.isNativePlatform();
}

function _capacitorPlatform() {
    if (typeof window === 'undefined' || typeof window.Capacitor === 'undefined') {
        return 'web';
    }
    if (typeof window.Capacitor.getPlatform === 'function') {
        return window.Capacitor.getPlatform();
    }
    return 'web';
}

function _urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const output = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i += 1) {
        output[i] = rawData.charCodeAt(i);
    }
    return output;
}

function _arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i += 1) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

async function _registerNativePush(base, transport, platformLabel) {
    const { PushNotifications } = await import('@capacitor/push-notifications');
    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') {
        throw new Error('push permission denied');
    }
    const tokenPromise = new Promise((resolve, reject) => {
        const onRegistration = PushNotifications.addListener('registration', (token) => {
            void onRegistration.then((handle) => handle.remove());
            void onError.then((handle) => handle.remove());
            resolve(token.value);
        });
        const onError = PushNotifications.addListener('registrationError', (err) => {
            void onRegistration.then((handle) => handle.remove());
            void onError.then((handle) => handle.remove());
            reject(new Error(err && err.error ? String(err.error) : 'push registration error'));
        });
    });
    await PushNotifications.register();
    const deviceToken = await tokenPromise;
    await httpRequest({
        method: 'POST',
        url: `${base}/api/push/subscribe`,
        body: {
            transport,
            endpoint: '',
            keys: { device_token: deviceToken },
            platform: platformLabel,
        },
    });
    return { transport, deviceToken };
}

async function _registerWebPush(base) {
    const reg = await navigator.serviceWorker.ready;
    if (!reg) {
        throw new Error('service worker not ready');
    }
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
        return { transport: 'web_vapid', endpoint: existing.endpoint };
    }
    const vapid = await httpRequest({ method: 'GET', url: `${base}/api/push/vapid-public-key` });
    const publicKey = vapid && vapid.publicKey;
    if (!publicKey) {
        throw new Error('VAPID public key недоступен');
    }
    const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(publicKey),
    });
    const json = subscription.toJSON();
    const keys = (json && json.keys) || {};
    await httpRequest({
        method: 'POST',
        url: `${base}/api/push/subscribe`,
        body: {
            transport: 'web_vapid',
            endpoint: subscription.endpoint,
            keys: {
                p256dh: keys.p256dh || _arrayBufferToBase64(subscription.getKey('p256dh')),
                auth: keys.auth || _arrayBufferToBase64(subscription.getKey('auth')),
            },
            platform: 'web',
        },
    });
    return { transport: 'web_vapid', endpoint: subscription.endpoint };
}

export const PWA_EVENTS = Object.freeze({
    INSTALL_PROMPT_REQUESTED:        'pwa/install/prompt_requested',
    PUSH_PERMISSION_REQUEST_REQUESTED:'pwa/push/permission_request_requested',
    PUSH_SUBSCRIBE_REQUESTED:        'pwa/push/subscribe_requested',
    PUSH_SUBSCRIBE_FAILED:           'pwa/push/subscribe_failed',
    PUSH_UNSUBSCRIBE_REQUESTED:      'pwa/push/unsubscribe_requested',
    PUSH_UNSUBSCRIBED:               'pwa/push/unsubscribed',
    DEPLOYMENT_VERSION_CHECK_REQUESTED: 'pwa/deployment_version/check_requested',
    DEPLOYMENT_VERSION_LOADED:       'pwa/deployment_version/loaded',
    DEPLOYMENT_VERSION_LOAD_FAILED:  'pwa/deployment_version/load_failed',
});

export function createPwaEffect({ baseUrl } = {}) {
    const base = baseUrl || '';
    let attached = false;
    let versionTimer = null;

    function _scheduleVersionCheck(ctx) {
        if (versionTimer) return;
        versionTimer = setInterval(() => {
            ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED, null, { source: 'timer' });
        }, VERSION_POLL_MS);
        ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED, null, { source: 'system' });
    }

    return async function pwaEffect(event, ctx) {
        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                if (!attached) {
                    attached = true;
                    if (typeof Notification !== 'undefined' && Notification.permission) {
                        ctx.dispatch(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, { permission: Notification.permission }, { source: 'system' });
                    }
                    window.addEventListener('beforeinstallprompt', (e) => {
                        e.preventDefault();
                        window.__platformDeferredInstallPrompt__ = e;
                        ctx.dispatch(CoreEvents.PWA_INSTALL_AVAILABLE, null, { source: 'system' });
                    });
                    window.addEventListener('appinstalled', () => {
                        ctx.dispatch(CoreEvents.PWA_INSTALLED, null, { source: 'system' });
                    });
                }
                _scheduleVersionCheck(ctx);
                return;
            }

            case PWA_EVENTS.INSTALL_PROMPT_REQUESTED: {
                const prompt = window.__platformDeferredInstallPrompt__;
                if (!prompt) return;
                try {
                    await prompt.prompt();
                    const choice = await prompt.userChoice;
                    if (choice && choice.outcome === 'accepted') {
                        ctx.dispatch(CoreEvents.PWA_INSTALLED, null, { causation_id: event.id, source: 'system' });
                    }
                } finally {
                    window.__platformDeferredInstallPrompt__ = null;
                }
                return;
            }

            case PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED: {
                if (_isCapacitorNative()) {
                    const { PushNotifications } = await import('@capacitor/push-notifications');
                    const result = await PushNotifications.requestPermissions();
                    ctx.dispatch(
                        CoreEvents.PWA_PUSH_PERMISSION_REQUESTED,
                        { permission: result.receive === 'granted' ? 'granted' : 'denied' },
                        { causation_id: event.id, source: 'system' },
                    );
                    return;
                }
                if (typeof Notification === 'undefined') return;
                const perm = await Notification.requestPermission();
                ctx.dispatch(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, { permission: perm }, { causation_id: event.id, source: 'system' });
                return;
            }

            case PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED: {
                try {
                    let result;
                    if (_isCapacitorNative()) {
                        const platform = _capacitorPlatform();
                        if (platform === 'ios') {
                            result = await _registerNativePush(base, 'ios_apns', 'ios_native');
                        } else if (platform === 'android') {
                            result = await _registerNativePush(base, 'android_fcm', 'android_native');
                        } else {
                            return;
                        }
                        ctx.dispatch(
                            CoreEvents.PWA_PUSH_REGISTERED,
                            { endpoint: `${result.transport === 'ios_apns' ? 'apns' : 'fcm'}:${result.deviceToken}`, transport: result.transport },
                            { causation_id: event.id, source: 'system' },
                        );
                        return;
                    }
                    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
                    result = await _registerWebPush(base);
                    ctx.dispatch(
                        CoreEvents.PWA_PUSH_REGISTERED,
                        { endpoint: result.endpoint, transport: 'web_vapid' },
                        { causation_id: event.id, source: 'system' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        PWA_EVENTS.PUSH_SUBSCRIBE_FAILED,
                        { message: String(err && err.message ? err.message : err) },
                        { causation_id: event.id, source: 'system' },
                    );
                }
                return;
            }

            case PWA_EVENTS.PUSH_UNSUBSCRIBE_REQUESTED: {
                if (!('serviceWorker' in navigator)) return;
                const reg = await navigator.serviceWorker.ready;
                if (!reg) return;
                const existing = await reg.pushManager.getSubscription();
                if (existing) {
                    await existing.unsubscribe();
                }
                ctx.dispatch(PWA_EVENTS.PUSH_UNSUBSCRIBED, null, { causation_id: event.id, source: 'system' });
                return;
            }

            case PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/health` });
                    const version = (data && (data.deployment_version || data.version)) || null;
                    const cur = ctx.getState().pwa.deploymentVersion;
                    ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_LOADED, { version }, { causation_id: event.id, source: 'http' });
                    if (cur && version && cur !== version) {
                        ctx.dispatch(CoreEvents.PWA_UPDATE_AVAILABLE, { from: cur, to: version }, { causation_id: event.id });
                    }
                } catch (err) {
                    ctx.dispatch(
                        PWA_EVENTS.DEPLOYMENT_VERSION_LOAD_FAILED,
                        { message: String(err && err.message ? err.message : err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }

            default:
                return;
        }
    };
}
