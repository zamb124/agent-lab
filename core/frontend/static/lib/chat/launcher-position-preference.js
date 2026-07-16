import { platformStorageKey } from '../utils/storage-keys.js';

const POSITION_KEY_PREFIX = 'lara_launcher_position';

function _storageKey(scope, branchId) {
    if (typeof branchId !== 'string' || !/^[a-z][a-z0-9_]*$/.test(branchId)) {
        throw new Error('Lara launcher branchId must be lowercase snake_case');
    }
    return platformStorageKey(scope, `${POSITION_KEY_PREFIX}.${branchId}`);
}

function _validateCoordinate(value, field) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
        throw new Error(`Lara launcher position ${field} must be a non-negative finite number`);
    }
    return value;
}

export function readLaraLauncherPosition(scope, branchId) {
    if (typeof window === 'undefined') {
        return null;
    }
    const serialized = window.localStorage.getItem(_storageKey(scope, branchId));
    if (serialized === null) {
        return null;
    }
    const parsed = JSON.parse(serialized);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Lara launcher position must be a JSON object');
    }
    return Object.freeze({
        left: _validateCoordinate(parsed.left, 'left'),
        top: _validateCoordinate(parsed.top, 'top'),
    });
}

export function writeLaraLauncherPosition(scope, branchId, position) {
    if (typeof window === 'undefined') {
        return;
    }
    if (!position || typeof position !== 'object' || Array.isArray(position)) {
        throw new Error('Lara launcher position is required');
    }
    const normalized = {
        left: _validateCoordinate(position.left, 'left'),
        top: _validateCoordinate(position.top, 'top'),
    };
    window.localStorage.setItem(_storageKey(scope, branchId), JSON.stringify(normalized));
}
