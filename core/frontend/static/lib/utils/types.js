/**
 * Типы и константы для Platform UI
 */

/**
 * @typedef {Object} User
 * @property {string} id
 * @property {string} email
 * @property {string} [name]
 */

/**
 * @typedef {Object} Agent
 * @property {string} id
 * @property {string} name
 * @property {string} [description]
 * @property {string} [icon]
 */

/**
 * @typedef {'user'|'assistant'|'system'} MessageRole
 */

/**
 * @typedef {Object} Message
 * @property {string} id
 * @property {MessageRole} role
 * @property {string} content
 * @property {string} [timestamp]
 * @property {boolean} [streaming]
 */

/**
 * @typedef {'pending'|'running'|'completed'|'failed'|'cancelled'} TaskState
 */

/**
 * @typedef {Object} Task
 * @property {string} id
 * @property {string} contextId
 * @property {TaskState} state
 * @property {Object} [status]
 * @property {Array} [artifacts]
 */

/**
 * @typedef {'success'|'error'|'warning'|'info'} ToastType
 */

/**
 * @typedef {Object} Toast
 * @property {string} id
 * @property {ToastType} type
 * @property {string} message
 * @property {number} [duration]
 */

/**
 * События приложения
 */
export const AppEvents = {
    AGENT_SELECT: 'agent-select',
    EDIT_AGENT: 'edit-agent',
    MESSAGE_SEND: 'message-send',
    MESSAGE_RECEIVED: 'message-received',
    TASK_UPDATE: 'task-update',
    AUTH_CHANGE: 'auth-change',
    THEME_CHANGE: 'theme-change',
    TOAST_SHOW: 'toast-show',
    MODAL_OPEN: 'modal-open',
    MODAL_CLOSE: 'modal-close',
};

/**
 * CSS классы для glass эффектов
 */
export const GlassClasses = {
    SUBTLE: 'glass-subtle',
    MEDIUM: 'glass-medium',
    STRONG: 'glass-strong',
};


