/**
 * Открывает встроенную панель Lara (crm-app: platform-lara-assistant, toggle-event-name="crm-lara-open").
 */
export function openCrmLaraAssistant() {
    window.dispatchEvent(new CustomEvent('crm-lara-open', { detail: { open: true } }));
}
