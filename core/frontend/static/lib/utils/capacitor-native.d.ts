/**
 * Ambient-типы плагинов, доступных только внутри нативного webview Capacitor.
 * На web guard `window.Capacitor.isNativePlatform()` не даёт дойти до импорта.
 */
declare module '@capacitor/splash-screen' {
    export const SplashScreen: { hide(): Promise<void>; show(options?: { autoHide?: boolean }): Promise<void> };
}

declare module '@capacitor/app' {
    export const App: {
        getLaunchUrl(): Promise<{ url?: string }>;
        addListener(event: string, cb: (event: { url?: string }) => void): void;
    };
}

declare module '@capacitor/push-notifications' {
    export interface PluginListenerHandle { remove(): Promise<void> }
    export const PushNotifications: {
        requestPermissions(): Promise<{ receive: 'granted' | 'denied' | 'prompt' | string }>;
        register(): Promise<void>;
        addListener(event: 'registration', cb: (token: { value: string }) => void): Promise<PluginListenerHandle>;
        addListener(event: 'registrationError', cb: (err: { error?: unknown }) => void): Promise<PluginListenerHandle>;
        addListener(event: string, cb: (data: unknown) => void): Promise<PluginListenerHandle>;
    };
}
