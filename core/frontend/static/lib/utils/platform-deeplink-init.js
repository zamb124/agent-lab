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

function _handleDeepLink(urlString) {
    if (!urlString) {
        return;
    }
    let parsed;
    try {
        parsed = new URL(urlString);
    } catch {
        return;
    }
    if (!isInternalProductNavigationUrl(parsed)) {
        return;
    }
    const target = hrefForDeepLinkNavigation(parsed, window.location.origin);
    assignInNativeShell(target);
}

function installCapacitorAppUrlOpenListener() {
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
        // Cold start: URL, которым запустили приложение из закрытого состояния
        App.getLaunchUrl().then((result) => {
            if (result?.url) {
                _handleDeepLink(result.url);
            }
        }).catch(() => {
            // getLaunchUrl может упасть на некоторых платформах
        });

        // Warm start: ссылки после того, как приложение уже открыто
        App.addListener('appUrlOpen', (event) => {
            if (!event?.url) {
                return;
            }
            _handleDeepLink(event.url);
        });
    });
}

installCapacitorAppUrlOpenListener();
