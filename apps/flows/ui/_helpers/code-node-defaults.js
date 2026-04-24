/**
 * Дефолтный конфиг новой code-ноды: минимальный async-обработчик для Python runner
 * (одна top-level функция — точка входа для execute_tool).
 */

/** @returns {string} */
export function getBlankCodeNodeCode() {
    return `async def main(query=None, state=None):
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
