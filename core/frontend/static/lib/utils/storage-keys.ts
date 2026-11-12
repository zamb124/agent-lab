/**
 * Единая схема ключей localStorage / sessionStorage платформы.
 *
 * Канон:
 *   `platform:<scope>:<key>`
 *
 * `<scope>` — `frontend`, `crm`, `sync`, `office`, `rag`, `flows`, `voice`,
 * `litserve`, `worktracker`, `wiki`, `stock` или `core`. Для общеплатформенных
 * вещей (тема, локаль) — `core`.
 *
 * Запрещены свободные префиксы вроде `linnex.sync.*`, `crm:*`,
 * `sync.chat.*` — это устаревший канон и должен быть удалён.
 */

export type PlatformStorageScope =
    | 'core'
    | 'frontend'
    | 'crm'
    | 'sync'
    | 'office'
    | 'rag'
    | 'flows'
    | 'voice'
    | 'litserve'
    | 'worktracker'
    | 'wiki'
    | 'stock';

const _ALLOWED_SCOPES: ReadonlySet<string> = new Set<PlatformStorageScope>([
    'core',
    'frontend',
    'crm',
    'sync',
    'office',
    'rag',
    'flows',
    'voice',
    'litserve',
    'worktracker',
    'wiki',
    'stock',
]);

const _KEY_RE = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/;

/**
 * @param scope 'core' | '<svc>' (см. PlatformStorageScope)
 * @param key   snake_case с опциональными точками-разделителями подгрупп
 * @returns     готовый ключ `platform:<scope>:<key>`
 */
export function platformStorageKey(scope: unknown, key: unknown): string {
    if (typeof scope !== 'string' || !_ALLOWED_SCOPES.has(scope)) {
        throw new Error(
            `platformStorageKey: scope must be one of ${Array.from(_ALLOWED_SCOPES).join(', ')}; got "${scope}"`,
        );
    }
    if (typeof key !== 'string' || !_KEY_RE.test(key)) {
        throw new Error(
            `platformStorageKey: key must match ${_KEY_RE.source}; got "${key}"`,
        );
    }
    return `platform:${scope}:${key}`;
}
