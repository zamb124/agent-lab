/**
 * Чистый A2A chat runtime.
 *
 * One JSON-RPC/SSE frame in, normalized chat/runtime events out. No DOM, no
 * EventBus, без fetch, без импортов app.
 */

export const A2A_CHAT_MESSAGE_METHODS = Object.freeze(['message/send', 'message/stream']);
export const A2A_CHAT_CANCEL_METHOD = 'tasks/cancel';

export function extractA2aTextFromParts(parts) {
    if (!Array.isArray(parts)) {
        return '';
    }
    return parts
        .map((part) => {
            if (!part || typeof part !== 'object') {
                return '';
            }
            if (part.kind === 'text' && typeof part.text === 'string') {
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

export function resolveA2aTaskId(result, fallback) {
    if (result && typeof result === 'object') {
        if (typeof result.taskId === 'string' && result.taskId.length > 0) {
            return result.taskId;
        }
        if (typeof result.task_id === 'string' && result.task_id.length > 0) {
            return result.task_id;
        }
        const status = result.status;
        if (status && typeof status === 'object') {
            if (typeof status.taskId === 'string' && status.taskId.length > 0) {
                return status.taskId;
            }
            if (typeof status.task_id === 'string' && status.task_id.length > 0) {
                return status.task_id;
            }
        }
    }
    return typeof fallback === 'string' && fallback.length > 0 ? fallback : null;
}

export function resolveA2aContextId(result, fallback) {
    if (result && typeof result === 'object') {
        if (typeof result.contextId === 'string' && result.contextId.length > 0) {
            return result.contextId;
        }
        if (typeof result.context_id === 'string' && result.context_id.length > 0) {
            return result.context_id;
        }
    }
    return typeof fallback === 'string' && fallback.length > 0 ? fallback : null;
}

export function isA2aTerminalState(state, final) {
    if (state === 'completed' || state === 'finished') {
        return final === true;
    }
    if (state === 'failed' || state === 'error') {
        return true;
    }
    if ((state === 'input-required' || state === 'input_required') && final === true) {
        return true;
    }
    return false;
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
    if (typeof state === 'string') {
        if (state === 'completed' || state === 'finished' || state === 'failed' || state === 'error') {
            const text = message ? extractA2aTextFromParts(message.parts) : '';
            traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: {
                    kind: 'status_terminal',
                    terminal_state: state,
                    message_preview: text.length > 160 ? text.slice(0, 160) : text,
                },
            });
        }
    }
    if (state === 'completed' || state === 'finished') {
        const text = message ? extractA2aTextFromParts(message.parts) : '';
        events.push({
            type: 'completed',
            payload: { task_id: taskId, context_id: contextId, content: text },
        });
        return;
    }
    if (state === 'failed' || state === 'error') {
        const text = message ? extractA2aTextFromParts(message.parts) : '';
        events.push({
            type: 'failed',
            payload: { task_id: taskId, context_id: contextId, error: text.length > 0 ? text : 'error' },
        });
    }
}

function _nodeRuntimeEventsFromArtifact(out, artifact, contextId, taskId) {
    if (!artifact || typeof artifact !== 'object' || !Array.isArray(artifact.parts)) {
        return;
    }
    for (const part of artifact.parts) {
        if (!part || part.kind !== 'data' || !part.data || typeof part.data !== 'object') {
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
            out.runEvents.push({ type: 'flows/run/node_completed', payload: { node_id: nodeId } });
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: {
                    kind: 'node_complete',
                    node_id: nodeId,
                    result_preview: typeof d.result_preview === 'string' ? d.result_preview : '',
                },
            });
        } else if (ev === 'node_error') {
            const error = typeof d.error === 'string' && d.error.length > 0 ? d.error : 'error';
            out.runEvents.push({ type: 'flows/run/node_failed', payload: { node_id: nodeId, error } });
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: { kind: 'node_error', node_id: nodeId, error },
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
        if (!part || part.kind !== 'data' || !part.data || typeof part.data !== 'object') {
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
        if (artifact.name === 'ui_event' && typeof d.type === 'string' && d.type.length > 0) {
            let payloadPreview = '';
            if (d.payload !== undefined && d.payload !== null) {
                const raw = typeof d.payload === 'string' ? d.payload : JSON.stringify(d.payload);
                payloadPreview = raw.length > 100 ? raw.slice(0, 100) : raw;
            }
            out.events.push({
                type: 'ui_event',
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
            out.traceEntries.push({
                context_id: contextId,
                task_id: taskId,
                fields: { kind: 'ui_event', event_type: d.type, payload_preview: payloadPreview },
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

    const taskId = resolveA2aTaskId(result, currentTaskId);
    const frameContextId = resolveA2aContextId(result, contextId);
    if (taskId) {
        out.nextTaskId = taskId;
    }
    if (!out.taskPrimed && taskId && frameContextId) {
        out.events.push({
            type: 'task_started',
            payload: { task_id: taskId, context_id: frameContextId },
        });
        out.taskPrimed = true;
    }

    if (result.kind === 'task' || (typeof result.id === 'string' && !result.kind)) {
        return out;
    }

    if (result.kind === 'message') {
        _messageMetadataEvents(out.events, taskId, result);
        return out;
    }

    if (result.kind === 'artifact-update') {
        return _artifactUpdateToRuntimeEvents(out, result, frameContextId, taskId);
    }

    if (result.kind === 'status-update') {
        return _statusUpdateToRuntimeEvents(out, result, frameContextId, taskId);
    }

    return out;
}

function _artifactUpdateToRuntimeEvents(out, result, contextId, taskId) {
    const artifact = result.artifact;
    const final = result.final === true;
    if (artifact) {
        _nodeRuntimeEventsFromArtifact(out, artifact, contextId, taskId);
    }

    if (artifact && Array.isArray(artifact.parts)) {
        const text = extractA2aTextFromParts(artifact.parts);
        if (text) {
            if (artifact.name === 'reasoning') {
                out.events.push({ type: 'reasoning_chunk', payload: { task_id: taskId, text } });
                out.traceEntries.push({
                    context_id: contextId,
                    task_id: taskId,
                    fields: { kind: 'reasoning_chunk', char_count: text.length },
                });
            } else if (artifact.name === 'operator_reply') {
                out.events.push({ type: 'operator_reply', payload: { task_id: taskId, text } });
            } else if (artifact.name !== 'operator_files') {
                out.events.push({ type: 'content_chunk', payload: { task_id: taskId, text } });
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
            out.events.push({ type: 'content_chunk', payload: { task_id: taskId, text: textFromMessage } });
        }
    }

    const state = artifact ? artifact.state : null;
    if (final) {
        if (state === 'input-required' || state === 'input_required') {
            _inputRequiredEvent(out.events, out.traceEntries, contextId, taskId, message, result.metadata);
        } else {
            _terminalEvent(out.events, out.traceEntries, contextId, taskId, state, message);
        }
        out.terminal = isA2aTerminalState(state, final);
    }
    return out;
}

function _statusUpdateToRuntimeEvents(out, result, contextId, taskId) {
    const status = result.status;
    if (!status) {
        return out;
    }
    const message = status.message;
    const state = status.state;
    const final = result.final === true;
    const metadata = _metadataFrom(result, message);

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

    const activityTerminal =
        final
        || state === 'completed'
        || state === 'finished'
        || state === 'failed'
        || state === 'error'
        || state === 'input-required'
        || state === 'input_required'
        || state === 'canceled'
        || state === 'cancelled';
    if (!activityTerminal && taskId && message && typeof message === 'object' && Array.isArray(message.parts)) {
        const activity = extractA2aTextFromParts(message.parts);
        if (activity.length > 0) {
            out.events.push({ type: 'activity', payload: { task_id: taskId, text: activity } });
        }
    }

    if (state === 'input-required' || state === 'input_required') {
        const handoffContinue = metadata && metadata.platform_handoff_continue === true;
        const oauthContinue = metadata && metadata.platform_oauth_continue === true;
        if (final || handoffContinue || oauthContinue) {
            _inputRequiredEvent(out.events, out.traceEntries, contextId, taskId, message, metadata);
        }
        out.terminal = isA2aTerminalState(state, final);
        return out;
    }

    if (final || state === 'failed' || state === 'error') {
        _terminalEvent(out.events, out.traceEntries, contextId, taskId, state, message);
    }
    out.terminal = isA2aTerminalState(state, final);
    return out;
}
