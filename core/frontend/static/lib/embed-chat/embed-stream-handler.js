/**
 * Нормализация A2A SSE событий в патчи сообщения ассистента.
 */

import { mergeBlocksFromToolResult } from './tool-result-blocks.js';

function partText(part) {
    if (!part) {
        return '';
    }
    if (part.kind === 'text' && part.text) {
        return part.text;
    }
    if (part.root && part.root.text !== undefined) {
        return part.root.text;
    }
    return '';
}

/**
 * @param {object | null} message
 * @param {object | undefined} resultMetadata - metadata события status-update / artifact-update
 */
function buildInputRequiredPatch(message, resultMetadata) {
    const meta = resultMetadata || {};
    const msgMeta = message?.metadata || {};
    const pi = meta.platform_interrupt || msgMeta.platform_interrupt;
    if (pi && typeof pi === 'object' && pi.body && pi.body.kind) {
        const kind = pi.body.kind;
        if (kind === 'user_message') {
            return { question: pi.body.question, interruptKind: kind };
        }
        if (kind === 'operator_task') {
            return {
                question: pi.body.question,
                interruptKind: kind,
                operatorTaskTitle: pi.body.task_title,
                operatorAssigneeQueue: pi.body.assignee_queue,
                handoffMode: pi.body.handoff_mode || 'single_reply',
                operatorTaskId: pi.body.operator_task_id || null,
            };
        }
        if (kind === 'oauth_required') {
            return {
                question: pi.body.question,
                interruptKind: kind,
                authUrl: pi.body.auth_url,
                provider: pi.body.provider,
                service: pi.body.service,
            };
        }
        throw new Error(`buildInputRequiredPatch: неизвестный interrupt kind ${kind}`);
    }
    return { question: extractQuestionFromMessage(message) };
}

function extractQuestionFromMessage(message) {
    if (!message) {
        return '';
    }
    if (message.parts) {
        return message.parts
            .filter((p) => p.kind === 'text' && p.text)
            .map((p) => p.text)
            .join('');
    }
    if (typeof message === 'string') {
        return message;
    }
    if (message.text) {
        return message.text;
    }
    return '';
}

/**
 * @param {object} msg - текущее сообщение assistant (будет мутировано логически через патчи)
 * @param {object} event - сырой SSE JSON
 * @returns {{ patch: object, contextId?: string, taskId?: string, currentTaskId?: string }}
 */
export function reduceEmbedStreamEvent(msg, event) {
    const out = { patch: {} };

    if (event?.error) {
        out.patch = {
            content: event.error.message || 'Stream error',
            streaming: false,
        };
        return out;
    }

    const result = event?.result;
    if (!result) {
        return out;
    }

    const kind = result.kind;

    if (kind === 'artifact-update') {
        return reduceArtifactUpdate(msg, result, out);
    }
    if (kind === 'status-update') {
        return reduceStatusUpdate(msg, result, out);
    }

    return out;
}

function reduceArtifactUpdate(msg, result, out) {
    const artifact = result.artifact;
    const message = artifact?.message;
    const state = artifact?.state;
    const meta = result.metadata || {};
    const taskId = result.taskId || result.task_id || meta.task_id;
    const ctx = result.contextId || result.context_id;
    if (ctx) {
        out.contextId = ctx;
    }

    if (taskId) {
        out.currentTaskId = taskId;
    }

    if (artifact?.parts) {
        const text = artifact.parts.map(partText).join('');
        if (text) {
            if (artifact.name === 'reasoning') {
                out.patch.reasoning = (msg.reasoning || '') + text;
            } else if (artifact.name === 'operator_reply') {
                out.operatorMessage = text;
            } else if (artifact.name === 'operator_files') {
                // handled below via DataPart
            } else if (msg.inputRequired) {
                out.splitMessage = true;
                out.patch.content = text;
            } else {
                out.patch.content = (msg.content || '') + text;
            }
        }
    }

    if (artifact?.name === 'operator_files' && artifact?.parts) {
        const dataPart = artifact.parts.find((p) => p.data?.file_ids);
        if (dataPart) {
            out.operatorFiles = dataPart.data.file_ids;
        }
    }

    if (message?.parts) {
        const text = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
        if (text) {
            out.patch.content = (msg.content || '') + text;
        }
        const reasoning = message.parts.find((p) => p.kind === 'reasoning');
        if (reasoning?.text) {
            out.patch.reasoning = reasoning.text;
        }
    }

    if (message?.metadata?.tool_calls) {
        const existing = msg.toolCalls || [];
        const add = message.metadata.tool_calls.filter(
            (tc) => !existing.some((e) => e.id === tc.id),
        );
        if (add.length > 0) {
            out.patch.toolCalls = [...existing, ...add];
        }
    }

    if (message?.metadata?.tool_result) {
        const existing = msg.toolResults || [];
        const tr = message.metadata.tool_result;
        if (!existing.some((r) => r.id === tr.id)) {
            out.patch.toolResults = [...existing, tr];
            out.patch.blocks = mergeBlocksFromToolResult(msg.blocks || [], tr);
        }
    }

    if (state === 'completed' && result.final) {
        out.patch.streaming = false;
        out.taskId = taskId;
        if (message?.parts) {
            const text = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
            if (text && !(msg.content || '').trim()) {
                out.patch.content = text;
            }
        }
    }

    if (state === 'failed' && result.final) {
        let err = 'Request failed';
        if (message?.parts) {
            const extracted = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
            if (extracted) {
                err = extracted;
            }
        }
        out.patch.content = err;
        out.patch.streaming = false;
    }

    if ((state === 'input-required' || state === 'input_required') && result.final) {
        out.patch.streaming = false;
        out.taskId = taskId;
        const metadata = result.metadata || {};
        if (metadata.breakpoint) {
            out.patch.breakpoint = {
                node_id: metadata.breakpoint.node_id,
                state: metadata.breakpoint.state,
                step: metadata.breakpoint.step,
                data: metadata.breakpoint.data,
            };
        } else {
            out.patch.inputRequired = buildInputRequiredPatch(message, metadata);
        }
    }

    return out;
}

function reduceStatusUpdate(msg, result, out) {
    const status = result.status;
    if (!status) {
        return out;
    }
    const message = status.message;
    const state = status.state;
    const taskId = result.taskId || result.task_id || status.taskId || status.task_id;
    const ctx = result.contextId || result.context_id;
    const terminalOk = state === 'completed' || state === 'finished';
    if (ctx) {
        out.contextId = ctx;
    }

    if (taskId) {
        out.currentTaskId = taskId;
    }

    const isTerminalState = terminalOk || state === 'failed' || state === 'error';
    if (isTerminalState && message?.parts) {
        const text = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
        if (text) {
            const cur = (msg.content || '').trim();
            if (!cur) {
                out.patch.content = text;
            }
        }
    }

    if (message?.metadata?.tool_calls) {
        const existing = msg.toolCalls || [];
        const add = message.metadata.tool_calls.filter(
            (tc) => !existing.some((e) => e.id === tc.id),
        );
        if (add.length > 0) {
            out.patch.toolCalls = [...existing, ...add];
        }
    }

    if (message?.metadata?.tool_result) {
        const existing = msg.toolResults || [];
        const tr = message.metadata.tool_result;
        if (!existing.some((r) => r.id === tr.id)) {
            out.patch.toolResults = [...existing, tr];
            out.patch.blocks = mergeBlocksFromToolResult(msg.blocks || [], tr);
        }
    }

    if (state === 'completed' || state === 'finished') {
        out.patch.streaming = false;
        out.patch.inputRequired = null;
        out.taskId = taskId;
    }

    if (state === 'failed' || state === 'error') {
        let err = 'Request failed';
        if (message?.parts) {
            const extracted = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
            if (extracted) {
                err = extracted;
            }
        }
        out.patch.content = err;
        out.patch.streaming = false;
        out.patch.inputRequired = null;
        out.taskId = taskId;
    }

    if (state === 'input-required' || state === 'input_required') {
        const metadata = result.metadata || {};
        const handoffContinue = metadata.platform_handoff_continue === true;
        const oauthContinue = metadata.platform_oauth_continue === true;
        if (!result.final && (handoffContinue || oauthContinue)) {
            out.patch.inputRequired = buildInputRequiredPatch(message, metadata);
            out.patch.streaming = false;
            if (taskId) {
                out.currentTaskId = taskId;
            }
            return out;
        }
        out.patch.streaming = false;
        out.taskId = taskId;
        if (metadata.breakpoint) {
            out.patch.breakpoint = {
                node_id: metadata.breakpoint.node_id,
                state: metadata.breakpoint.state,
                step: metadata.breakpoint.step,
                data: metadata.breakpoint.data,
            };
        } else {
            out.patch.inputRequired = buildInputRequiredPatch(message, metadata);
        }
    }

    return out;
}
