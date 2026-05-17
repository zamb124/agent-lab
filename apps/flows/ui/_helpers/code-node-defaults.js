/**
 * Дефолтный конфиг новой code-ноды: тот же контракт, что у inline tool —
 * isolated code-runner вызывает экспорт/функцию run(args, state).
 */

import { normalizeFlowCodeLanguage, starterCodeForLanguage } from './flows-code-languages.js';

/** @returns {string} */
export function getBlankCodeNodeCode(language = 'python') {
    return starterCodeForLanguage(language);
}

/** @returns {{ code: string, language: string }} */
export function getBlankCodeNodeConfig(language = 'python') {
    const normalized = normalizeFlowCodeLanguage(language);
    return {
        code: getBlankCodeNodeCode(normalized),
        language: normalized,
    };
}
