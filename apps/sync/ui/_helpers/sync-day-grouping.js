/**
 * Хелперы группировки по дням Sync — группировка ленты сообщений по дням и
 * по «отправитель + соседство по времени» (sender grouping window).
 *
 * Чистые функции; работают с уже отсортированной по `sent_at` лентой.
 */

const SENDER_WINDOW_MS = 120_000;

function _dayKey(iso) {
    if (typeof iso !== 'string' || iso === '') return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function _isToday(iso) {
    if (typeof iso !== 'string' || iso === '') return false;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return false;
    const now = new Date();
    return date.toDateString() === now.toDateString();
}

function _isYesterday(iso) {
    if (typeof iso !== 'string' || iso === '') return false;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return false;
    const y = new Date();
    y.setDate(y.getDate() - 1);
    return date.toDateString() === y.toDateString();
}

/**
 * Возвращает массив [{ kind:'day', label, key }, { kind:'message', message, position }]:
 * label — локализованная строка дня, position — 'first' | 'middle' | 'last' | 'single'.
 */
export function groupMessagesForRender(messages, t) {
    if (!Array.isArray(messages) || messages.length === 0) return [];
    const out = [];
    let currentDayKey = null;
    for (let i = 0; i < messages.length; i += 1) {
        const m = messages[i];
        if (!m || typeof m !== 'object') continue;
        const dayKey = _dayKey(m.sent_at);
        if (dayKey !== currentDayKey) {
            currentDayKey = dayKey;
            let label = '';
            if (_isToday(m.sent_at)) label = t('message_list.today');
            else if (_isYesterday(m.sent_at)) label = t('message_list.yesterday');
            else if (typeof m.sent_at === 'string') {
                const dt = new Date(m.sent_at);
                if (!Number.isNaN(dt.getTime())) {
                    label = dt.toLocaleDateString();
                }
            }
            out.push({ kind: 'day', label, key: dayKey });
        }
        const prev = messages[i - 1];
        const next = messages[i + 1];
        const prevSenderSame = !!(prev && prev.sender && m.sender && prev.sender.user_id === m.sender.user_id);
        const nextSenderSame = !!(next && next.sender && m.sender && next.sender.user_id === m.sender.user_id);
        const prevDaySame = prev ? _dayKey(prev.sent_at) === dayKey : false;
        const nextDaySame = next ? _dayKey(next.sent_at) === dayKey : false;
        const prevTimeClose = prev && prev.sent_at && m.sent_at
            ? Math.abs(new Date(m.sent_at).getTime() - new Date(prev.sent_at).getTime()) <= SENDER_WINDOW_MS
            : false;
        const nextTimeClose = next && next.sent_at && m.sent_at
            ? Math.abs(new Date(next.sent_at).getTime() - new Date(m.sent_at).getTime()) <= SENDER_WINDOW_MS
            : false;
        const groupedWithPrev = prevSenderSame && prevDaySame && prevTimeClose;
        const groupedWithNext = nextSenderSame && nextDaySame && nextTimeClose;
        let position = 'single';
        if (groupedWithPrev && groupedWithNext) position = 'middle';
        else if (groupedWithPrev) position = 'last';
        else if (groupedWithNext) position = 'first';
        out.push({ kind: 'message', message: m, position });
    }
    return out;
}

export { SENDER_WINDOW_MS };
