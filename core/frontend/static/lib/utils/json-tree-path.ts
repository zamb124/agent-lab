/**
 * Пути узлов JSON-дерева: object — через точку, array — [index].
 */

export function jsonTreeChildPath(parentPath: unknown, key: unknown, isIndex: unknown): string {
    if (typeof parentPath !== 'string') {
        throw new Error('jsonTreeChildPath: parentPath must be a string');
    }
    if (typeof isIndex !== 'boolean') {
        throw new Error('jsonTreeChildPath: isIndex must be a boolean');
    }
    if (isIndex) {
        if (typeof key !== 'number' || !Number.isFinite(key) || key < 0) {
            throw new Error('jsonTreeChildPath: array index must be a non-negative number');
        }
        return `${parentPath}[${String(Math.floor(key))}]`;
    }
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('jsonTreeChildPath: object key must be a non-empty string');
    }
    if (parentPath.length === 0) {
        return key;
    }
    return `${parentPath}.${key}`;
}
