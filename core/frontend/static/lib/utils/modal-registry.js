/**
 * Реестр модалок: kind -> tagName.
 *
 * Любая модалка при импорте файла регистрирует себя через registerModalKind.
 * platform-modal-stack рендерит компоненты по kind из state.modals.stack.
 *
 * kind: '<scope>.<name>' (точка как разделитель), например 'frontend.api_key_create'.
 */

const _registry = new Map();

const KIND_PATTERN = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;

export function registerModalKind(kind, tagName) {
    if (typeof kind !== 'string' || !KIND_PATTERN.test(kind)) {
        throw new Error(
            `registerModalKind: kind "${kind}" violates pattern <scope>.<name> (snake_case).`,
        );
    }
    if (typeof tagName !== 'string' || tagName.length === 0) {
        throw new Error(`registerModalKind: tagName must be non-empty string, got: ${tagName}`);
    }
    const tag = tagName.toLowerCase();
    const existing = _registry.get(kind);
    if (existing && existing !== tag) {
        throw new Error(
            `registerModalKind: kind "${kind}" already registered as <${existing}>, refused <${tag}>.`,
        );
    }
    _registry.set(kind, tag);
    return kind;
}

export function getModalTag(kind) {
    const tag = _registry.get(kind);
    if (!tag) {
        throw new Error(`getModalTag: kind "${kind}" not registered. Did you import the modal module?`);
    }
    return tag;
}

export function hasModalKind(kind) {
    return _registry.has(kind);
}

export function listModalKinds() {
    return Array.from(_registry.keys()).sort();
}
