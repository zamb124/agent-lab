/**
 * Права оператора для UI flows.
 */

import { isPlainObject } from './flows-resolvers.js';

const OPERATOR_ROLES = new Set(['admin', 'owner']);

export function userCanManageOperator(user, activeCompanyId) {
    if (!user) {
        return false;
    }
    if (typeof user !== 'object') {
        return false;
    }
    if (typeof activeCompanyId !== 'string') {
        return false;
    }
    const direct = isPlainObject(user.companies) ? user.companies : null;
    const rawCompanies = isPlainObject(user.raw) && isPlainObject(user.raw.companies)
        ? user.raw.companies
        : null;
    const companies = direct !== null ? direct : rawCompanies;
    if (!companies) {
        return false;
    }
    const entry = companies[activeCompanyId];
    if (!entry) {
        return false;
    }
    const list = Array.isArray(entry) ? entry : [entry];
    for (const role of list) {
        if (typeof role !== 'string') {
            continue;
        }
        if (OPERATOR_ROLES.has(role.trim().toLowerCase())) {
            return true;
        }
    }
    return false;
}
