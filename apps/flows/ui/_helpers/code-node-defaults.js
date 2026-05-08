/**
 * Дефолтный конфиг новой code-ноды: тот же контракт, что у inline tool —
 * PythonCodeRunner.execute_tool (execute / BaseTool / последняя top-level функция).
 */

/** @returns {string} */
export function getBlankCodeNodeCode() {
    return `# Графовая нода type=code и inline tool исполняются одинаково (execute_tool).
# Допустимы: def / async def execute(args, state), класс BaseTool, или последняя top-level функция.
# args собираются из args_schema и input mapping панели ноды.

def execute(args, state):
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
