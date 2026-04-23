/**
 * Дефолтный конфиг новой code-ноды: валидный `execute` для python runner.
 */

/** @returns {string} */
export function getBlankCodeNodeCode() {
    return `async def execute(state=None):
    """Map inputs in the node panel (Input mapping)."""
    return {}
`;
}

/** @returns {{ code: string, language: string }} */
export function getBlankCodeNodeConfig() {
    return {
        code: getBlankCodeNodeCode(),
        language: 'python',
    };
}
