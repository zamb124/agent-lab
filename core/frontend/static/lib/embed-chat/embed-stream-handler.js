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
            } else {
                out.patch.content = (msg.content || '') + text;
            }
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
            out.patch.inputRequired = { question: extractQuestionFromMessage(message) };
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
    if (ctx) {
        out.contextId = ctx;
    }

    if (taskId) {
        out.currentTaskId = taskId;
    }

    if (message?.parts) {
        const text = message.parts.filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('');
        if (text) {
            out.patch.content = (msg.content || '') + text;
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
        out.taskId = taskId;
    }

    if (state === 'input-required' || state === 'input_required') {
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
            out.patch.inputRequired = { question: extractQuestionFromMessage(message) };
        }
    }

    return out;
}
