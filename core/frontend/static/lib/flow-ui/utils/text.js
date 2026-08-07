/**
 * Flow UI chrome texts. The runtime is standalone (embed on foreign origins,
 * production iframe) and cannot depend on the platform i18n bus, so renderer
 * chrome strings live in this pinned RU/EN dictionary. Document content
 * (labels, greeting, placeholders) stays owner-editable data and never goes
 * through this module.
 */

const FLOW_UI_TEXT = Object.freeze({
    ru: Object.freeze({
        composer_send: 'Отправить',
        composer_stop: 'Остановить',
        composer_sending: 'Отправка…',
        composer_placeholder: 'Спросите о чём угодно…',
        attach_files: 'Прикрепить файлы',
        file_upload_hint: 'Перетащите сюда или выберите с устройства',
        file_upload_browse: 'Выбрать',
        remove_file: 'Убрать {name}',
        open_file: 'Открыть {name}',
        session_files: 'Файлы',
        session_files_panel: 'Файлы сессии ({count})',
        uploading: 'Загружаем файл…',
        assistant_typing: 'Агент отвечает…',
        message_copy: 'Копировать',
        message_copied: 'Скопировано',
        retry: 'Повторить',
        scroll_to_bottom: 'К последним сообщениям',
        stop_task: 'Остановить ответ',
        task_running: 'Агент отвечает…',
        conversation_feed: 'Сообщения',
        read_only: 'Только просмотр',
        status_saving: 'Сохранение…',
        status_saved: 'Сохранено',
        status_conflict: 'Конфликт синхронизации',
        status_preview: 'Предпросмотр',
        loading_interface: 'Загрузка интерфейса',
        pages_nav: 'Страницы',
        share: 'Поделиться сессией',
        share_aria: 'Поделиться этой сессией',
        share_title: 'Поделиться сессией',
        share_description: 'Ссылка открывает этот же диалог в его последней сохранённой версии. Это не гостевой просмотр flow.',
        share_view_only: 'Только просмотр',
        share_can_interact: 'Может взаимодействовать',
        share_creating: 'Сохраняем и создаём отзывную ссылку…',
        share_link: 'Ссылка',
        share_copy: 'Копировать',
        share_copied: 'Скопировано',
        share_revoke: 'Отозвать ссылку',
        surface_no_root: 'У поверхности нет корневого компонента',
        unknown_component: 'Неподдерживаемый внешний компонент',
        component_render_failed: 'Компонент не удалось отрисовать',
        image_empty: 'Изображение не выбрано',
        binary_file: 'Бинарный файл',
        binary_data: 'Бинарные данные',
        artifact: 'Артефакт',
        message_composer: 'Поле сообщения',
        status_read_only: 'Просмотр без изменений',
        interface_unavailable: 'Интерфейс недоступен',
        unknown_error: 'Неизвестная ошибка',
        open: 'Открыть',
        submit_default: 'Отправить',
        dialog: 'Диалог',
        citations: 'Источники',
        chart: 'График',
        run_trace: 'Трассировка выполнения',
        tool_activity: 'Работа инструментов',
        browser_preview: 'Предпросмотр браузера',
        skill_activity: 'Активность Skill',
        reflection: 'Рефлексия',
        action_preview: 'Предпросмотр действия',
        action_result: 'Результат действия',
        activity: 'Активность',
        required_field: 'Обязательное поле',
        invalid_email: 'Введите корректный email',
        invalid_pattern: 'Значение не соответствует шаблону',
        min_length: 'Не меньше {value} символов',
        max_length: 'Не больше {value} символов',
        turn_toast_working: 'Агент работает…',
        turn_toast_reasoning: 'Рассуждение',
        turn_toast_activity: 'Активность',
        turn_toast_response: 'Ответ',
        turn_toast_error: 'Ошибка',
        turn_toast_error_generic: 'Не удалось выполнить запрос',
        turn_toast_dismiss: 'Закрыть',
        turn_toast_stop: 'Остановить',
    }),
    en: Object.freeze({
        composer_send: 'Send',
        composer_stop: 'Stop',
        composer_sending: 'Sending…',
        composer_placeholder: 'Ask anything…',
        attach_files: 'Attach files',
        file_upload_hint: 'Drop files here or browse',
        file_upload_browse: 'Browse',
        remove_file: 'Remove {name}',
        open_file: 'Open {name}',
        session_files: 'Files',
        session_files_panel: 'Session files ({count})',
        uploading: 'Uploading file…',
        assistant_typing: 'Agent is responding…',
        message_copy: 'Copy',
        message_copied: 'Copied',
        retry: 'Retry',
        scroll_to_bottom: 'Jump to latest messages',
        stop_task: 'Stop response',
        task_running: 'Agent is responding…',
        conversation_feed: 'Messages',
        read_only: 'Read only',
        status_saving: 'Saving…',
        status_saved: 'Saved',
        status_conflict: 'Sync conflict',
        status_preview: 'Preview',
        loading_interface: 'Loading interface',
        pages_nav: 'Pages',
        share: 'Share session',
        share_aria: 'Share this session',
        share_title: 'Share this session',
        share_description: 'The link opens this same conversation at its latest acknowledged revision. This is not a guest flow preview.',
        share_view_only: 'View only',
        share_can_interact: 'Can interact',
        share_creating: 'Saving and creating a revocable link…',
        share_link: 'Link',
        share_copy: 'Copy',
        share_copied: 'Copied',
        share_revoke: 'Revoke link',
        surface_no_root: 'Surface has no root component',
        unknown_component: 'Unsupported external component',
        component_render_failed: 'Component failed to render',
        image_empty: 'No image selected',
        binary_file: 'Binary file',
        binary_data: 'Binary data',
        artifact: 'Artifact',
        message_composer: 'Message composer',
        status_read_only: 'Live read-only view',
        interface_unavailable: 'Interface unavailable',
        unknown_error: 'Unknown error',
        open: 'Open',
        submit_default: 'Submit',
        dialog: 'Dialog',
        citations: 'Citations',
        chart: 'Chart',
        run_trace: 'Run trace',
        tool_activity: 'Tool activity',
        browser_preview: 'Browser preview',
        skill_activity: 'Skill activity',
        reflection: 'Reflection',
        action_preview: 'Action preview',
        action_result: 'Action result',
        activity: 'Activity',
        required_field: 'This field is required',
        invalid_email: 'Enter a valid email',
        invalid_pattern: 'Value does not match the required pattern',
        min_length: 'Enter at least {value} characters',
        max_length: 'Enter at most {value} characters',
        turn_toast_working: 'Agent is working…',
        turn_toast_reasoning: 'Reasoning',
        turn_toast_activity: 'Activity',
        turn_toast_response: 'Response',
        turn_toast_error: 'Error',
        turn_toast_error_generic: 'The request could not be completed',
        turn_toast_dismiss: 'Dismiss',
        turn_toast_stop: 'Stop',
    }),
});

/**
 * Normalize any locale tag to a supported Flow UI chrome locale.
 * @param {unknown} locale
 * @param {Document | undefined} [doc]
 * @returns {'ru' | 'en'}
 */
export function resolveFlowUILocale(locale, doc = globalThis.document) {
    let tag = typeof locale === 'string' ? locale.trim().toLowerCase() : '';
    if (tag === '' || tag === 'auto') {
        const documentLang = doc?.documentElement?.lang;
        tag = typeof documentLang === 'string' && documentLang.trim() !== ''
            ? documentLang.trim().toLowerCase()
            : (typeof globalThis.navigator?.language === 'string'
                ? globalThis.navigator.language.toLowerCase()
                : 'en');
    }
    return tag === 'ru' || tag.startsWith('ru-') ? 'ru' : 'en';
}

/**
 * @param {'ru' | 'en'} locale
 * @param {string} key
 * @param {Record<string, string>} [vars]
 * @returns {string}
 */
export function flowUIText(locale, key, vars = undefined) {
    const bundle = FLOW_UI_TEXT[locale === 'ru' ? 'ru' : 'en'];
    const template = bundle[key];
    if (typeof template !== 'string') {
        throw new Error(`flow-ui: unknown text key ${key}`);
    }
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, (match, name) => {
        const value = vars[name];
        if (typeof value !== 'string') {
            throw new Error(`flow-ui: text ${key} missing variable ${name}`);
        }
        return value;
    });
}
