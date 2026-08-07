export const A2A_PROTOCOL_VERSION = '1.0';
export const A2A_EXTENSION_HEADER = 'A2A-Extensions';
export const A2UI_EXTENSION_URI = 'https://a2ui.org/a2a-extension/a2ui/v0.9.1';
export const A2UI_VERSION = 'v0.9.1';
export const A2UI_MEDIA_TYPE = 'application/a2ui+json';
// Catalog identity is derived from the primary apex only, never from window.location.
const PLATFORM_PRIMARY_APEX = 'linnex.io';
export const LINNEX_CATALOG_ID = `https://${PLATFORM_PRIMARY_APEX}/a2ui/catalog/platform/v1`;

export const FLOW_UI_ACTIONS = Object.freeze({
    bootstrap: 'platform.ui.bootstrap',
    sync: 'platform.ui.sync',
    submit: 'platform.ui.submit',
});

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
