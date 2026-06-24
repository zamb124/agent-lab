/**
 * Перестановка колонок доски по индексу вставки (gap между элементами).
 *
 * insertIndex — позиция щели: 0 перед первым, length после последнего.
 */

export function reorderByInsertIndex(items, fromIndex, insertIndex) {
    if (!Array.isArray(items)) {
        throw new Error('reorderByInsertIndex: items must be an array');
    }
    if (fromIndex < 0 || fromIndex >= items.length) {
        return items.slice();
    }
    if (insertIndex < 0 || insertIndex > items.length) {
        return items.slice();
    }
    if (fromIndex === insertIndex || fromIndex + 1 === insertIndex) {
        return items.slice();
    }
    const next = items.slice();
    const [moved] = next.splice(fromIndex, 1);
    let toIndex = insertIndex;
    if (fromIndex < insertIndex) {
        toIndex -= 1;
    }
    next.splice(toIndex, 0, moved);
    return next;
}
