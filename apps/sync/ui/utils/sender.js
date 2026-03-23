/**
 * Извлекает user_id отправителя из объекта sender.
 * API возвращает поле user_id (UserBrief); оптимистичные сообщения могут хранить id.
 * @param {object|null|undefined} sender
 * @returns {string|null}
 */
export function senderUserId(sender) {
    return sender?.user_id ?? sender?.id ?? null;
}
