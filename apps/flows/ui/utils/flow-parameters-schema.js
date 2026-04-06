/**
 * Минимальная проверка JSON Schema верхнего уровня для OpenAI function parameters.
 * @param {unknown} obj
 * @returns {boolean}
 */
export function isValidLlmParametersSchema(obj) {
    return (
        obj !== null &&
        typeof obj === 'object' &&
        !Array.isArray(obj) &&
        obj.type === 'object' &&
        Object.prototype.hasOwnProperty.call(obj, 'properties') &&
        typeof obj.properties === 'object' &&
        obj.properties !== null &&
        !Array.isArray(obj.properties)
    );
}
