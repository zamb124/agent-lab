/**
 * Веточные ресурсы flow: резолв для UI (inline / каталог + overlay).
 */

import { isPlainObject } from './flows-resolvers.js';

export function branchDataResources(branchData) {
    if (!isPlainObject(branchData)) {
        return {};
    }
    const raw = branchData.resources;
    return isPlainObject(raw) ? raw : {};
}

export function mergeBranchResourceRef(ref, patch) {
    if (!isPlainObject(ref) || !isPlainObject(patch)) {
        throw new Error('flows-branch-resource: mergeBranchResourceRef requires plain objects');
    }
    const out = { ...ref };
    for (const [k, v] of Object.entries(patch)) {
        if (k === 'config' && isPlainObject(v)) {
            const base = isPlainObject(out.config) ? out.config : {};
            out.config = { ...base, ...v };
        } else {
            out[k] = v;
        }
    }
    return out;
}

/**
 * @param {string} selectedId
 * @param {object} editorState
 * @param {Array<{ resource_id?: string, type?: string, name?: string, description?: string, tags?: string[], config?: object }>} catalogItems
 * @returns {{ resource: object, storage: 'catalog' | 'branch' } | null}
 */
export function resolveResourceForPanel(selectedId, editorState, catalogItems) {
    if (typeof selectedId !== 'string' || selectedId.length === 0) {
        return null;
    }
    const items = Array.isArray(catalogItems) ? catalogItems : [];
    const fromCatalog = items.find((r) => r && r.resource_id === selectedId);
    if (fromCatalog) {
        return { resource: fromCatalog, storage: 'catalog' };
    }
    const bd = isPlainObject(editorState.branchData) ? editorState.branchData : null;
    const resources = branchDataResources(bd);
    const ref = resources[selectedId];
    if (!isPlainObject(ref)) {
        return null;
    }
    const rid = typeof ref.resource_id === 'string' ? ref.resource_id.trim() : '';
    const inlineType = typeof ref.type === 'string' ? ref.type.trim() : '';
    if (inlineType.length > 0) {
        return {
            storage: 'branch',
            resource: {
                resource_id: selectedId,
                type: inlineType,
                name: typeof ref.name === 'string' && ref.name.length > 0 ? ref.name : selectedId,
                description: typeof ref.description === 'string' ? ref.description : '',
                tags: Array.isArray(ref.tags) ? ref.tags : [],
                permission: Array.isArray(ref.permission) ? ref.permission : [],
                config: isPlainObject(ref.config) ? ref.config : {},
            },
        };
    }
    if (rid.length > 0) {
        const cat = items.find((r) => r && r.resource_id === rid);
        const baseCfg = cat && isPlainObject(cat.config) ? cat.config : {};
        const ov = isPlainObject(ref.config) ? ref.config : {};
        const catType = cat && typeof cat.type === 'string' ? cat.type : '';
        const catPermission = cat && Array.isArray(cat.permission) ? cat.permission : [];
        return {
            storage: 'branch',
            resource: {
                resource_id: selectedId,
                type: catType.length > 0 ? catType : '',
                name: typeof ref.name === 'string' && ref.name.length > 0
                    ? ref.name
                    : (cat && typeof cat.name === 'string' && cat.name.length > 0 ? cat.name : rid),
                description: typeof ref.description === 'string'
                    ? ref.description
                    : (cat && typeof cat.description === 'string' ? cat.description : ''),
                tags: Array.isArray(ref.tags) ? ref.tags : (cat && Array.isArray(cat.tags) ? cat.tags : []),
                permission: Array.isArray(ref.permission) ? ref.permission : catPermission,
                config: { ...baseCfg, ...ov },
            },
        };
    }
    return null;
}

export function pinnedResourceIds(nodeConfig) {
    if (!isPlainObject(nodeConfig)) {
        return [];
    }
    const raw = nodeConfig.resources;
    if (!isPlainObject(raw)) {
        return [];
    }
    const out = [];
    const seen = new Set();
    for (const [k, ref] of Object.entries(raw)) {
        if (!isPlainObject(ref)) {
            continue;
        }
        const rid = typeof ref.resource_id === 'string' && ref.resource_id.length > 0 ? ref.resource_id : k;
        if (typeof rid !== 'string' || rid.length === 0) {
            continue;
        }
        if (seen.has(rid)) {
            continue;
        }
        seen.add(rid);
        out.push(rid);
    }
    return out;
}

export function uniquePinnedResourceType(nodeConfig, editorState, catalogItems) {
    const ids = pinnedResourceIds(nodeConfig);
    const types = [];
    for (const id of ids) {
        const resolved = resolveResourceForPanel(id, editorState, catalogItems);
        if (resolved === null) {
            return null;
        }
        const resourceType = resolved.resource.type;
        if (typeof resourceType !== 'string' || resourceType.length === 0) {
            return null;
        }
        types.push(resourceType);
    }
    const unique = [...new Set(types)];
    if (unique.length !== 1) {
        return null;
    }
    return unique[0];
}
