/**
 * Сигнал на window для platform-embed-chat-drawer (toggle-event-name).
 * CustomEvent создаётся здесь, в core, а не в apps (check_ui_canon).
 */
export function dispatchEmbedChatWindowToggle(eventName, detail) {
    if (typeof eventName !== 'string' || eventName.length === 0) {
        throw new Error('dispatchEmbedChatWindowToggle: eventName must be non-empty string');
    }
    if (typeof window === 'undefined') {
        throw new Error('dispatchEmbedChatWindowToggle: window is undefined');
    }
    const d = typeof detail === 'object' && detail !== null ? detail : {};
    window.dispatchEvent(new CustomEvent(eventName, { detail: d }));
}
