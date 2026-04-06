/**
 * Строки UI embed-чата без i18n хоста (внешний сайт / любой shell).
 */

/** @type {Record<string, Record<string, string>>} */
export const EMBED_CHAT_DEFAULT_LABELS = {
    ru: {
        title: 'Ассистент',
        fab_aria_open: 'Открыть чат',
        fab_aria_close: 'Закрыть панель',
        panel_close: 'Закрыть',
        greeting:
            'Привет. Могу отвечать по данным из подключённых инструментов. Задайте вопрос или приложите файл.',
        placeholder: 'Сообщение…',
        send: 'Отправить',
        new_chat: 'Новый чат',
        voice_title: 'Голосовой ввод',
        voice_not_supported: 'Голосовой ввод не поддерживается в этом браузере',
    },
    en: {
        title: 'Assistant',
        fab_aria_open: 'Open chat',
        fab_aria_close: 'Close panel',
        panel_close: 'Close',
        greeting: 'Hi. Ask a question or attach a file — answers use your flow tools.',
        placeholder: 'Message…',
        send: 'Send',
        new_chat: 'New chat',
        voice_title: 'Voice input',
        voice_not_supported: 'Voice input is not supported in this browser',
    },
};

/**
 * @param {string} [lang] - например document.documentElement.lang
 * @returns {Record<string, string>}
 */
export function embedChatLabelsForLang(lang) {
    const raw = (lang || 'ru').toLowerCase();
    const key = raw.startsWith('en') ? 'en' : 'ru';
    return { ...EMBED_CHAT_DEFAULT_LABELS[key] };
}
