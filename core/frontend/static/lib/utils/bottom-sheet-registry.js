/**
 * Реестр нижних экранов (bottom sheets): kind -> tagName.
 *
 * Любой sheet при импорте модуля регистрирует себя через registerBottomSheetKind.
 * platform-bottom-sheet-stack рендерит компоненты по kind из state.bottomSheets.stack.
 *
 * kind: '<scope>.<name>' (точка как разделитель), например 'platform.service_switcher'.
 */

const _registry = new Map();

const KIND_PATTERN = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;

export function registerBottomSheetKind(kind, tagName) {
    if (typeof kind !== 'string' || !KIND_PATTERN.test(kind)) {
        throw new Error(
            `registerBottomSheetKind: kind "${kind}" violates pattern <scope>.<name> (snake_case).`,
        );
    }
    if (typeof tagName !== 'string' || tagName.length === 0) {
        throw new Error(`registerBottomSheetKind: tagName must be non-empty string, got: ${tagName}`);
    }
    const tag = tagName.toLowerCase();
    const existing = _registry.get(kind);
    if (existing && existing !== tag) {
        throw new Error(
            `registerBottomSheetKind: kind "${kind}" already registered as <${existing}>, refused <${tag}>.`,
        );
    }
    _registry.set(kind, tag);
    return kind;
}

export function getBottomSheetTag(kind) {
    const tag = _registry.get(kind);
    if (!tag) {
        throw new Error(`getBottomSheetTag: kind "${kind}" not registered. Did you import the sheet module?`);
    }
    return tag;
}

export function hasBottomSheetKind(kind) {
    return _registry.has(kind);
}

export function listBottomSheetKinds() {
    return Array.from(_registry.keys()).sort();
}
