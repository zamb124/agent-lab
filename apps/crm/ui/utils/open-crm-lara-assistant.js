/**
 * Открывает встроенную панель Lara (crm-app: platform-chat display="drawer", toggle-event-name="crm-lara-open").
 */
import { dispatchEmbedChatWindowToggle } from '@platform/lib/chat/chat-window-toggle.js';

export function openCrmLaraAssistant() {
    dispatchEmbedChatWindowToggle('crm-lara-open', { open: true });
}
