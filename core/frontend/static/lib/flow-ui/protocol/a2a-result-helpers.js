/**
 * Чистый A2A Protocol 1.0 A2A result helpers.
 *
 * One JSON-RPC/SSE frame in, normalized chat/runtime events out. No DOM, no
 * EventBus, без fetch, без импортов app.
 *
 * Wire: `result.statusUpdate` / `result.artifactUpdate` / `result.task` /
 * `result.message`. Parts без `kind`. TaskState — `TASK_STATE_*`. Role —
 * `ROLE_USER` / `ROLE_AGENT`. Поля `final` на statusUpdate нет: граница
 * стрима = terminal/interrupted state или конец SSE.
 */

export const A2A_CHAT_MESSAGE_METHODS = Object.freeze(['SendMessage', 'SendStreamingMessage']);
export const A2A_CHAT_CANCEL_METHOD = 'CancelTask';
export const A2A_CHAT_SUBSCRIBE_METHOD = 'SubscribeToTask';

const A2A_TASK_STATE_TO_PLATFORM = Object.freeze({
    TASK_STATE_SUBMITTED: 'submitted',
    TASK_STATE_WORKING: 'working',
    TASK_STATE_COMPLETED: 'completed',
    TASK_STATE_FAILED: 'failed',
    TASK_STATE_CANCELED: 'canceled',
    TASK_STATE_INPUT_REQUIRED: 'input-required',
    TASK_STATE_REJECTED: 'rejected',
    TASK_STATE_AUTH_REQUIRED: 'auth-required',
});

/**
 * A2A 1.0 StreamResponse → `{ frameKind, event }`.
 * @param {object|null|undefined} result
 * @returns {{ frameKind: 'statusUpdate'|'artifactUpdate'|'task'|'message', event: object }|null}
 */
export function unwrapA2aStreamResult(result) {
    if (!result || typeof result !== 'object') {
        return null;
    }
    if (result.statusUpdate && typeof result.statusUpdate === 'object') {
        return { frameKind: 'statusUpdate', event: result.statusUpdate };
    }
    if (result.artifactUpdate && typeof result.artifactUpdate === 'object') {
        return { frameKind: 'artifactUpdate', event: result.artifactUpdate };
    }
    if (result.task && typeof result.task === 'object') {
        return { frameKind: 'task', event: result.task };
    }
    if (result.message && typeof result.message === 'object') {
        return { frameKind: 'message', event: result.message };
    }
    return null;
}

/** Wire `TASK_STATE_*` → platform kebab (`completed`, `input-required`, …). */
export function normalizeA2aTaskState(state) {
    if (typeof state !== 'string' || state.length === 0) {
        return null;
    }
    if (Object.prototype.hasOwnProperty.call(A2A_TASK_STATE_TO_PLATFORM, state)) {
        return A2A_TASK_STATE_TO_PLATFORM[state];
    }
    return null;
}

export function extractA2aTextFromParts(parts) {
    if (!Array.isArray(parts)) {
        return '';
    }
    return parts
        .map((part) => {
            if (!part || typeof part !== 'object') {
                return '';
            }
            if (typeof part.text === 'string') {
                return part.text;
            }
            const root = part.root;
            if (root && typeof root === 'object' && typeof root.text === 'string') {
                return root.text;
            }
            return '';
        })
        .filter((text) => text.length > 0)
        .join('');
}

function _eventFromResult(result) {
    const unwrapped = unwrapA2aStreamResult(result);
    return unwrapped ? unwrapped.event : result;
}

export function resolveA2aTaskId(result, fallback) {
    const unwrapped = unwrapA2aStreamResult(result);
    const event = unwrapped ? unwrapped.event : result;
    if (event && typeof event === 'object') {
        if (typeof event.taskId === 'string' && event.taskId.length > 0) {
            return event.taskId;
        }
        if (unwrapped && unwrapped.frameKind === 'task' && typeof event.id === 'string' && event.id.length > 0) {
            return event.id;
        }
        const status = event.status;
        if (status && typeof status === 'object') {
            if (typeof status.taskId === 'string' && status.taskId.length > 0) {
                return status.taskId;
            }
        }
    }
    return typeof fallback === 'string' && fallback.length > 0 ? fallback : null;
}

export function resolveA2aContextId(result, fallback) {
    const event = _eventFromResult(result);
    if (event && typeof event === 'object') {
        if (typeof event.contextId === 'string' && event.contextId.length > 0) {
            return event.contextId;
        }
    }
    return typeof fallback === 'string' && fallback.length > 0 ? fallback : null;
}

/** Terminal: COMPLETED / FAILED / CANCELED / REJECTED. */
export function isA2aTerminalState(state) {
    const normalized = normalizeA2aTaskState(state);
    return (
        normalized === 'completed'
        || normalized === 'failed'
        || normalized === 'canceled'
        || normalized === 'rejected'
    );
}

/** Interrupted: INPUT_REQUIRED / AUTH_REQUIRED. */
export function isA2aInterruptedState(state) {
    const normalized = normalizeA2aTaskState(state);
    return normalized === 'input-required' || normalized === 'auth-required';
}

/** Stream boundary без поля `final`: terminal или interrupted. */
export function isA2aStreamBoundaryState(state) {
    return isA2aTerminalState(state) || isA2aInterruptedState(state);
}

function _isDataPart(part) {
    return Boolean(
        part
        && typeof part === 'object'
        && part.data != null
        && typeof part.data === 'object',
    );
}

export function inputRequiredFieldsFromA2a(message, resultMetadata) {
    const resultMeta = resultMetadata && typeof resultMetadata === 'object' ? resultMetadata : {};
    let question = '';
    if (message && typeof message === 'object' && Array.isArray(message.parts)) {
        question = extractA2aTextFromParts(message.parts);
    }
    let interruptKind = null;
    let authUrl = '';
    const packed = resultMeta.platform_interrupt;
    if (packed && typeof packed === 'object') {
        if (typeof packed.question === 'string' && packed.question.length > 0) {
            question = packed.question;
        }
        const body = packed.body;
        if (body && typeof body === 'object' && typeof body.kind === 'string') {
            interruptKind = body.kind;
            if (body.kind === 'operator_task') {
                return {
                    question: typeof body.question === 'string' ? body.question : question,
                    interruptKind,
                    authUrl,
                    operatorTaskTitle: body.task_title,
                    operatorAssigneeQueue: body.assignee_queue,
                    handoffMode: typeof body.handoff_mode === 'string' && body.handoff_mode.length > 0
                        ? body.handoff_mode
                        : 'single_reply',
                    workItemId: typeof body.work_item_id === 'string' ? body.work_item_id : null,
                };
            }
            if (
                body.kind === 'oauth_required'
                && typeof body.auth_url === 'string'
                && body.auth_url.length > 0
            ) {
                authUrl = body.auth_url;
            }
            if (body.kind === 'oauth_required') {
                return {
                    question: typeof body.question === 'string' ? body.question : question,
                    interruptKind,
                    authUrl,
                    provider: body.provider,
                    service: body.service,
                };
            }
            if (body.kind === 'user_message') {
                return {
                    question: typeof body.question === 'string' ? body.question : question,
                    interruptKind,
                    authUrl,
                };
            }
            if (body.kind === 'handoff') {
                return {
                    question: typeof body.question === 'string' ? body.question : question,
                    interruptKind,
                    authUrl,
                    targetFlowId: typeof body.target_flow_id === 'string' ? body.target_flow_id : '',
                    targetFlowName: typeof body.target_name === 'string' ? body.target_name : '',
                    reason: typeof body.reason === 'string' ? body.reason : '',
                    depth: typeof body.depth === 'number' ? body.depth : 0,
                };
            }
        }
    }
    return { question, interruptKind, authUrl };
}

function _metadataFrom(result, message) {
    if (result && typeof result === 'object' && result.metadata && typeof result.metadata === 'object') {
        return result.metadata;
    }
    if (message && typeof message === 'object' && message.metadata && typeof message.metadata === 'object') {
        return message.metadata;
    }
    return {};
}

function _authorFromMetadata(metadata) {
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
        return null;
    }
    const author = metadata.author;
    return author && typeof author === 'object' && !Array.isArray(author) ? author : null;
}

function _authorFromResult(result) {
    const unwrapped = unwrapA2aStreamResult(result);
    if (!unwrapped) {
        return null;
    }
    if (unwrapped.frameKind === 'artifactUpdate') {
        return _authorFromMetadata(unwrapped.event.artifact?.metadata);
    }
    if (unwrapped.frameKind === 'message') {
        return _authorFromMetadata(unwrapped.event.metadata);
    }
    if (unwrapped.frameKind === 'statusUpdate') {
        return _authorFromMetadata(unwrapped.event.status?.message?.metadata);
    }
    return null;
}

function _messageMetadataEvents(events, taskId, message) {
    if (!taskId || !message || typeof message !== 'object') {
        return;
    }
    const metadata = message.metadata;
    if (!metadata || typeof metadata !== 'object') {
        return;
    }
    if (Array.isArray(metadata.tool_calls) && metadata.tool_calls.length > 0) {
        events.push({
            type: 'tool_calls',
            payload: { task_id: taskId, tool_calls: metadata.tool_calls },
        });
    }
    if (metadata.tool_result && typeof metadata.tool_result === 'object') {
        events.push({
            type: 'tool_result',
            payload: { task_id: taskId, tool_result: metadata.tool_result },
        });
    }
}

function _inputRequiredEvent(events, traceEntries, contextId, taskId, message, metadata) {
    if (!taskId) {
        return;
    }
    const meta = metadata && typeof metadata === 'object' ? metadata : {};
    if (meta.breakpoint) {
        const nodeFromMeta =
            typeof meta.node_id === 'string' && meta.node_id.length > 0 ? meta.node_id : '';
        let breakpointPayload;
        if (typeof meta.breakpoint === 'object' && meta.breakpoint !== null) {
            breakpointPayload = {
                node_id: typeof meta.breakpoint.node_id === 'string' ? meta.breakpoint.node_id : nodeFromMeta,
                state: meta.breakpoint.state,
                step: meta.breakpoint.step,
                data: meta.breakpoint.data,
            };
        } else {
            breakpointPayload = {
                node_id: nodeFromMeta,
                state: meta.state_snapshot,
                step: undefined,
                data: undefined,
            };
        }
        traceEntries.push({
            context_id: contextId,
            task_id: taskId,
            fields: { kind: 'breakpoint', node_id: breakpointPayload.node_id },
        });
        events.push({
            type: 'breakpoint',
            payload: { task_id: taskId, context_id: contextId, breakpoint: breakpointPayload },
        });
        return;
    }
    traceEntries.push({
        context_id: contextId,
        task_id: taskId,
        fields: { kind: 'input_required' },
    });
    events.push({
        type: 'input_required',
        payload: {
            task_id: taskId,
            context_id: contextId,
            result_metadata: meta,
            message_metadata: message && message.metadata ? message.metadata : {},
            message: typeof message === 'object' && message !== null ? message : null,
        },
    });
}

function _terminalEvent(events, traceEntries, contextId, taskId, state, message) {
    if (!taskId) {
        return;
    }
    const normalized = normalizeA2aTaskState(state);
    if (normalized === 'completed' || normalized === 'failed' || normalized === 'canceled' || normalized === 'rejected') {
        const text = message ? extractA2aTextFromParts(message.parts) : '';
        traceEntries.push({
            context_id: contextId,
            task_id: taskId,
            fields: {
                kind: 'status_terminal',
                terminal_state: normalized,
                message_preview: text.length > 160 ? text.slice(0, 160) : text,
            },
        });
    }
    if (normalized === 'completed') {
        const text = message ? extractA2aTextFromParts(message.parts) : '';
        const author = _authorFromMetadata(message?.metadata);
        events.push({
            type: 'completed',
            payload: {
                task_id: taskId,
                context_id: contextId,
                content: text,
                ...(author ? { author } : {}),
            },
        });
        return;
    }
    if (normalized === 'failed' || normalized === 'canceled' || normalized === 'rejected') {
        const text = message ? extractA2aTextFromParts(message.parts) : '';
        events.push({
            type: 'failed',
            payload: { task_id: taskId, context_id: contextId, error: text.length > 0 ? text : 'error' },
        });
    }
}

function _nodeCompletedRunPayload(d) {
    const nodeId = typeof d.node_id === 'string' ? d.node_id : '';
    const payload = { node_id: nodeId };
    if (typeof d.node_type === 'string') {
        payload.node_type = d.node_type;
    }
    if (typeof d.result_preview === 'string') {
        payload.result_preview = d.result_preview;
    }
    if (typeof d.duration_ms === 'number' && Number.isFinite(d.duration_ms)) {
        payload.duration_ms = Math.round(d.duration_ms);
    }
    if (typeof d.run_index === 'number' && Number.isFinite(d.run_index)) {
        payload.run_index = Math.floor(d.run_index);
    }
    if (typeof d.primary_field === 'string') {
        payload.primary_field = d.primary_field;
    }
    if (Array.isArray(d.diff)) {
        payload.diff = d.diff;
    }
    if (Array.isArray(d.steps)) {
        payload.steps = d.steps;
    }
    return payload;
}

function _nodeFailedRunPayload(d, error) {
    const nodeId = typeof d.node_id === 'string' ? d.node_id : '';
    const payload = { node_id: nodeId, error };
    if (typeof d.node_type === 'string') {
        payload.node_type = d.node_type;
    }
    if (typeof d.duration_ms === 'number' && Number.isFinite(d.duration_ms)) {
        payload.duration_ms = Math.round(d.duration_ms);
    }
    if (typeof d.run_index === 'number' && Number.isFinite(d.run_index)) {
        payload.run_index = Math.floor(d.run_index);
    }
    return payload;
}

function _nodeRuntimeEventsFromArtifact(out, artifact, contextId, taskId) {
    if (!artifact || typeof artifact !== 'object' || !Array.isArray(artifact.parts)) {
        return;
    }
    for (const part of artifact.parts) {
        if (!_isDataPart(part)) {
            continue;
        }
        const d = part.data;
        const ev = d.event;
        if (ev === 'edge_executed') {
            const edgeIndex = typeof d.edge_index === 'number' && Number.isFinite(d.edge_index)
                ? Math.floor(d.edge_index)
                : -1;
            const fromNode = typeof d.from_node === 'string' ? d.from_node : '';
            const toNode = typeof d.to_node === 'string' ? d.to_node : '';
            if (edgeIndex >= 0 && fromNode.length > 0 && toNode.length > 0) {
                out.runEvents.push({
                    type: 'flows/run/edge_executed',
                    payload: { edge_index: edgeIndex, from_node: fromNode, to_node: toNode },
                });
            }
            continue;
        }
        if (ev === 'edge_error') {
            const edgeIndex = typeof d.edge_index === 'number' && Number.isFinite(d.edge_index)
                ? Math.floor(d.edge_index)
                : -1;
            const fromNode = typeof d.from_node === 'string' ? d.from_node : '';
            const toNode = typeof d.to_node === 'string' ? d.to_node : '';
            if (edgeIndex >= 0 && fromNode.length > 0 && toNode.length > 0) {
                out.runEvents.push({
                    type: 'flows/run/edge_error',
                    payload: {
                        edge_index: edgeIndex,
                        from_node: fromNode,
                        to_node: toNode,
                        error: typeof d.error === 'string' ? d.error : '',
                    },
                });
            }
            continue;
        }
        const nodeId = typeof d.node_id === 'string' ? d.node_id : '';
        if (nodeId.length === 0) {
            continue;
        }
        if (ev === 'node_start') {
            out.runEvents.push({ type: 'flows/run/node_started', payload: { node_id: nodeId } });
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: {
                    kind: 'node_start',
                    node_id: nodeId,
                    node_type: typeof d.node_type === 'string' ? d.node_type : '',
                },
            });
        } else if (ev === 'node_complete') {
            const completedPayload = _nodeCompletedRunPayload(d);
            out.runEvents.push({ type: 'flows/run/node_completed', payload: completedPayload });
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: {
                    kind: 'node_complete',
                    node_id: nodeId,
                    node_type: typeof d.node_type === 'string' ? d.node_type : '',
                    result_preview: typeof d.result_preview === 'string' ? d.result_preview : '',
                    duration_ms: typeof d.duration_ms === 'number' && Number.isFinite(d.duration_ms)
                        ? Math.round(d.duration_ms)
                        : null,
                    run_index: typeof d.run_index === 'number' && Number.isFinite(d.run_index)
                        ? Math.floor(d.run_index)
                        : null,
                },
            });
        } else if (ev === 'node_error') {
            const error = typeof d.error === 'string' && d.error.length > 0 ? d.error : 'error';
            const failedPayload = _nodeFailedRunPayload(d, error);
            out.runEvents.push({ type: 'flows/run/node_failed', payload: failedPayload });
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: {
                    kind: 'node_error',
                    node_id: nodeId,
                    error,
                    node_type: typeof d.node_type === 'string' ? d.node_type : '',
                    duration_ms: typeof d.duration_ms === 'number' && Number.isFinite(d.duration_ms)
                        ? Math.round(d.duration_ms)
                        : null,
                    run_index: typeof d.run_index === 'number' && Number.isFinite(d.run_index)
                        ? Math.floor(d.run_index)
                        : null,
                },
            });
        }
    }
}

function _artifactDataEvents(out, artifact, contextId, taskId) {
    if (!artifact || !Array.isArray(artifact.parts)) {
        return;
    }
    const canMutateMessages = typeof taskId === 'string' && taskId.length > 0;
    for (const part of artifact.parts) {
        if (!_isDataPart(part)) {
            continue;
        }
        const d = part.data;
        if (typeof d.event === 'string' && typeof d.node_id === 'string') {
            continue;
        }
        if (typeof d.tool === 'string' && d.tool.length > 0 && typeof d.tool_call_id === 'string' && d.tool_call_id.length > 0) {
            if (Object.prototype.hasOwnProperty.call(d, 'args')) {
                if (canMutateMessages) {
                    out.events.push({
                        type: 'tool_calls',
                        payload: {
                            task_id: taskId,
                            tool_calls: [{ id: d.tool_call_id, name: d.tool, args: d.args }],
                        },
                    });
                }
                out.traceEntries.push({
                    context_id: contextId,
                    task_id: taskId,
                    fields: { kind: 'tool_call', tool: d.tool, tool_call_id: d.tool_call_id },
                });
            } else if (Object.prototype.hasOwnProperty.call(d, 'result')) {
                if (canMutateMessages) {
                    out.events.push({
                        type: 'tool_result',
                        payload: {
                            task_id: taskId,
                            tool_result: { id: d.tool_call_id, name: d.tool, result: d.result },
                        },
                    });
                }
                out.traceEntries.push({
                    context_id: contextId,
                    task_id: taskId,
                    fields: { kind: 'tool_result', tool: d.tool, tool_call_id: d.tool_call_id },
                });
            }
            continue;
        }
        if (Array.isArray(d.file_ids)) {
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: { kind: 'operator_files', file_count: d.file_ids.length },
            });
            continue;
        }
        if (artifact.name === '__removed_ui_event__' && typeof d.type === 'string' && d.type.length > 0) {
            let payloadPreview = '';
            if (d.payload !== undefined && d.payload !== null) {
                const raw = typeof d.payload === 'string' ? d.payload : JSON.stringify(d.payload);
                payloadPreview = raw.length > 100 ? raw.slice(0, 100) : raw;
            }
            out.events.push({
                type: 'artifact_data',
                payload: {
                    task_id: taskId,
                    context_id: contextId,
                    event: d,
                },
            });
            if (d.type.startsWith('browser.preview.') && canMutateMessages) {
                out.events.push({
                    type: 'browser_preview_event',
                    payload: {
                        task_id: taskId,
                        context_id: contextId,
                        event: {
                            id: typeof d.id === 'string' ? d.id : '',
                            type: d.type,
                            payload: d.payload && typeof d.payload === 'object' ? d.payload : {},
                            timestamp: typeof d.timestamp === 'string' ? d.timestamp : '',
                        },
                    },
                });
            }
            if (d.type.startsWith('files.') && canMutateMessages) {
                out.events.push({
                    type: 'files_event',
                    payload: {
                        task_id: taskId,
                        context_id: contextId,
                        event: {
                            id: typeof d.id === 'string' ? d.id : '',
                            type: d.type,
                            payload: d.payload && typeof d.payload === 'object' ? d.payload : {},
                            timestamp: typeof d.timestamp === 'string' ? d.timestamp : '',
                        },
                    },
                });
            }
            if (d.type === 'platform.handoff_initiated') {
                out.events.push({
                    type: 'handoff_initiated',
                    payload: { task_id: taskId, context_id: contextId, ...(d.payload || {}) },
                });
            }
            if (d.type === 'platform.handback_completed') {
                out.events.push({
                    type: 'handback_completed',
                    payload: { task_id: taskId, context_id: contextId, ...(d.payload || {}) },
                });
            }
            if (d.type === 'platform.skill_loaded') {
                out.events.push({
                    type: 'skill_loaded',
                    payload: { task_id: taskId, context_id: contextId, ...(d.payload || {}) },
                });
            }
            if (d.type === 'platform.reflection_resolved') {
                out.events.push({
                    type: 'reflection_resolved',
                    payload: { task_id: taskId, context_id: contextId, ...(d.payload || {}) },
                });
            }
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: { kind: 'artifact_data', event_type: d.type, payload_preview: payloadPreview },
            });
            continue;
        }
        if (artifact.name === 'artifact' && typeof d.content === 'string' && d.content.length > 0) {
            const content = d.content;
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: { kind: 'flow_artifact', preview: content.length > 120 ? content.slice(0, 120) : content },
            });
        }
    }
}

function _emptyOut(currentTaskId, taskPrimed) {
    return {
        events: [],
        runEvents: [],
        traceEntries: [],
        nextTaskId: currentTaskId,
        taskPrimed,
        terminal: false,
    };
}

export function mapA2aResultToChatRuntimeEvents(result, options = {}) {
    const contextId = typeof options.contextId === 'string' && options.contextId.length > 0 ? options.contextId : null;
    const currentTaskId = typeof options.currentTaskId === 'string' && options.currentTaskId.length > 0
        ? options.currentTaskId
        : null;
    const out = _emptyOut(currentTaskId, options.taskPrimed === true);
    if (!result || typeof result !== 'object') {
        return out;
    }

    const unwrapped = unwrapA2aStreamResult(result);
    if (!unwrapped) {
        return out;
    }
    const event = unwrapped.event;

    const taskId = resolveA2aTaskId(result, currentTaskId);
    const frameContextId = resolveA2aContextId(result, contextId);
    // Активный conversation context клиента главнее frame.context_id: handoff child
    // emit'ит `{parent}:handoff:{flow}`, но лента чата живёт в parent context.
    const effectiveContextId = contextId || frameContextId;
    if (taskId) {
        out.nextTaskId = taskId;
    }
    const frameAuthor = _authorFromResult(result);
    if (!out.taskPrimed && taskId && effectiveContextId) {
        out.events.push({
            type: 'task_started',
            payload: {
                task_id: taskId,
                context_id: effectiveContextId,
                ...(frameAuthor ? { author: frameAuthor } : {}),
            },
        });
        out.taskPrimed = true;
    }

    if (unwrapped.frameKind === 'task') {
        return out;
    }

    if (unwrapped.frameKind === 'message') {
        _messageMetadataEvents(out.events, taskId, event);
        return out;
    }

    if (unwrapped.frameKind === 'artifactUpdate') {
        return _artifactUpdateToRuntimeEvents(out, event, effectiveContextId, taskId);
    }

    if (unwrapped.frameKind === 'statusUpdate') {
        return _statusUpdateToRuntimeEvents(out, event, effectiveContextId, taskId);
    }

    return out;
}

function _artifactUpdateToRuntimeEvents(out, event, contextId, taskId) {
    const artifact = event.artifact;
    const author = _authorFromMetadata(artifact?.metadata);
    if (artifact) {
        _nodeRuntimeEventsFromArtifact(out, artifact, contextId, taskId);
    }

    if (artifact && Array.isArray(artifact.parts)) {
        const text = extractA2aTextFromParts(artifact.parts);
        if (text) {
            if (artifact.name === 'reasoning') {
                out.events.push({
                    type: 'reasoning_chunk',
                    payload: {
                        task_id: taskId,
                        context_id: contextId,
                        text,
                        ...(author ? { author } : {}),
                    },
                });
                out.traceEntries.push({
                    context_id: contextId,
                    task_id: taskId,
                    fields: { kind: 'reasoning_chunk', char_count: text.length },
                });
            } else if (artifact.name === 'operator_reply') {
                out.events.push({ type: 'operator_reply', payload: { task_id: taskId, text } });
            } else if (artifact.name === 'user_message') {
                out.events.push({
                    type: 'user_message_added',
                    payload: {
                        contextId,
                        message: {
                            id: `hitl-user-stream-${taskId}-${Date.now()}`,
                            role: 'user',
                            content: text,
                            timestamp: new Date().toISOString(),
                            files: [],
                        },
                    },
                });
            } else if (artifact.name !== 'operator_files') {
                out.events.push({
                    type: 'content_chunk',
                    payload: {
                        task_id: taskId,
                        context_id: contextId,
                        text,
                        ...(author ? { author } : {}),
                    },
                });
            }
        }
        if (artifact.name === 'operator_files') {
            const dataPart = artifact.parts.find((p) => p && p.data && Array.isArray(p.data.file_ids));
            if (dataPart) {
                out.events.push({
                    type: 'operator_files',
                    payload: { task_id: taskId, file_ids: dataPart.data.file_ids },
                });
            }
        }
        _artifactDataEvents(out, artifact, contextId, taskId);
    }

    const message = artifact && artifact.message ? artifact.message : null;
    if (message) {
        _messageMetadataEvents(out.events, taskId, message);
        const textFromMessage = extractA2aTextFromParts(message.parts);
        if (textFromMessage) {
            out.events.push({
                type: 'content_chunk',
                payload: {
                    task_id: taskId,
                    context_id: contextId,
                    text: textFromMessage,
                    ...(_authorFromMetadata(message.metadata)
                        ? { author: _authorFromMetadata(message.metadata) }
                        : {}),
                },
            });
        }
    }

    return out;
}

function _statusUpdateToRuntimeEvents(out, event, contextId, taskId) {
    const status = event.status;
    if (!status) {
        return out;
    }
    const message = status.message;
    const state = status.state;
    const normalized = normalizeA2aTaskState(state);
    const metadata = _metadataFrom(event, message);

    if (metadata && metadata.platform_ping === true) {
        out.events.push({
            type: 'stream_ping',
            payload: {
                task_id: taskId,
                context_id: contextId,
                sent_at: typeof metadata.sent_at === 'string' ? metadata.sent_at : '',
                received_at: Date.now(),
                sequence: typeof metadata.sequence === 'number' ? metadata.sequence : null,
            },
        });
        return out;
    }

    if (message) {
        _messageMetadataEvents(out.events, taskId, message);
    }

    if (
        !isA2aStreamBoundaryState(state)
        && taskId
        && message
        && typeof message === 'object'
        && Array.isArray(message.parts)
    ) {
        const activity = extractA2aTextFromParts(message.parts);
        if (activity.length > 0) {
            out.events.push({ type: 'activity', payload: { task_id: taskId, text: activity } });
        }
    }

    if (normalized === 'input-required' || normalized === 'auth-required') {
        _inputRequiredEvent(out.events, out.traceEntries, contextId, taskId, message, metadata);
        const interrupt = metadata && metadata.platform_interrupt;
        const body = interrupt && typeof interrupt === 'object' ? interrupt.body : null;
        // Backend RedisSubscriber closes SendStreamingMessage on an agent handoff.
        // Interrupted state is the stream boundary (нет поля final).
        if (body && typeof body === 'object' && body.kind === 'handoff') {
            out.terminal = true;
            return out;
        }
        // HITL: закрываем SendStreamingMessage → ChatController.syncHitlLiveTail (SubscribeToTask).
        if (body && typeof body === 'object' && body.kind === 'operator_task') {
            out.terminal = true;
            return out;
        }
        out.terminal = true;
        return out;
    }

    if (isA2aTerminalState(state)) {
        _terminalEvent(out.events, out.traceEntries, contextId, taskId, state, message);
        out.terminal = true;
        return out;
    }
    out.terminal = false;
    return out;
}
