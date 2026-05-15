/**
 * Открывает встроенную панель Lara (crm-app: platform-lara-assistant, toggle-event-name="crm-lara-open").
 */
import { dispatchEmbedChatWindowToggle } from '@platform/lib/embed-chat/embed-chat-window-toggle.js';

export function openCrmLaraAssistant() {
    dispatchEmbedChatWindowToggle('crm-lara-open', { open: true });
}
