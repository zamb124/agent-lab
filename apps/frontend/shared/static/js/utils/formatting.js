/**
 * Утилиты форматирования
 */

export function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function formatDate(date, locale = 'ru-RU') {
    if (!date) return '—';
    return new Date(date).toLocaleDateString(locale);
}

export function formatDateTime(date, locale = 'ru-RU') {
    if (!date) return '—';
    return new Date(date).toLocaleString(locale);
}

export function formatCurrency(amount, currency = '₽') {
    if (amount === null || amount === undefined) return '—';
    return `${amount.toFixed(2)} ${currency}`;
}

export function truncateText(text, maxLength = 100) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

