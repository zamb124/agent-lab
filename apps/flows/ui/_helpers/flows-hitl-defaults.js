/**
 * Стартовый конфиг hitl_node при дропе с палитры.
 * Пример title/message с @state: — канон как у обычных полей (variable-input).
 */

/**
 * @returns {Record<string, unknown>}
 */
export function getBlankHitlNodeConfig() {
    return {
        handoff_mode: 'single_reply',
        handoff_task_title: 'Оператор: @state:content',
        handoff_user_message: [
            '## Запрос передан оператору',
            '',
            'Контекст от пользователя:',
            '',
            '@state:content',
        ].join('\n'),
    };
}
