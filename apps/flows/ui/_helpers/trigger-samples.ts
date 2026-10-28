/**
 * Sample payloads and DX helpers for flow trigger editor.
 *
 * Telegram Update sample follows Bot API Message + Update shapes:
 * https://core.telegram.org/bots/api#update
 * https://core.telegram.org/bots/api#message
 */

/** @typedef {{ state: string, payload: string, descKey: string }} MappingExample */

/** @type {Readonly<Record<string, readonly MappingExample[]>>} */
export const MAPPING_EXAMPLES = Object.freeze({
    telegram: Object.freeze([
        { state: 'content', payload: 'message.text', descKey: 'examples_telegram_text' },
        { state: 'context.chat_id', payload: 'message.chat.id', descKey: 'examples_telegram_chat_id' },
        { state: 'context.user_id', payload: 'message.from.id', descKey: 'examples_telegram_user_id' },
        { state: 'context.username', payload: 'message.from.username', descKey: 'examples_telegram_username' },
        { state: 'context.message_id', payload: 'message.message_id', descKey: 'examples_telegram_message_id' },
    ]),
    webhook: Object.freeze([
        { state: 'content', payload: 'body.text', descKey: 'examples_webhook_body' },
        { state: 'context.event', payload: 'headers.X-Event', descKey: 'examples_webhook_header' },
        { state: 'context.ref', payload: 'query.ref', descKey: 'examples_webhook_query' },
    ]),
    cron: Object.freeze([
        { state: 'content', payload: 'scheduled_time', descKey: 'examples_cron_scheduled_time' },
        { state: 'context.timezone', payload: 'timezone', descKey: 'examples_cron_timezone' },
    ]),
    email: Object.freeze([
        { state: 'content', payload: 'body', descKey: 'examples_email_body' },
        { state: 'context.from', payload: 'from', descKey: 'examples_email_from' },
        { state: 'context.subject', payload: 'subject', descKey: 'examples_email_subject' },
        { state: 'context.message_id', payload: 'message_id', descKey: 'examples_email_message_id' },
    ]),
    platform_event: Object.freeze([
        { state: 'context.event_type', payload: 'event_type', descKey: 'examples_platform_event_type' },
        { state: 'content', payload: 'payload.entity_id', descKey: 'examples_platform_event_payload' },
        { state: 'context.actor_user_id', payload: 'actor_user_id', descKey: 'examples_platform_event_actor' },
        { state: 'context.company_id', payload: 'company_id', descKey: 'examples_platform_event_company' },
    ]),
});

/**
 * Official-shaped Telegram Update with a text Message
 * (fields from Bot API Update + Message).
 * @see https://core.telegram.org/bots/api#update
 * @see https://core.telegram.org/bots/api#message
 */
export const TELEGRAM_SAMPLE_UPDATE = Object.freeze({
    update_id: 10000,
    message: Object.freeze({
        message_id: 1365,
        from: Object.freeze({
            id: 1111111,
            is_bot: false,
            first_name: 'Test',
            last_name: 'User',
            username: 'TestUser',
            language_code: 'en',
        }),
        chat: Object.freeze({
            id: 1111111,
            first_name: 'Test',
            last_name: 'User',
            username: 'TestUser',
            type: 'private',
        }),
        date: 1441645532,
        text: 'Hello, world!',
    }),
});

/** Sample inbound webhook envelope (matches generic_webhook runtime). */
export const WEBHOOK_SAMPLE_PAYLOAD = Object.freeze({
    body: Object.freeze({ text: 'stock-updated', sku: 'SKU-42' }),
    headers: Object.freeze({ 'X-Event': 'inventory.changed', 'Content-Type': 'application/json' }),
    query: Object.freeze({ ref: 'order-42' }),
});

/** Sample email trigger payload (matches inbound_mail_to_trigger_payload). */
export const EMAIL_SAMPLE_PAYLOAD = Object.freeze({
    from: 'warehouse@example.com',
    subject: 'Stock alert',
    body: 'SKU-42 is below threshold.',
    uid: 42,
    mailbox_binding_id: 'mailbind_example',
    email_address: 'ops@company.example',
    message_id: '<stock-42@example.com>',
});

/**
 * One-click filter presets for email triggers (subject / senders).
 * `subjectValueKey` — i18n key under trigger_editor_modal for locale-specific substring.
 * @typedef {{
 *   id: string,
 *   labelKey: string,
 *   allowed_senders: readonly string[],
 *   subjectValueKey: string | null,
 * }} EmailFilterPreset
 */

/** @type {ReadonlyArray<EmailFilterPreset>} */
export const EMAIL_FILTER_PRESETS = Object.freeze([
    Object.freeze({
        id: 'all',
        labelKey: 'email_preset_all',
        allowed_senders: Object.freeze([]),
        subjectValueKey: null,
    }),
    Object.freeze({
        id: 'subject_order',
        labelKey: 'email_preset_subject_order',
        allowed_senders: Object.freeze([]),
        subjectValueKey: 'email_preset_subject_order_value',
    }),
    Object.freeze({
        id: 'subject_invoice',
        labelKey: 'email_preset_subject_invoice',
        allowed_senders: Object.freeze([]),
        subjectValueKey: 'email_preset_subject_invoice_value',
    }),
    Object.freeze({
        id: 'subject_alert',
        labelKey: 'email_preset_subject_alert',
        allowed_senders: Object.freeze([]),
        subjectValueKey: 'email_preset_subject_alert_value',
    }),
    Object.freeze({
        id: 'noreply',
        labelKey: 'email_preset_noreply',
        allowed_senders: Object.freeze(['noreply', 'no-reply', 'donotreply']),
        subjectValueKey: null,
    }),
]);

/** Sample cron tick payload. */
export const CRON_SAMPLE_PAYLOAD = Object.freeze({
    scheduled_time: '2026-07-24T09:00:00+03:00',
    timezone: 'Europe/Moscow',
});

/** Sample platform_event trigger payload (bus envelope fields for mapping). */
export const PLATFORM_EVENT_SAMPLE_PAYLOAD = Object.freeze({
    event_id: 'evt_example_001',
    event_type: 'crm/entity/created',
    company_id: 'company_example',
    actor_user_id: 'user_example',
    occurred_ts: 1753362000,
    payload: Object.freeze({
        entity_id: 'ent_42',
        entity_type: 'person',
        name: 'Ada Lovelace',
    }),
});

/** @type {Readonly<Record<string, unknown>>} */
export const TRIGGER_SAMPLE_PAYLOADS = Object.freeze({
    telegram: TELEGRAM_SAMPLE_UPDATE,
    webhook: WEBHOOK_SAMPLE_PAYLOAD,
    email: EMAIL_SAMPLE_PAYLOAD,
    cron: CRON_SAMPLE_PAYLOAD,
    platform_event: PLATFORM_EVENT_SAMPLE_PAYLOAD,
});

/** @type {Readonly<Record<string, string>>} */
export const TRIGGER_SAMPLE_DOCS = Object.freeze({
    telegram: 'https://core.telegram.org/bots/api#update',
    webhook: '/documentation/flows/triggers_runtime_matrix/',
    email: '',
    cron: '',
    platform_event: '/flows/platform-events',
});

function presentText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

/**
 * Absolute webhook URL for the current host.
 * @param {{ origin: string, flowId: string, triggerId: string }} args
 */
export function buildWebhookEndpointUrl({ origin, flowId, triggerId }: any) {
    const base = presentText(origin).replace(/\/$/, '');
    const fid = presentText(flowId).trim();
    const tid = presentText(triggerId).trim();
    if (!base || !fid) {
        throw new Error('buildWebhookEndpointUrl: origin and flowId are required');
    }
    const pathTid = tid.length > 0 ? tid : '<trigger_id>';
    return `${base}/flows/api/v1/triggers/webhook/${fid}/${pathTid}`;
}

/**
 * Ready-to-paste curl for the current webhook config.
 * @param {{
 *   origin: string,
 *   flowId: string,
 *   triggerId: string,
 *   secretToken?: string,
 *   secretHeader?: string,
 * }} args
 */
export function buildWebhookCurl(args: any) {
    const secretHeader = String(args.secretHeader || 'X-Trigger-Secret').trim() || 'X-Trigger-Secret';
    const secretToken = typeof args.secretToken === 'string' ? args.secretToken.trim() : '';
    const url = `${buildWebhookEndpointUrl(args)}?ref=order-42`;
    const bodyJson = JSON.stringify({ text: 'stock-updated', sku: 'SKU-42' });
    const lines = [
        `curl -X POST '${url}'`,
        `  -H 'Content-Type: application/json'`,
        `  -H 'X-Event: inventory.changed'`,
    ];
    if (secretToken.length > 0) {
        const escapedSecret = secretToken.replace(/'/g, `'\\''`);
        lines.push(`  -H '${secretHeader}: ${escapedSecret}'`);
    }
    lines.push(`  -d '${bodyJson}'`);
    return lines.join(' \\\n');
}

/**
 * Ready-to-paste curl simulating a Telegram Update webhook.
 * @param {{
 *   origin: string,
 *   flowId: string,
 *   triggerId: string,
 *   secretToken?: string,
 * }} args
 */
export function buildTelegramCurl(args: any) {
    const base = presentText(args.origin).replace(/\/$/, '');
    const fid = presentText(args.flowId).trim();
    const tid = presentText(args.triggerId).trim() || '<trigger_id>';
    if (!base || !fid) {
        throw new Error('buildTelegramCurl: origin and flowId are required');
    }
    const url = `${base}/flows/api/v1/triggers/telegram/${fid}/${tid}`;
    const bodyJson = JSON.stringify(TELEGRAM_SAMPLE_UPDATE);
    const secretToken = typeof args.secretToken === 'string' ? args.secretToken.trim() : '';
    const lines = [
        `curl -X POST '${url}'`,
        `  -H 'Content-Type: application/json'`,
    ];
    if (secretToken.length > 0) {
        const escapedSecret = secretToken.replace(/'/g, `'\\''`);
        lines.push(`  -H 'X-Telegram-Bot-Api-Secret-Token: ${escapedSecret}'`);
    }
    lines.push(`  -d '${bodyJson}'`);
    return lines.join(' \\\n');
}
