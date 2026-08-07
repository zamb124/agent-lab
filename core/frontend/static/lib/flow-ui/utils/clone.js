/**
 * Clone protocol-owned JSON without requiring structuredClone in older webviews.
 * Flow UI state is deliberately JSON-serializable, so the fallback is lossless for
 * every value allowed by the wire contract.
 */
export function cloneSerializable(value) {
    if (value == null || typeof value !== 'object') return value;
    if (typeof globalThis.structuredClone === 'function') {
        return globalThis.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
}
