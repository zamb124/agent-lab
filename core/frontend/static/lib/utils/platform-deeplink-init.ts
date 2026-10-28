/**
 * Холодное открытие по ссылке (Mail / Safari): Capacitor App → тот же WebView.
 */
import { hrefForDeepLinkNavigation } from './platform-deeplink-paths.js';
import {
    assignInNativeShell,
    isInternalProductNavigationUrl,
    isStandaloneOrNativeAppShell,
} from './native-app-shell.js';

export { hrefForDeepLinkNavigation } from './platform-deeplink-paths.js';

function _handleDeepLink(urlString: string | null | undefined): void {
    if (!urlString) {
        return;
    }
    const parsed = new URL(urlString);
    if (!isInternalProductNavigationUrl(parsed)) {
        return;
    }
    const target = hrefForDeepLinkNavigation(parsed, window.location.origin);
    assignInNativeShell(target);
}

function installCapacitorAppUrlOpenListener(): void {
    if (typeof window === 'undefined') {
        return;
    }
    if (!isStandaloneOrNativeAppShell()) {
        return;
    }
    if (typeof window.Capacitor === 'undefined') {
        return;
    }
    if (typeof window.Capacitor.isNativePlatform === 'function' && !window.Capacitor.isNativePlatform()) {
        return;
    }

    void import('@capacitor/app').then(({ App }) => {
        // Холодный старт: URL, которым запустили приложение из закрытого состояния
        App.getLaunchUrl().then((result: { url?: string }) => {
            if (result?.url) {
                _handleDeepLink(result.url);
            }
        }).catch(() => {
            // getLaunchUrl может упасть на некоторых платформах
        });

        // Тёплый старт: ссылки после того, как приложение уже открыто
        App.addListener('appUrlOpen', (event: { url?: string }) => {
            if (!event?.url) {
                return;
            }
            _handleDeepLink(event.url);
        });
    });
}

installCapacitorAppUrlOpenListener();
