/**
 * Единый справочник типов триггера: иконка platform-icon и цвет (как в редакторе).
 */

export const TRIGGER_TYPES = Object.freeze([
    { id: 'telegram', icon: 'send', color: '#0088cc', nameKey: 'type_telegram', descKey: 'type_telegram_desc' },
    { id: 'cron', icon: 'clock', color: '#f59e0b', nameKey: 'type_cron', descKey: 'type_cron_desc' },
    { id: 'webhook', icon: 'globe', color: '#8b5cf6', nameKey: 'type_webhook', descKey: 'type_webhook_desc' },
    { id: 'email', icon: 'mail', color: '#ea4335', nameKey: 'type_email', descKey: 'type_email_desc' },
    { id: 'redis', icon: 'database', color: '#dc382d', nameKey: 'type_redis', descKey: 'type_redis_desc' },
]);

/**
 * @param {unknown} typeId
 * @returns {{ icon: string, wrapBg: string, wrapFg: string }}
 */
export function getTriggerTypeRowVisual(typeId) {
    const id = typeof typeId === 'string' ? typeId.trim() : '';
    const found = TRIGGER_TYPES.find((t) => t.id === id);
    if (found) {
        return {
            icon: found.icon,
            wrapBg: `${found.color}20`,
            wrapFg: found.color,
        };
    }
    return {
        icon: 'bell-ring',
        wrapBg: 'var(--glass-solid-medium)',
        wrapFg: 'var(--text-tertiary)',
    };
}
