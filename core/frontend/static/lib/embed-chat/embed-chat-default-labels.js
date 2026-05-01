/**
 * Строки UI embed-чата без i18n хоста (внешний сайт / любой shell).
 */

/** @type {Record<string, Record<string, string>>} */
export const EMBED_CHAT_DEFAULT_LABELS = {
    ru: {
        title: 'Ассистент',
        fab_aria_open: 'Открыть чат',
        fab_aria_open_unread: 'Открыть чат, новых ответов: {count}',
        fab_aria_close: 'Закрыть панель',
        panel_close: 'Закрыть',
        panel_minimize: 'Свернуть',
        panel_fullscreen: 'Расширить окно',
        panel_exit_fullscreen: 'Обычный размер',
        greeting:
            'Привет. Могу отвечать по данным из подключённых инструментов. Задайте вопрос или приложите файл.',
        placeholder: 'Сообщение…',
        attach: 'Вложения',
        send: 'Отправить',
        new_chat: 'Новый чат',
        voice_title: 'Голосовой ввод',
        voice_not_supported: 'Голосовой ввод не поддерживается в этом браузере',
        locale_auto: 'Авто',
        locale_ru: 'Русский',
        locale_en: 'English',
        ai_disclaimer: 'Содержимое, созданное ИИ, может быть неточным.',
        interrupt_operator_banner: 'Ожидается действие оператора. Диалог на паузе.',
        interrupt_oauth_banner: 'Требуется авторизация во внешнем сервисе',
        interrupt_oauth_button: 'Авторизоваться',
        integration_badge_title: 'Подключено: {provider} / {service}',
        integration_disconnect: 'Отключить',
        operator_reply_heading: 'Оператор',
        download_file: 'Скачать',
        tool_default_name: 'инструмент',
        tool_stack_aria: 'Вызовы инструментов: {names}',
        tool_hint_tool_name: 'Инструмент: {name}',
        tool_hint_args_label: 'Аргументы:',
        tool_hint_result_label: 'Результат:',
        attachment_remove: 'Убрать файл',
        attachment_clear_all: 'Удалить все вложения',
    },
    en: {
        title: 'Assistant',
        fab_aria_open: 'Open chat',
        fab_aria_open_unread: 'Open chat, new replies: {count}',
        fab_aria_close: 'Close panel',
        panel_close: 'Close',
        panel_minimize: 'Minimize',
        panel_fullscreen: 'Expand panel',
        panel_exit_fullscreen: 'Normal size',
        greeting: 'Hi. Ask a question or attach a file — answers use your flow tools.',
        placeholder: 'Message…',
        attach: 'Attachments',
        send: 'Send',
        new_chat: 'New chat',
        voice_title: 'Voice input',
        voice_not_supported: 'Voice input is not supported in this browser',
        locale_auto: 'Auto',
        locale_ru: 'Russian',
        locale_en: 'English',
        ai_disclaimer: 'AI-generated content may be inaccurate.',
        interrupt_operator_banner: 'Waiting for an operator. The chat is on hold.',
        interrupt_oauth_banner: 'External service authorization required',
        interrupt_oauth_button: 'Authorize',
        integration_badge_title: 'Connected: {provider} / {service}',
        integration_disconnect: 'Disconnect',
        operator_reply_heading: 'Operator',
        download_file: 'Download',
        tool_default_name: 'tool',
        tool_stack_aria: 'Tool calls: {names}',
        tool_hint_tool_name: 'Tool: {name}',
        tool_hint_args_label: 'Arguments:',
        tool_hint_result_label: 'Result:',
        attachment_remove: 'Remove file',
        attachment_clear_all: 'Remove all attachments',
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

/**
 * Переменные для metadata.variables A2A (CRM / Lara): совпадают с бэкендом EntityService.
 * @param {string} [locale] - атрибут locale drawer или пусто → document.documentElement.lang
 * @returns {{ interface_language_code: 'ru'|'en', interface_language_name: string }}
 */
export function crmA2aInterfaceLanguageVariables(locale) {
    const raw = String(locale || '').trim().toLowerCase();
    const docLang =
        typeof document !== 'undefined'
            ? String(document.documentElement.getAttribute('lang') || '').trim().toLowerCase()
            : '';
    const combined = !raw || raw === 'auto' ? docLang || 'ru' : raw;
    const primary = combined.split(/[-_]/)[0];
    if (primary === 'en') {
        return { interface_language_code: 'en', interface_language_name: 'английском' };
    }
    if (primary === 'ru') {
        return { interface_language_code: 'ru', interface_language_name: 'русском' };
    }
    return { interface_language_code: 'ru', interface_language_name: 'русском' };
}
