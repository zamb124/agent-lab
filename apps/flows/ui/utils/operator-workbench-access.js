/**
 * Доступ к центру оператора и к API управления очередями (создание, список):
 * роли текущей компании из JWT — admin или owner.
 * @param {{ user?: { roles?: string[] } } | null | undefined} auth
 */
const MANAGER_ROLES = new Set(['admin', 'owner']);

export function canManageOperatorWorkbench(auth) {
    const roles = auth?.user?.roles;
    if (!Array.isArray(roles) || roles.length === 0) {
        return false;
    }
    return roles.some((r) => MANAGER_ROLES.has(String(r).toLowerCase()));
}
