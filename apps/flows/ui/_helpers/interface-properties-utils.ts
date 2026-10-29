import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { FlowUiDocument, FlowUiPage } from './interface-editor-domain.js';

export const HIDDEN_PROPERTIES = new Set(['type', 'blocks']);
export const CONVERSATION_DEF = 'FlowUIConversationSettings';

export function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

export function documentPages(document: FlowUiDocument | null): FlowUiPage[] {
    if (document === null) return [];
    return document.pages;
}

export function objectRows(value: unknown, label: string): Record<string, unknown>[] {
    if (!Array.isArray(value)) {
        throw new Error(`flows-interface-properties-panel: ${label} must be a list`);
    }
    const rows: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) {
            throw new Error(`flows-interface-properties-panel: ${label} item must be an object`);
        }
        rows.push(item);
    }
    return rows;
}

export function rowListCount(row: Record<string, unknown>, field: string): number {
    const items = row[field];
    if (!Array.isArray(items)) {
        throw new Error(`flows-interface-properties-panel: ${field} must be a list`);
    }
    return items.length;
}

export function actionField(action: unknown, field: string): unknown {
    if (!isPlainRecord(action)) return undefined;
    return action[field];
}

export function objectValue(value: unknown): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error('flows-interface-properties-panel: object value required');
    }
    return value;
}

export function problemParams(params: Record<string, unknown>): Record<string, string | number> {
    const result: Record<string, string | number> = {};
    for (const [key, value] of Object.entries(params)) {
        if (typeof value !== 'string' && typeof value !== 'number') {
            throw new Error(`flows-interface-properties-panel: problem param ${key} must be a string or number`);
        }
        result[key] = value;
    }
    return result;
}

export function conditionEqualsText(value: Record<string, unknown>): string {
    if (!('equals' in value)) return '';
    const equals = value.equals;
    if (typeof equals === 'string') return equals;
    return JSON.stringify(equals);
}

/** Значение условия: JSON-литерал (число, bool, null, объект) или строка как есть. */
export function parseConditionValue(text: string) {
    const trimmed = text.trim();
    if (trimmed === '') return null;
    if (/^(-?\d+(\.\d+)?|true|false|null|\{.*\}|\[.*\])$/s.test(trimmed)) return JSON.parse(trimmed);
    return trimmed;
}

export function clickKindValue(kinds: readonly { value: string }[]): string {
    const first = kinds[0];
    if (first === undefined) {
        throw new Error('flows-interface-properties-panel: click kind missing');
    }
    return first.value;
}
