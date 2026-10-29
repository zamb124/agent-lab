import { isPlainRecord } from '../../events/payload.js';
import type { A2aFileSource } from '../../a2a/a2a-codec.js';
import type { FlowUiRecord } from '../runtime/flow-ui-store.js';
import type { HitlConversation } from '../runtime/hitl-transport.js';

export const EDITING_CAPABILITIES = Object.freeze({ cancel: false, files: false, voice: false });

export type FlowUiStatus = 'idle' | 'loading' | 'ready' | 'error';
export type HitlMode = 'takeover' | 'single_reply';

export interface FlowUiInteractionPolicy {
    mode?: string;
    conversation?: HitlConversation;
    can_send?: boolean;
}

export function presentText(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

export function flowRecord(value: unknown): FlowUiRecord | undefined {
    if (value === undefined || value === null) {
        return undefined;
    }
    if (!isPlainRecord(value)) {
        throw new Error('platform-flow-ui: object required');
    }
    return value;
}

export function requireHitlConversation(policy: FlowUiInteractionPolicy | null): HitlConversation {
    const conversation = policy === null ? undefined : policy.conversation;
    if (conversation === undefined) {
        throw new Error('platform-flow-ui: interactionPolicy.conversation required');
    }
    return conversation;
}

export function fileSources(refs: readonly Record<string, unknown>[]): A2aFileSource[] {
    return refs.map((ref) => {
        const source: A2aFileSource = {};
        if ('url' in ref) source.url = ref.url;
        if ('content_type' in ref) source.content_type = ref.content_type;
        if ('original_name' in ref) source.original_name = ref.original_name;
        return source;
    });
}

export function formControlValue(event: Event): string {
    const target = event.target;
    if (!(target instanceof HTMLTextAreaElement) && !(target instanceof HTMLInputElement)) {
        throw new Error('platform-flow-ui: form control required');
    }
    return target.value;
}
