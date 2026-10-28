/**
 * Единый справочник типов триггера: иконка platform-icon и semantic tokens.
 */

export const TRIGGER_TYPES = Object.freeze([
    { id: 'telegram', icon: 'send', color: 'var(--info)', bg: 'var(--info-bg)', nameKey: 'type_telegram', descKey: 'type_telegram_desc' },
    { id: 'cron', icon: 'clock', color: 'var(--warning)', bg: 'var(--warning-bg)', nameKey: 'type_cron', descKey: 'type_cron_desc' },
    { id: 'webhook', icon: 'globe', color: 'var(--accent)', bg: 'var(--accent-subtle)', nameKey: 'type_webhook', descKey: 'type_webhook_desc' },
    { id: 'email', icon: 'mail', color: 'var(--error)', bg: 'var(--error-bg)', nameKey: 'type_email', descKey: 'type_email_desc' },
    { id: 'platform_event', icon: 'zap', color: 'var(--accent-secondary)', bg: 'color-mix(in srgb, var(--accent-secondary) 18%, transparent)', nameKey: 'type_platform_event', descKey: 'type_platform_event_desc' },
]);

/**
 * @param {unknown} typeId
 * @returns {{ icon: string, wrapBg: string, wrapFg: string }}
 */
export function getTriggerTypeRowVisual(typeId: any) {
    const id = typeof typeId === 'string' ? typeId.trim() : '';
    const found = TRIGGER_TYPES.find((t) => t.id === id);
    if (found) {
        return {
            icon: found.icon,
            wrapBg: found.bg,
            wrapFg: found.color,
        };
    }
    return {
        icon: 'bell-ring',
        wrapBg: 'var(--glass-solid-medium)',
        wrapFg: 'var(--text-tertiary)',
    };
}
