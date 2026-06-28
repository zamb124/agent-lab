/**
 * Read-only catalog of system/context variables for autocomplete and help.
 */

export const SYSTEM_VARIABLE_KEYS = [
    'current_date',
    'current_time',
    'current_datetime',
    'current_year',
    'current_month',
    'current_day',
    'user_id',
    'user_name',
    'user_email',
    'user_first_name',
    'user_last_name',
    'company_id',
    'company_name',
    'active_namespace',
    'user_language',
    'interface_language_code',
    'interface_language_name',
];

export function listSystemVariableKeys() {
    return [...SYSTEM_VARIABLE_KEYS];
}

export function isSystemVariableKey(variableKey) {
    return typeof variableKey === 'string' && SYSTEM_VARIABLE_KEYS.includes(variableKey);
}
