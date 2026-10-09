/**
 * Тексты chrome Flow UI. Runtime автономен (embed на чужом origin) и не зависит от i18n-шины
 * платформы, поэтому строки chrome живут в этом словаре RU/EN. Контент документа
 * (подписи, приветствие, placeholder) — данные автора, не проходят через этот модуль.
 */

const FLOW_UI_TEXT = Object.freeze({
    ru: Object.freeze({
        composer_send: 'Отправить',
        composer_stop: 'Остановить',
        composer_placeholder: 'Спросите о чём угодно…',
        attach_files: 'Прикрепить файлы',
        file_upload_hint: 'Перетащите сюда или выберите с устройства',
        file_uploading: 'Загружаем файл…',
        remove_file: 'Убрать {name}',
        open_file: 'Открыть {name}',
        session_files: 'Файлы',
        session_files_panel: 'Файлы сессии ({count})',
        files_empty: 'Файлов пока нет',
        assistant_typing: 'Агент отвечает…',
        message_copy: 'Копировать',
        message_copied: 'Скопировано',
        stop_task: 'Остановить ответ',
        task_running: 'Агент отвечает…',
        task_canceled: 'Остановлено',
        conversation_feed: 'Сообщения',
        reasoning: 'Рассуждение',
        read_only: 'Только просмотр',
        status_preview: 'Предпросмотр',
        status_read_only: 'Просмотр без изменений',
        status_live: 'Онлайн',
        status_error: 'Ошибка соединения',
        loading_interface: 'Загрузка интерфейса',
        pages_nav: 'Страницы',
        share: 'Поделиться сессией',
        share_aria: 'Поделиться этой сессией',
        share_title: 'Поделиться сессией',
        share_description: 'Ссылка открывает этот же диалог и продолжает получать его обновления.',
        share_view_only: 'Только просмотр',
        share_can_interact: 'Может писать',
        share_creating: 'Создаём отзывную ссылку…',
        share_link: 'Ссылка',
        share_copy: 'Копировать',
        share_copied: 'Скопировано',
        share_revoke: 'Отозвать ссылку',
        expand_aria: 'На весь экран',
        collapse_aria: 'Свернуть',
        close_aria: 'Закрыть',
        resize_aria: 'Изменить размер окна',
        embed: 'Встроить',
        embed_aria: 'Код и ссылка для встраивания',
        embed_title: 'Встроить агента',
        embed_page_url: 'Полноэкранная страница',
        embed_page_description: 'Открывает чат на весь экран без FAB.',
        embed_copy: 'Копировать',
        embed_copied: 'Скопировано',
        voice_start: 'Включить голосовой эфир',
        voice_stop: 'Выключить голосовой эфир',
        interface_unavailable: 'Интерфейс недоступен',
        unknown_error: 'Неизвестная ошибка',
        field_required: 'Обязательное поле',
        slot_empty: 'Сюда агент положит блоки через ui_render',
        block_empty: 'Блок {type} пока пуст: появится, когда в state будут данные',
        drop_block_here: 'Перетащите блок сюда',
        tool_activity_empty: 'Здесь появится работа инструментов во время выполнения',
        skill_label: 'Skill',
        action_preview_label: 'Черновик действия',
        action_status_success: 'Выполнено',
        action_status_failed: 'Ошибка',
        action_status_pending: 'Ожидает',
        browser_status_running: 'Открывается',
        browser_status_finished: 'Готово',
        browser_status_failed: 'Ошибка',
        turn_toast_working: 'Агент работает…',
        turn_toast_response: 'Ответ',
        turn_toast_error: 'Ошибка',
        turn_toast_error_generic: 'Не удалось выполнить запрос',
        turn_toast_dismiss: 'Закрыть',
        turn_toast_stop: 'Остановить',
        hitl_banner_single_reply: 'Оператор готовит ответ. Писать не нужно.',
        hitl_banner_takeover: 'Можете писать оператору. Агент продолжит после завершения задачи.',
        hitl_submit_single_reply: 'Ответить и завершить',
        hitl_submit_takeover: 'Отправить',
        value_yes: 'да',
        value_no: 'нет',
        oauth_authorize: 'Авторизоваться',
        operator_label: 'Оператор',
        open_tracing: 'Трассировка',
        open_logs: 'Логи',
        run_trace: 'Трассировка выполнения',
        run_trace_empty: 'Пока нет событий выполнения',
        node_start: 'старт',
        node_complete: 'готово',
        node_error: 'ошибка',
        edge_executed: 'переход',
    }),
    en: Object.freeze({
        composer_send: 'Send',
        composer_stop: 'Stop',
        composer_placeholder: 'Ask anything…',
        attach_files: 'Attach files',
        file_upload_hint: 'Drop files here or browse',
        file_uploading: 'Uploading file…',
        remove_file: 'Remove {name}',
        open_file: 'Open {name}',
        session_files: 'Files',
        session_files_panel: 'Session files ({count})',
        files_empty: 'No files yet',
        assistant_typing: 'Agent is responding…',
        message_copy: 'Copy',
        message_copied: 'Copied',
        stop_task: 'Stop response',
        task_running: 'Agent is responding…',
        task_canceled: 'Stopped',
        conversation_feed: 'Messages',
        reasoning: 'Reasoning',
        read_only: 'Read only',
        status_preview: 'Preview',
        status_read_only: 'Live read-only view',
        status_live: 'Live',
        status_error: 'Connection error',
        loading_interface: 'Loading interface',
        pages_nav: 'Pages',
        share: 'Share session',
        share_aria: 'Share this session',
        share_title: 'Share this session',
        share_description: 'The link opens this same conversation and keeps receiving its updates.',
        share_view_only: 'View only',
        share_can_interact: 'Can write',
        share_creating: 'Creating a revocable link…',
        share_link: 'Link',
        share_copy: 'Copy',
        share_copied: 'Copied',
        share_revoke: 'Revoke link',
        expand_aria: 'Expand to full screen',
        collapse_aria: 'Collapse',
        close_aria: 'Close',
        resize_aria: 'Resize window',
        embed: 'Embed',
        embed_aria: 'Embed code and page link',
        embed_title: 'Embed this agent',
        embed_page_url: 'Full-screen page',
        embed_page_description: 'Opens the chat edge-to-edge without a FAB.',
        embed_copy: 'Copy',
        embed_copied: 'Copied',
        voice_start: 'Start live voice session',
        voice_stop: 'Stop live voice session',
        interface_unavailable: 'Interface unavailable',
        unknown_error: 'Unknown error',
        field_required: 'This field is required',
        slot_empty: 'The agent will place blocks here via ui_render',
        block_empty: 'The {type} block is empty: it appears once state has data',
        drop_block_here: 'Drop a block here',
        tool_activity_empty: 'Tool activity appears here while the flow runs',
        skill_label: 'Skill',
        action_preview_label: 'Action draft',
        action_status_success: 'Done',
        action_status_failed: 'Failed',
        action_status_pending: 'Pending',
        browser_status_running: 'Loading',
        browser_status_finished: 'Ready',
        browser_status_failed: 'Failed',
        turn_toast_working: 'Agent is working…',
        turn_toast_response: 'Response',
        turn_toast_error: 'Error',
        turn_toast_error_generic: 'The request could not be completed',
        turn_toast_dismiss: 'Dismiss',
        turn_toast_stop: 'Stop',
        hitl_banner_single_reply: 'The operator is preparing a reply. You do not need to write.',
        hitl_banner_takeover: 'You can message the operator. The agent continues after the task is completed.',
        hitl_submit_single_reply: 'Reply and complete',
        hitl_submit_takeover: 'Send',
        value_yes: 'yes',
        value_no: 'no',
        oauth_authorize: 'Authorize',
        operator_label: 'Operator',
        open_tracing: 'Tracing',
        open_logs: 'Logs',
        run_trace: 'Run trace',
        run_trace_empty: 'No execution events yet',
        node_start: 'start',
        node_complete: 'done',
        node_error: 'error',
        edge_executed: 'edge',
    }),
});

/** @returns {'ru' | 'en'} */
export type FlowUILocale = 'ru' | 'en';

export function resolveFlowUILocale(locale?: string | null, doc: Document | undefined = globalThis.document): FlowUILocale {
    let tag = typeof locale === 'string' ? locale.trim().toLowerCase() : '';
    if (tag === '' || tag === 'auto') {
        const documentLang = doc?.documentElement?.lang;
        tag = typeof documentLang === 'string' && documentLang.trim() !== ''
            ? documentLang.trim().toLowerCase()
            : (typeof globalThis.navigator?.language === 'string' ? globalThis.navigator.language.toLowerCase() : 'en');
    }
    return tag === 'ru' || tag.startsWith('ru-') ? 'ru' : 'en';
}

/** Подпись кнопки отправки оператора; для обычного профиля — ``null`` (composer_send). */
export function hitlComposerSendLabel(locale: string, mode?: string | null): string | null {
    if (mode === undefined || mode === null) return null;
    if (mode === 'single_reply') return flowUIText(locale, 'hitl_submit_single_reply');
    if (mode === 'takeover') return flowUIText(locale, 'hitl_submit_takeover');
    throw new Error(`flow-ui: unsupported HITL mode ${JSON.stringify(mode)}`);
}

export function flowUIText(locale: string, key: string, vars?: Record<string, string>): string {
    const bundle: Record<string, string> = FLOW_UI_TEXT[locale === 'ru' ? 'ru' : 'en'];
    const template = bundle[key];
    if (typeof template !== 'string') throw new Error(`flow-ui: unknown text key ${key}`);
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, (match, name) => {
        const value = vars[name];
        if (typeof value !== 'string') throw new Error(`flow-ui: text ${key} missing variable ${name}`);
        return value;
    });
}
