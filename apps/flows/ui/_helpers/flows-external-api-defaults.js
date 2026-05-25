/**
 * Стартовый конфиг ноды type=external_api при дропе с палитры.
 * Поля на верхнем уровне объекта ноды (тот же контракт, что у ExternalAPINode и редактора).
 */

/**
 * @returns {Record<string, unknown>}
 */
export function getBlankExternalApiNodeConfig() {
    const bodyTemplateObject = {
        message_from_state: '@state:content',
        nested_object: {
            literal_bool: false,
            literal_number: 1,
            state_path: '@state:user.profile.id',
        },
        full_var_cell: '@var:integration.secret_id',
        bearer_from_var: 'Bearer @var:secrets.service_token',
        inline_var_in_string: 'env-@var:config.env_code-suffix',
        list_of_state_refs: ['@state:first_id', '@state:second_id'],
        envelope: {
            source_literal: 'platform',
            trace_from_state: '@state:trace_id',
        },
    };

    return {
        description:
            'External API: входы через input_mapping; URL {placeholders}, заголовки и body — @state: / @var:.',
        method: 'POST',
        url: 'https://httpbin.org/anything/{item_id}',
        timeout: 30.0,
        headers: {
            Accept: 'application/json',
            'X-Example-Static': 'replace-or-use-@var:path',
            'X-Trace-Id': '@var:trace.request_id',
            Authorization: 'Bearer @var:secrets.example_token',
        },
        body_template: JSON.stringify(bodyTemplateObject, null, 2),
        parameters_schema: {
            type: 'object',
            properties: {
                item_id: {
                    type: 'string',
                    description: 'Подставляется в URL как {item_id}, если нода вызывается как tool.',
                },
                dry_run: {
                    type: 'boolean',
                    description: 'Пример поля: перенесите в body_template или отдельное поле входа при необходимости.',
                },
            },
            required: ['item_id'],
        },
        input_mapping: {
            item_id: '@state:context.item_id',
            dry_run: '@state:flags.dry_run',
        },
        state_mapping: {
            echoed_url: 'url',
        },
    };
}
