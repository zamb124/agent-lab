/**
 * Константы протокола Flow UI поверх A2A 1.0.
 * Значения совпадают с ``core/flow_ui/protocol.py`` (wire) и ``core/flow_ui/document.py``
 * (грамматика документа); паритет проверяет ``scripts/check_flow_ui_hard_cut.py``.
 */

export const A2A_PROTOCOL_VERSION = '1.0';

export const JSON_MEDIA_TYPE = 'application/json';
export const JSON_PATCH_MEDIA_TYPE = 'application/json-patch+json';
export const FLOW_UI_MEDIA_TYPE = 'application/vnd.platform.ui+json';
export const FLOW_UI_ACTION_MEDIA_TYPE = 'application/vnd.platform.ui-action+json';

export const STATE_ARTIFACT_ID = 'state';
export const UI_ARTIFACT_ID = 'ui';
export const RESPONSE_ARTIFACT_NAME = 'response';
export const REASONING_ARTIFACT_NAME = 'reasoning';
export const OPERATOR_REPLY_ARTIFACT_NAME = 'operator_reply';
export const USER_MESSAGE_ARTIFACT_NAME = 'user_message';
export const CONVERSATION_SLOT_ID = 'conversation';

export const TERMINAL_TASK_STATES = Object.freeze(new Set([
    'TASK_STATE_COMPLETED',
    'TASK_STATE_FAILED',
    'TASK_STATE_CANCELED',
    'TASK_STATE_REJECTED',
]));

export const INTERRUPTED_TASK_STATES = Object.freeze(new Set([
    'TASK_STATE_INPUT_REQUIRED',
    'TASK_STATE_AUTH_REQUIRED',
]));

/** Путь поля state: сегменты через точку, без индексов и пробелов. */
export const STATE_PATH_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$/;

/** Блоки ввода грамматики: их ``field`` уходит в ``ui-action.fields``. */
export const INPUT_BLOCK_TYPES = Object.freeze(new Set([
    'text_input',
    'number_input',
    'select',
    'checkbox',
    'switch',
    'slider',
    'date_input',
    'datetime_input',
    'file_upload',
    'voice_input',
]));
