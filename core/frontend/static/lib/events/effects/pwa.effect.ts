/**
 * Эффект PWA.
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
 *   pwa/deployment_version/check_requested — GET /<base>/health и сравнить с persisted/state version.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';
import { platformStorageKey } from '../../utils/storage-keys.js';

declare global {
    interface Window {
        __platformDeferredInstallPrompt__?: {
            prompt: () => Promise<void>;
            userChoice: Promise<{ outcome: string }>;
        } | null;
    }
}

interface BeforeInstallPromptEvent extends Event {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: string }>;
}

function isBeforeInstallPrompt(event: Event): event is BeforeInstallPromptEvent {
    return 'prompt' in event && typeof event.prompt === 'function' && 'userChoice' in event;
}

const VERSION_POLL_MS = 60_000;
const HUMANITEC_CACHE_PREFIX = 'humanitec-';
const DEPLOYMENT_VERSION_STORAGE_KEY = platformStorageKey('core', 'deployment_version');
let reloadPageForTests: (() => void) | null = null;

function _isCapacitorNative(): boolean {
    if (typeof window === 'undefined' || typeof window.Capacitor === 'undefined') {
        return false;
    }
    if (typeof window.Capacitor.isNativePlatform !== 'function') {
        return false;
    }
    return window.Capacitor.isNativePlatform();
}

function _capacitorPlatform(): string {
    if (typeof window === 'undefined' || typeof window.Capacitor === 'undefined') {
        return 'web';
    }
    if (typeof window.Capacitor.getPlatform === 'function') {
        return window.Capacitor.getPlatform();
    }
    return 'web';
}

function _urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const output = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i += 1) {
        output[i] = rawData.charCodeAt(i);
    }
    return output;
}

function vapidApplicationServerKey(publicKey: string): ArrayBuffer {
    const bytes = _urlBase64ToUint8Array(publicKey);
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    return buffer;
}

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) return err.message;
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
    return String(err);
}

function isReloadCallback(fn: unknown): fn is () => void {
    return typeof fn === 'function';
}

function nonEmptyString(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

function pushKey(subscription: PushSubscription, name: PushEncryptionKeyName): ArrayBuffer {
    const key = subscription.getKey(name);
    if (key === null) {
        throw new Error(`pwa: push key ${name} missing`);
    }
    return key;
}

function _arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i += 1) {
        const byte = bytes[i];
        if (byte === undefined) {
            throw new Error('pwa: byte missing');
        }
        binary += String.fromCharCode(byte);
    }
    return btoa(binary);
}

async function _registerNativePush(base: string, transport: string, platformLabel: string): Promise<{ transport: string; deviceToken: string }> {
    const { PushNotifications } = await import('@capacitor/push-notifications');
    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') {
        throw new Error('push permission denied');
    }
    const tokenPromise = new Promise<string>((resolve, reject) => {
        const onRegistration = PushNotifications.addListener('registration', (token: { value: string }) => {
            void onRegistration.then((handle) => handle.remove());
            void onError.then((handle) => handle.remove());
            resolve(token.value);
        });
        const onError = PushNotifications.addListener('registrationError', (err: { error?: unknown }) => {
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

async function _registerWebPush(base: string): Promise<{ transport: string; endpoint: string }> {
    const reg = await navigator.serviceWorker.ready;
    if (!reg) {
        throw new Error('service worker not ready');
    }
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
        return { transport: 'web_vapid', endpoint: existing.endpoint };
    }
    const vapid = await httpRequest({ method: 'GET', url: `${base}/api/push/vapid-public-key` });
    const publicKey = isPlainRecord(vapid) ? vapid.publicKey : undefined;
    if (typeof publicKey !== 'string' || publicKey.length === 0) {
        throw new Error('VAPID public key недоступен');
    }
    const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: vapidApplicationServerKey(publicKey),
    });
    const json = subscription.toJSON();
    const keys = json.keys === undefined ? {} : json.keys;
    await httpRequest({
        method: 'POST',
        url: `${base}/api/push/subscribe`,
        body: {
            transport: 'web_vapid',
            endpoint: subscription.endpoint,
            keys: {
                p256dh: keys.p256dh || _arrayBufferToBase64(pushKey(subscription, 'p256dh')),
                auth: keys.auth || _arrayBufferToBase64(pushKey(subscription, 'auth')),
            },
            platform: 'web',
        },
    });
    return { transport: 'web_vapid', endpoint: subscription.endpoint };
}

async function _deleteHumanitecCaches() {
    if (typeof caches === 'undefined') {
        return;
    }
    const names = await caches.keys();
    const toDelete = names.filter((name) => name.startsWith(HUMANITEC_CACHE_PREFIX));
    await Promise.all(toDelete.map((name) => caches.delete(name)));
}

function _browserStorage(): Storage | null {
    if (typeof window !== 'undefined' && window.localStorage) {
        return window.localStorage;
    }
    if (typeof globalThis !== 'undefined' && globalThis.localStorage) {
        return globalThis.localStorage;
    }
    return null;
}

function _readStoredDeploymentVersion(): string | null {
    const storage = _browserStorage();
    if (!storage) {
        return null;
    }
    const value = storage.getItem(DEPLOYMENT_VERSION_STORAGE_KEY);
    return typeof value === 'string' && value.length > 0 ? value : null;
}

function _writeStoredDeploymentVersion(version: unknown): void {
    if (typeof version !== 'string' || version.length === 0) {
        return;
    }
    const storage = _browserStorage();
    if (!storage) {
        return;
    }
    storage.setItem(DEPLOYMENT_VERSION_STORAGE_KEY, version);
}

async function _fetchDeploymentVersion(base: string): Promise<string | null> {
    const normalizedBase = typeof base === 'string' ? base.replace(/\/+$/, '') : '';
    const healthUrl = `${normalizedBase}/health`;
    const response = await fetch(healthUrl, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        headers: {
            Accept: 'application/json',
            'Cache-Control': 'no-cache',
        },
    });
    if (!response.ok) {
        throw new Error(`deployment version check failed: HTTP ${response.status}`);
    }
    const data: unknown = await response.json();
    if (!isPlainRecord(data)) {
        throw new Error('deployment version check failed: JSON object required');
    }
    return nonEmptyString(data.deployment_version) ?? nonEmptyString(data.version);
}

async function _reloadAfterDeployment(version: unknown): Promise<void> {
    _writeStoredDeploymentVersion(version);
    await _deleteHumanitecCaches();
    const sw = typeof navigator !== 'undefined' && navigator.serviceWorker;
    if (sw && typeof sw.getRegistration === 'function') {
        const reg = await sw.getRegistration();
        if (reg) {
            if (typeof reg.update === 'function') {
                await reg.update();
            }
            if (reg.waiting && typeof reg.waiting.postMessage === 'function') {
                reg.waiting.postMessage({ type: 'skipWaiting' });
            }
        }
    }
    _reloadPage();
}

function _reloadPage() {
    if (typeof reloadPageForTests === 'function') {
        reloadPageForTests();
        return;
    }
    if (typeof location !== 'undefined' && typeof location.reload === 'function') {
        location.reload();
    }
}

export function _setPwaReloadForTests(fn: unknown): void {
    reloadPageForTests = isReloadCallback(fn) ? fn : null;
}

function _handleServiceWorkerMessage(event: MessageEvent): void {
    const data = event.data;
    if (!isPlainRecord(data)) {
        return;
    }
    if (data.type === 'humanitec-deployment-updated') {
        void _reloadAfterDeployment(data.to);
    }
    if (data.type === 'humanitec-deployment-reload-requested') {
        void _reloadAfterDeployment(null);
    }
}

function _registerServiceWorker(): void {
    if (_isCapacitorNative()) {
        return;
    }
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
        return;
    }
    const sw = navigator.serviceWorker;
    if (!sw || typeof sw.register !== 'function') {
        return;
    }
    void sw.register('/sw.js', { scope: '/' });
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

export function createPwaEffect({ baseUrl, suppressHostIntegrations }: { baseUrl?: string; suppressHostIntegrations?: boolean } = {}): (event: PlatformEvent, ctx: EffectCtx<{ pwa?: { deploymentVersion?: string | null } }>) => Promise<void> {
    const base = typeof baseUrl === 'string' ? baseUrl : '';
    const suppressHost = Boolean(suppressHostIntegrations);
    let attached = false;
    let versionTimer: ReturnType<typeof setInterval> | null = null;

    function _scheduleVersionCheck(ctx: EffectCtx<{ pwa?: { deploymentVersion?: string | null } }>): void {
        if (versionTimer) return;
        versionTimer = setInterval(() => {
            ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED, null, { source: 'timer' });
        }, VERSION_POLL_MS);
        ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED, null, { source: 'system' });
    }

    return async function pwaEffect(event: PlatformEvent, ctx: EffectCtx<{ pwa?: { deploymentVersion?: string | null } }>): Promise<void> {
        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                if (suppressHost) {
                    return;
                }
                if (!attached) {
                    attached = true;
                    if (typeof Notification !== 'undefined' && Notification.permission) {
                        ctx.dispatch(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, { permission: Notification.permission }, { source: 'system' });
                    }
                    window.addEventListener('beforeinstallprompt', (e) => {
                        e.preventDefault();
                        if (!isBeforeInstallPrompt(e)) {
                            throw new Error('pwa: beforeinstallprompt event has no prompt method');
                        }
                        window.__platformDeferredInstallPrompt__ = e;
                        ctx.dispatch(CoreEvents.PWA_INSTALL_AVAILABLE, null, { source: 'system' });
                    });
                    window.addEventListener('appinstalled', () => {
                        ctx.dispatch(CoreEvents.PWA_INSTALLED, null, { source: 'system' });
                    });
                    _registerServiceWorker();
                    const sw = typeof navigator !== 'undefined' && navigator.serviceWorker;
                    if (sw && typeof sw.addEventListener === 'function') {
                        sw.addEventListener('message', _handleServiceWorkerMessage);
                    }
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
                        { message: errorMessage(err) },
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
                    const version = await _fetchDeploymentVersion(base);
                    const stateVersion = ctx.getState().pwa?.deploymentVersion;
                    const storedVersion = _readStoredDeploymentVersion();
                    ctx.dispatch(PWA_EVENTS.DEPLOYMENT_VERSION_LOADED, { version }, { causation_id: event.id, source: 'http' });
                    if (storedVersion && version && storedVersion !== version) {
                        ctx.dispatch(CoreEvents.PWA_UPDATE_AVAILABLE, { from: storedVersion, to: version }, { causation_id: event.id });
                        await _reloadAfterDeployment(version);
                        return;
                    }
                    if (stateVersion && version && stateVersion !== version) {
                        ctx.dispatch(CoreEvents.PWA_UPDATE_AVAILABLE, { from: stateVersion, to: version }, { causation_id: event.id });
                        await _reloadAfterDeployment(version);
                        return;
                    }
                    if (version) {
                        _writeStoredDeploymentVersion(version);
                    }
                } catch (err) {
                    ctx.dispatch(
                        PWA_EVENTS.DEPLOYMENT_VERSION_LOAD_FAILED,
                        { message: errorMessage(err) },
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
