/**
 * Тосты хода агента для страниц без блока ``conversation``: пока Task стримит —
 * «агент работает» с активностью инструментов, после — ответ или ошибка.
 */

import { conversationTurn, type FlowUiSettings } from './conversation.js';
import { flowUIText } from '../utils/text.js';

/**
 * @returns {readonly { id: string, kind: 'working' | 'response' | 'error', title: string, body: string,
 *   streaming: boolean, canCancel: boolean, dismissible: boolean }[]}
 */
export interface TurnToast {
    id: string;
    kind: 'working' | 'response' | 'error';
    title: string;
    body: string;
    streaming: boolean;
    canCancel: boolean;
    dismissible: boolean;
}

export function deriveTurnToasts(
    store: { task: (id: string | null) => Record<string, unknown> | null | undefined; activeTaskId: string | null },
    settings: FlowUiSettings,
    locale: string,
    { allowCancel = false }: { allowCancel?: boolean } = {},
): readonly TurnToast[] {
    const task = store.task(store.activeTaskId);
    if (!task) return Object.freeze([]);
    const turn = conversationTurn(task, settings, locale);
    if (!turn.settled) {
        const running = turn.activity.filter((item) => item.kind !== 'error').map((item) => item.label);
        return Object.freeze([{
            id: `working:${turn.taskId}`,
            kind: 'working',
            title: flowUIText(locale, 'turn_toast_working'),
            body: running.slice(-3).join(' · '),
            streaming: true,
            canCancel: allowCancel,
            dismissible: false,
        }]);
    }
    if (turn.error !== '') {
        return Object.freeze([{
            id: `error:${turn.taskId}`,
            kind: 'error',
            title: flowUIText(locale, 'turn_toast_error'),
            body: turn.error,
            streaming: false,
            canCancel: false,
            dismissible: true,
        }]);
    }
    if (turn.text !== '') {
        return Object.freeze([{
            id: `response:${turn.taskId}`,
            kind: 'response',
            title: flowUIText(locale, 'turn_toast_response'),
            body: turn.text.length > 280 ? `${turn.text.slice(0, 280)}…` : turn.text,
            streaming: false,
            canCancel: false,
            dismissible: true,
        }]);
    }
    return Object.freeze([]);
}
