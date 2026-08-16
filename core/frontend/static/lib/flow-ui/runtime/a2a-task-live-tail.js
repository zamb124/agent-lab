/**
 * SubscribeToTask live tail. Shared by operator HITL transport and user
 * session after an operator_task interrupt closes SendStreamingMessage.
 */

import {
    a2aEndpointUrl,
    buildSubscribeTaskBody,
} from '../protocol/a2a-codec.js';
import { consumeA2AStream } from '../protocol/a2a-stream.js';

function sleep(ms, signal) {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
        }
        const timer = setTimeout(resolve, ms);
        const onAbort = () => {
            clearTimeout(timer);
            reject(new DOMException('Aborted', 'AbortError'));
        };
        signal.addEventListener('abort', onAbort, { once: true });
    });
}

/**
 * @param {{
 *   target: { baseUrl: string, flowId: string, branchId?: string, embedId?: string },
 *   taskId: string,
 *   headersFn: () => Promise<Record<string, string>>|Record<string, string>,
 *   credentials?: RequestCredentials,
 *   signal: AbortSignal,
 *   onFrame: (frame: unknown) => void,
 *   retryDelayMs?: number,
 *   restartDelayMs?: number,
 * }} options
 */
export async function runA2aTaskLiveTail(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('runA2aTaskLiveTail: options required');
    }
    const taskId = typeof options.taskId === 'string' ? options.taskId.trim() : '';
    if (taskId === '') {
        throw new Error('runA2aTaskLiveTail: taskId required');
    }
    if (typeof options.headersFn !== 'function') {
        throw new Error('runA2aTaskLiveTail: headersFn required');
    }
    if (typeof options.onFrame !== 'function') {
        throw new Error('runA2aTaskLiveTail: onFrame required');
    }
    if (!options.signal || typeof options.signal.aborted !== 'boolean') {
        throw new Error('runA2aTaskLiveTail: AbortSignal required');
    }
    const credentials = options.credentials || 'include';
    const retryDelayMs = typeof options.retryDelayMs === 'number' ? options.retryDelayMs : 800;
    const restartDelayMs = typeof options.restartDelayMs === 'number' ? options.restartDelayMs : 400;
    const { target, signal, onFrame } = options;

    while (!signal.aborted) {
        try {
            const headers = await options.headersFn();
            await consumeA2AStream(
                {
                    url: a2aEndpointUrl(target),
                    body: buildSubscribeTaskBody(taskId),
                    headers: headers && typeof headers === 'object' ? headers : {},
                    credentials,
                    signal,
                },
                onFrame,
            );
        } catch (error) {
            if (error instanceof Error && error.name === 'AbortError') break;
            try {
                await sleep(retryDelayMs, signal);
            } catch (sleepError) {
                if (sleepError instanceof Error && sleepError.name === 'AbortError') break;
                throw sleepError;
            }
            continue;
        }
        if (signal.aborted) break;
        try {
            await sleep(restartDelayMs, signal);
        } catch (sleepError) {
            if (sleepError instanceof Error && sleepError.name === 'AbortError') break;
            throw sleepError;
        }
    }
}
