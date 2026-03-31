/**
 * Холодное открытие по ссылке (Mail / Safari): Capacitor App → тот же WebView.
 */
import { hrefForDeepLinkNavigation } from './platform-deeplink-paths.js';
import { isInternalProductNavigationUrl, isStandaloneOrNativeAppShell } from './native-app-shell.js';

export { hrefForDeepLinkNavigation } from './platform-deeplink-paths.js';

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
        void App.addListener('appUrlOpen', (event) => {
            if (!event?.url) {
                return;
            }
            let parsed;
            try {
                parsed = new URL(event.url);
            } catch {
                return;
            }
            if (!isInternalProductNavigationUrl(parsed)) {
                return;
            }
            const target = hrefForDeepLinkNavigation(parsed, window.location.origin);
            window.location.assign(target);
        });
    });
}

installCapacitorAppUrlOpenListener();
