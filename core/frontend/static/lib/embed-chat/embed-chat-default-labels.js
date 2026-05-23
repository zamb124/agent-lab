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
        title_attach: 'Прикрепить файл',
        title_remove_file: 'Убрать файл',
        send: 'Отправить',
        new_chat: 'Новый чат',
        voice_title: 'Голосовой ввод',
        voice_not_supported: 'Голосовой ввод не поддерживается в этом браузере',
        voice_on: 'Включить голос',
        voice_off: 'Выключить голос',
        voice_status_idle: 'Голосовой режим: ожидание',
        voice_status_listening: 'Голосовой режим: слушаю',
        voice_status_speaking: 'Голосовой режим: говорю',
        voice_status_error: 'Голосовой режим: ошибка',
        voice_status_closed: 'Голосовой режим: соединение закрыто',
        voice_err_no_base_url: 'Голос недоступен: не указан адрес голосового шлюза.',
        voice_err_no_embed: 'Голос недоступен: нет контекста виджета (embed / flow).',
        voice_err_no_company: 'Голос недоступен: не указана компания.',
        voice_err_no_flows: 'Голос недоступен: не указан адрес flows (A2A).',
        title_stop: 'Остановить ответ',
        title_stop_pending: 'Останавливаю ответ…',
        tts_output_enable: 'Включить озвучку ответов',
        tts_output_disable: 'Отключить озвучку ответов',
        locale_auto: 'Авто',
        locale_ru: 'Русский',
        locale_en: 'English',
        ai_disclaimer: 'Содержимое, созданное ИИ, может быть неточным.',
        interrupt_operator_banner: 'Ожидается действие оператора. Диалог на паузе.',
        interrupt_oauth_banner: 'Требуется авторизация во внешнем сервисе',
        interrupt_oauth_button: 'Авторизоваться',
        breakpoint_continue: 'Продолжить',
        breakpoint_view_state: 'Состояние',
        integration_badge_title: 'Подключено: {provider} / {service}',
        integration_disconnect: 'Отключить',
        role_user: 'Вы',
        role_assistant: 'Ассистент',
        role_operator: 'Оператор',
        role_system: 'Система',
        operator_reply_heading: 'Оператор',
        operator_files: 'Прикреплённые файлы',
        download_file: 'Скачать',
        streaming_placeholder: 'Формирую ответ…',
        thinking_status: 'Думаю над ответом…',
        thinking_aria: 'Показать ход рассуждения',
        tool_default_name: 'инструмент',
        tool_stack_aria: 'Вызовы инструментов: {names}',
        tool_hint_tool_name: 'Инструмент: {name}',
        tool_hint_args_label: 'Аргументы:',
        tool_hint_result_label: 'Результат:',
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
        title_attach: 'Attach file',
        title_remove_file: 'Remove file',
        send: 'Send',
        new_chat: 'New chat',
        voice_title: 'Voice input',
        voice_not_supported: 'Voice input is not supported in this browser',
        voice_on: 'Enable voice',
        voice_off: 'Disable voice',
        voice_status_idle: 'Voice mode: idle',
        voice_status_listening: 'Voice mode: listening',
        voice_status_speaking: 'Voice mode: speaking',
        voice_status_error: 'Voice mode: error',
        voice_status_closed: 'Voice mode: connection closed',
        voice_err_no_base_url: 'Voice unavailable: voice gateway URL is missing.',
        voice_err_no_embed: 'Voice unavailable: missing widget context (embed / flow).',
        voice_err_no_company: 'Voice unavailable: company is not set.',
        voice_err_no_flows: 'Voice unavailable: flows (A2A) base URL is missing.',
        title_stop: 'Stop response',
        title_stop_pending: 'Stopping response…',
        tts_output_enable: 'Enable spoken responses',
        tts_output_disable: 'Disable spoken responses',
        locale_auto: 'Auto',
        locale_ru: 'Russian',
        locale_en: 'English',
        ai_disclaimer: 'AI-generated content may be inaccurate.',
        interrupt_operator_banner: 'Waiting for an operator. The chat is on hold.',
        interrupt_oauth_banner: 'External service authorization required',
        interrupt_oauth_button: 'Authorize',
        breakpoint_continue: 'Continue',
        breakpoint_view_state: 'View state',
        integration_badge_title: 'Connected: {provider} / {service}',
        integration_disconnect: 'Disconnect',
        role_user: 'You',
        role_assistant: 'Assistant',
        role_operator: 'Operator',
        role_system: 'System',
        operator_reply_heading: 'Operator',
        operator_files: 'Attached files',
        download_file: 'Download',
        streaming_placeholder: 'Generating a reply…',
        thinking_status: 'Thinking…',
        thinking_aria: 'Show reasoning',
        tool_default_name: 'tool',
        tool_stack_aria: 'Tool calls: {names}',
        tool_hint_tool_name: 'Tool: {name}',
        tool_hint_args_label: 'Arguments:',
        tool_hint_result_label: 'Result:',
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
