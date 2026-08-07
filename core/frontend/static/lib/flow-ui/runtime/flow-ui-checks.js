/**
 * Pure evaluation of Flow UI component.checks against surface data_model values.
 * Client-first submit gate; shape mirrors core/state/flow_ui_checks.py.
 */

import { getPointer } from './flow-ui-actions.js';
import { flowUIText } from '../utils/text.js';

const VALUE_BINDING_NAMES = Object.freeze(['value', 'values', 'files']);
const ALLOWED_FUNCTIONS = Object.freeze(
    new Set(['required', 'email', 'regex', 'minLength', 'maxLength']),
);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function requireCheck(check) {
    if (!check || typeof check !== 'object') {
        throw new Error('flow-ui: check must be an object');
    }
    if (!ALLOWED_FUNCTIONS.has(check.function)) {
        throw new Error(`flow-ui: unsupported check function ${check.function}`);
    }
    return check;
}

export function resolveComponentCheckValue(dataModel, component) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui: component is required for check evaluation');
    }
    const bindings = component.bindings || {};
    for (const name of VALUE_BINDING_NAMES) {
        const path = bindings[name];
        if (typeof path === 'string' && path.startsWith('/')) {
            return getPointer(dataModel, path);
        }
    }
    return undefined;
}

export function isEmptyCheckValue(value) {
    if (value == null) return true;
    if (typeof value === 'string') return value.trim() === '';
    if (typeof value === 'boolean') return value === false;
    if (Array.isArray(value)) return value.length === 0;
    if (typeof value === 'object') return Object.keys(value).length === 0;
    return false;
}

function defaultCheckMessage(check, locale) {
    if (check.function === 'required') return flowUIText(locale, 'required_field');
    if (check.function === 'email') return flowUIText(locale, 'invalid_email');
    if (check.function === 'regex') return flowUIText(locale, 'invalid_pattern');
    if (check.function === 'minLength') {
        return flowUIText(locale, 'min_length', { value: String(check.value) });
    }
    if (check.function === 'maxLength') {
        return flowUIText(locale, 'max_length', { value: String(check.value) });
    }
    throw new Error(`flow-ui: unsupported check function ${check.function}`);
}

export function checkMessage(check, locale = 'en') {
    const normalized = requireCheck(check);
    if (typeof normalized.message === 'string' && normalized.message.trim() !== '') {
        return normalized.message;
    }
    return defaultCheckMessage(normalized, locale);
}

export function evaluateFlowUICheck(check, value, locale = 'en') {
    const normalized = requireCheck(check);
    if (normalized.function === 'required') {
        return isEmptyCheckValue(value) ? checkMessage(normalized, locale) : null;
    }
    if (isEmptyCheckValue(value)) return null;

    if (normalized.function === 'email') {
        if (typeof value !== 'string' || !EMAIL_RE.test(value.trim())) {
            return checkMessage(normalized, locale);
        }
        return null;
    }

    if (normalized.function === 'regex') {
        if (typeof normalized.pattern !== 'string' || normalized.pattern === '') {
            throw new Error('flow-ui: regex check requires pattern');
        }
        if (typeof value !== 'string') return checkMessage(normalized, locale);
        if (!new RegExp(normalized.pattern).test(value)) {
            return checkMessage(normalized, locale);
        }
        return null;
    }

    if (normalized.function === 'minLength' || normalized.function === 'maxLength') {
        if (!Number.isInteger(normalized.value)) {
            throw new Error(`flow-ui: ${normalized.function} check requires integer value`);
        }
        const text = typeof value === 'string' ? value : String(value);
        const length = text.length;
        if (normalized.function === 'minLength' && length < normalized.value) {
            return checkMessage(normalized, locale);
        }
        if (normalized.function === 'maxLength' && length > normalized.value) {
            return checkMessage(normalized, locale);
        }
        return null;
    }

    throw new Error(`flow-ui: unsupported check function ${normalized.function}`);
}

/**
 * @returns {Record<string, string>} first failing message per component_id
 */
export function evaluateFlowUIChecks(surface, { locale = 'en' } = {}) {
    if (!surface || typeof surface !== 'object') {
        throw new Error('flow-ui: surface is required for check evaluation');
    }
    const dataModel = surface.data_model || {};
    const errors = {};
    for (const component of Object.values(surface.components || {})) {
        const checks = Array.isArray(component.checks) ? component.checks : [];
        if (checks.length === 0) continue;
        const value = resolveComponentCheckValue(dataModel, component);
        for (const check of checks) {
            const failure = evaluateFlowUICheck(check, value, locale);
            if (failure != null) {
                errors[component.component_id] = failure;
                break;
            }
        }
    }
    return errors;
}

export function clearFieldErrorsForPath(fieldErrors, surface, path) {
    if (!fieldErrors || typeof fieldErrors !== 'object') return Object.freeze({});
    if (!surface || typeof surface !== 'object') {
        throw new Error('flow-ui: surface is required to clear field errors');
    }
    if (typeof path !== 'string' || !path.startsWith('/')) {
        throw new Error(`flow-ui: invalid binding path ${path}`);
    }
    const next = { ...fieldErrors };
    let changed = false;
    for (const component of Object.values(surface.components || {})) {
        const bindings = component.bindings || {};
        const bound = Object.values(bindings).includes(path);
        if (bound && next[component.component_id] != null) {
            delete next[component.component_id];
            changed = true;
        }
    }
    return changed ? Object.freeze(next) : fieldErrors;
}
