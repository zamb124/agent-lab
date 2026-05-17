/**
 * Дефолтный конфиг новой code-ноды: тот же контракт, что у inline tool —
 * PythonCodeRunner.execute_tool (run / execute / первая top-level функция).
 */

/** @returns {string} */
export function getBlankCodeNodeCode() {
    return `# Графовая нода type=code и inline tool исполняются одинаково (execute_tool).
# Предпочитай async def run(...); execute(...) допустим для совместимости.
# Если run/execute нет, будет вызвана первая top-level функция.
# args собираются из args_schema и input mapping панели ноды.

async def run(args, state):
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
