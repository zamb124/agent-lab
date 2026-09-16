/**
 * Стартовый конфиг ноды type=code_agent при дропе с палитры.
 * invoke_argv не задаём: runtime/rebuild без argv падают, не угадывают main.py.
 */

/**
 * @returns {Record<string, unknown>}
 */
export function getBlankCodeAgentNodeConfig() {
    return {
        language: 'python',
        invoke_kind: 'cli',
    };
}
