/**
 * Утилиты для генерации UUID
 */

export function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substr(2, 9);
    return `${timestamp}_${random}`;
}

export function generateSessionId(prefix = '') {
    const uuid = generateUUID();
    return prefix ? `${prefix}_${uuid}` : uuid;
}

