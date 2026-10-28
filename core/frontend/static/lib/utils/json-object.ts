/** JSON-объект на границе: `unknown` из payload, storage или ответа сужается до записи без массива и `null`. */
export function isJsonObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}
