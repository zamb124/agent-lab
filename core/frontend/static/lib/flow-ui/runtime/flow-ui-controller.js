import {
    a2aEndpointUrl,
    buildCancelTaskBody,
    buildFlowUIMessage,
    buildListTasksBody,
    buildSendMessageBody,
    createProtocolId,
    flowUIShareCollectionUrl,
    normalizeFlowUIBranchId,
} from '../protocol/a2a-codec.js';
import { consumeA2AStream, flowUIIsAbortError, sendA2ARequest } from '../protocol/a2a-stream.js';
import {
    applyA2AFrame as accumulateA2AFrame,
    createA2ATaskAccumulator,
    serializableTask,
    taskBoundary,
} from '../protocol/a2a-task-accumulator.js';
import { applyA2UIArtifact, isA2UIArtifact } from '../protocol/a2ui-0-9-1-codec.js';
import { FLOW_UI_ACTIONS } from '../protocol/constants.js';
import { FlowUIAutosync } from './flow-ui-autosync.js';
import { setPointer, getPointer } from './flow-ui-actions.js';
import {
    clearFieldErrorsForPath,
    evaluateFlowUIChecks,
} from './flow-ui-checks.js';
import { applyFlowUIProfileKindOverrides, fetchFlowUIProfile } from './flow-ui-profile.js';
import { readRecoveryJournal, writeRecoveryJournal } from './flow-ui-recovery-journal.js';
import { cloneSerializable } from '../utils/clone.js';
import { resolveFlowUILocale } from '../utils/text.js';
import { buildFlowSessionFileCreateSpecJson } from '../../utils/file-create-spec.js';
import { resolvePlatformFileRefs } from '../../utils/platform-file-upload.js';
import {
    activeFlowUIContext,
    createFlowUIRuntimeState,
    reduceFlowUIState,
} from './flow-ui-state.js';

function clone(value) {
    return cloneSerializable(value);
}

function freezeDetail(value) {
    return Object.freeze(value && typeof value === 'object' ? { ...value } : { value });
}

function unwrapFrame(frame) {
    const result = frame?.result || frame;
    if (result?.artifactUpdate) return { kind: 'artifactUpdate', value: result.artifactUpdate };
    if (result?.task) return { kind: 'task', value: result.task };
    if (result?.id && result?.status) return { kind: 'task', value: result };
    return null;
}

function uiArtifacts(wrapped) {
    if (!wrapped) return [];
    if (wrapped.kind === 'artifactUpdate') return wrapped.value?.artifact ? [wrapped.value.artifact] : [];
    return (wrapped.value?.artifacts || []).filter((artifact) => (
        isA2UIArtifact(artifact)
        || (artifact?.parts || []).some((part) => part?.data?.flowUi)
    ));
}

export class FlowUIController extends EventTarget {
    constructor({
        flowId = '', branchId = 'default', embedId = '', baseUrl = '', contextId = '',
        headers = null, credentials = 'include', initialDocument = null, profile = null,
        profileKind = 'spa',
        autosyncDelay = 320,
        getExtraMetadataVariables = null,
    } = {}) {
        super();
        this.target = { flowId, branchId: normalizeFlowUIBranchId(branchId), embedId, baseUrl };
        this.contextId = contextId || '';
        this.headers = headers;
        this.credentials = credentials;
        this.getExtraMetadataVariables = typeof getExtraMetadataVariables === 'function'
            ? getExtraMetadataVariables
            : null;
        this.state = createFlowUIRuntimeState();
        this.accumulator = createA2ATaskAccumulator();
        this.abortController = null;
        this.profileOverride = profile;
        this.profileKind = typeof profileKind === 'string' && profileKind.trim() !== ''
            ? profileKind
            : 'spa';
        this.initialDocument = initialDocument ? clone(initialDocument) : null;
        this.localPreview = this.initialDocument !== null;
        this.autosync = new FlowUIAutosync(() => this.sync(), autosyncDelay);
        this.fieldErrors = Object.freeze({});
        this.locale = resolveFlowUILocale('auto');
    }

    get activeContext() {
        return activeFlowUIContext(this.state);
    }

    get document() {
        return this.activeContext?.document || null;
    }

    get profile() {
        return this.state.profile;
    }

    _canInteract() {
        return this.profile?.viewer?.can_interact !== false;
    }

    _assertCanInteract(operation) {
        if (!this._canInteract()) {
            throw new Error(`flow-ui: ${operation} is unavailable for a read-only viewer`);
        }
    }

    _headers() {
        const value = typeof this.headers === 'function' ? this.headers() : this.headers;
        return value && typeof value === 'object' ? value : {};
    }

    async _resolveExtraMetadataVariables() {
        if (typeof this.getExtraMetadataVariables !== 'function') {
            return null;
        }
        const variables = await this.getExtraMetadataVariables();
        if (variables == null) {
            return null;
        }
        if (typeof variables !== 'object' || Array.isArray(variables)) {
            throw new Error('flow-ui: getExtraMetadataVariables must return a plain object');
        }
        return variables;
    }

    _commit(event) {
        this.state = reduceFlowUIState(this.state, event);
        this.dispatchEvent(new CustomEvent('change', { detail: freezeDetail({ state: this.state, event }) }));
    }

    _emit(name, detail) {
        this.dispatchEvent(new CustomEvent(name, { detail: freezeDetail(detail) }));
    }

    async connect() {
        this.abortController?.abort();
        this.abortController = new AbortController();
        if (this.profileOverride) {
            this._commit({
                type: 'profile.loaded',
                profile: applyFlowUIProfileKindOverrides(this.profileOverride, this.profileKind),
            });
        } else {
            const profile = await fetchFlowUIProfile({
                target: this.target, headers: this._headers(), credentials: this.credentials,
                signal: this.abortController.signal,
            });
            this._commit({
                type: 'profile.loaded',
                profile: applyFlowUIProfileKindOverrides(profile, this.profileKind),
            });
        }
        if (this.initialDocument) {
            this.contextId = this.contextId || `preview:${createProtocolId('context')}`;
            this._commit({ type: 'context.hydrated', contextId: this.contextId, document: clone(this.initialDocument) });
            return this.state;
        }
        await this.bootstrap();
        return this.state;
    }

    async bootstrap() {
        if (!this.contextId) this.contextId = createProtocolId('context');
        this._commit({ type: 'context.loading', contextId: this.contextId });
        try {
            // A2A Tasks are immutable projections. A fresh control identity is
            // mandatory so reopening a context cannot replay an older bootstrap Task.
            const bootstrapId = createProtocolId('bootstrap');
            // Standing host variables (Lara flow_id/node_id/…) are submit-scoped.
            // Bootstrap only hydrates the authoritative document; do not call the host hook here.
            const command = buildFlowUIMessage({
                kind: 'bootstrap', contextId: this.contextId, branchId: this.target.branchId,
                actionId: bootstrapId,
                clientMutationId: bootstrapId,
            });
            const frame = await sendA2ARequest({
                url: a2aEndpointUrl(this.target), body: buildSendMessageBody(command),
                headers: this._headers(), credentials: this.credentials,
                signal: this.abortController?.signal,
            });
            this.applyA2AFrame(frame);
            if (!this.document) throw new Error('Flow UI bootstrap returned no authoritative document');
            await this.hydrateContextTasks();
            this._rebaseRecoveryJournal();
            this._emit('flow-ui-ready', { contextId: this.contextId, document: this.document });
        } catch (error) {
            if (flowUIIsAbortError(error)) throw error;
            this._commit({ type: 'context.failed', contextId: this.contextId, error });
            this._emit('flow-ui-error', { error, contextId: this.contextId });
            throw error;
        }
    }

    async hydrateContextTasks() {
        if (typeof this.contextId !== 'string' || this.contextId.trim() === '') {
            throw new Error('flow-ui: hydrateContextTasks requires contextId');
        }
        let pageToken = '';
        for (let page = 0; page < 20; page += 1) {
            const frame = await sendA2ARequest({
                url: a2aEndpointUrl(this.target),
                body: buildListTasksBody({
                    contextId: this.contextId,
                    pageSize: 50,
                    pageToken,
                    includeArtifacts: true,
                }),
                headers: this._headers(),
                credentials: this.credentials,
                signal: this.abortController?.signal,
            });
            const result = frame?.result;
            if (!result || !Array.isArray(result.tasks)) {
                throw new Error('flow-ui: ListTasks returned no tasks array');
            }
            for (const task of result.tasks) {
                // Historical Task snapshots hydrate the accumulator only.
                // Document authority stays with the bootstrap ui.document Artifact.
                accumulateA2AFrame(this.accumulator, { result: { task } });
            }
            const contextId = this.contextId;
            const tasks = Object.fromEntries(
                this.accumulator.taskOrder
                    .map((id) => this.accumulator.tasksById[id])
                    .filter((item) => item.contextId === contextId)
                    .map((item) => [item.id, serializableTask(item)]),
            );
            const order = this.accumulator.taskOrder.filter((id) => tasks[id]);
            const active = [...order].reverse().find((id) => !taskBoundary(this.accumulator.tasksById[id])) || order.at(-1) || null;
            this._commit({ type: 'tasks.changed', contextId, tasksById: tasks, taskOrder: order, activeTaskId: active });
            const next = typeof result.nextPageToken === 'string' ? result.nextPageToken : '';
            if (next === '') {
                return;
            }
            pageToken = next;
        }
        throw new Error('flow-ui: ListTasks pagination exceeded safe page limit');
    }

    applyA2AFrame(frame) {
        const wrapped = unwrapFrame(frame);
        const result = accumulateA2AFrame(this.accumulator, frame);
        let nextDocument = this.document;
        for (const artifact of uiArtifacts(wrapped)) nextDocument = applyA2UIArtifact(nextDocument, artifact);
        const task = result.changedTaskId ? this.accumulator.tasksById[result.changedTaskId] : null;
        const contextId = task?.contextId || this.contextId;
        if (contextId && contextId !== this.contextId) this.contextId = contextId;
        if (nextDocument && contextId) {
            this._commit({ type: 'context.hydrated', contextId, document: nextDocument });
        }
        if (contextId) {
            const tasks = Object.fromEntries(
                this.accumulator.taskOrder
                    .map((id) => this.accumulator.tasksById[id])
                    .filter((item) => item.contextId === contextId)
                    .map((item) => [item.id, serializableTask(item)]),
            );
            const order = this.accumulator.taskOrder.filter((id) => tasks[id]);
            const active = [...order].reverse().find((id) => !taskBoundary(this.accumulator.tasksById[id])) || order.at(-1) || null;
            this._commit({ type: 'tasks.changed', contextId, tasksById: tasks, taskOrder: order, activeTaskId: active });
        }
        this._emit('flow-ui-a2a-frame', { frame, taskId: result.changedTaskId, contextId });
    }

    setValue(surfaceId, path, value) {
        const context = this.activeContext;
        if (!context?.document) throw new Error('flow-ui: document is not hydrated');
        if (!this.localPreview) this._assertCanInteract('editing');
        const surface = context.document.surfaces?.[surfaceId];
        if (!surface) throw new Error(`flow-ui: unknown surface ${surfaceId}`);
        const document = clone(context.document);
        document.surfaces[surfaceId].data_model = setPointer(surface.data_model, path, value);
        this.fieldErrors = clearFieldErrorsForPath(this.fieldErrors, surface, path);
        if (this.localPreview) {
            this._commit({ type: 'document.preview', contextId: this.contextId, document });
            this._emit('flow-ui-value-change', {
                surfaceId, path, value: clone(value), mutationId: null, preview: true,
            });
            return;
        }
        const mutation = {
            id: createProtocolId('mutation'), surfaceId, path, value: clone(value),
            baseRevision: context.serverRevision, createdAt: new Date().toISOString(),
        };
        this._commit({ type: 'document.local', contextId: this.contextId, document, mutation });
        writeRecoveryJournal({ ...this.target, contextId: this.contextId }, this.activeContext.pendingMutations);
        if (this.profile?.capabilities?.autosync !== false) this.autosync.schedule();
        this._emit('flow-ui-value-change', { surfaceId, path, value, mutationId: mutation.id });
    }

    navigate(pageId) {
        const context = this.activeContext;
        if (!context?.document?.pages?.[pageId]) throw new Error(`flow-ui: unknown page ${pageId}`);
        const document = clone(context.document);
        document.active_page_id = pageId;
        if (this.localPreview || this.profile?.capabilities?.autosync === false) {
            this._commit({ type: 'document.preview', contextId: this.contextId, document });
            this._emit('flow-ui-navigation', { contextId: this.contextId, pageId, persisted: false });
            return;
        }
        this._assertCanInteract('navigation persistence');
        const mutation = {
            id: createProtocolId('mutation'), kind: 'navigate', pageId,
            baseRevision: context.serverRevision, createdAt: new Date().toISOString(),
        };
        this._commit({ type: 'document.local', contextId: this.contextId, document, mutation });
        writeRecoveryJournal({ ...this.target, contextId: this.contextId }, this.activeContext.pendingMutations);
        this.autosync.schedule();
        this._emit('flow-ui-navigation', { contextId: this.contextId, pageId, persisted: true });
    }

    async uploadFiles(surfaceId, componentId, path, files, { append = false } = {}) {
        if (!path || typeof path !== 'string') {
            throw new Error('flow-ui: FileUpload requires a /values binding');
        }
        if (typeof append !== 'boolean') {
            throw new Error('flow-ui: uploadFiles append must be boolean');
        }
        const list = Array.from(files || []);
        if (list.length === 0) return [];
        if (this.localPreview) {
            const refs = list.map((file) => ({
                file_id: `preview:${createProtocolId('file')}`,
                original_name: file.name || 'file',
                content_type: file.type || 'application/octet-stream',
                file_size: Number(file.size || 0),
                url: null,
                preview: true,
            }));
            const merged = append
                ? [...this._existingFileRefs(surfaceId, path), ...refs]
                : refs;
            this.setValue(surfaceId, path, merged);
            this._emit('flow-ui-files-ready', { componentId, surfaceId, files: merged, preview: true });
            return merged;
        }
        this._assertCanInteract('file upload');
        if (this.profile?.capabilities?.files !== true) {
            throw new Error('flow-ui: file upload is disabled by the interface profile');
        }
        const flowId = String(this.profile?.flow_id || this.target.flowId || '').trim();
        if (!flowId || !this.contextId) {
            throw new Error('flow-ui: flow and context identity are required for file upload');
        }
        const refs = await resolvePlatformFileRefs(list, {
            credentials: this.credentials,
            headers: this._headers(),
            routeSegment: 'flows',
            buildSpec: () => buildFlowSessionFileCreateSpecJson({
                flowId,
                sessionId: `${flowId}:${this.contextId}`,
            }),
            onProgress: (progress) => this._emit('flow-ui-file-progress', {
                ...progress, componentId, surfaceId,
            }),
        });
        const merged = append
            ? [...this._existingFileRefs(surfaceId, path), ...refs]
            : refs;
        this.setValue(surfaceId, path, merged);
        this._emit('flow-ui-files-ready', { componentId, surfaceId, files: merged, preview: false });
        return merged;
    }

    _existingFileRefs(surfaceId, path) {
        const surface = this.document?.surfaces?.[surfaceId];
        if (!surface?.data_model) return [];
        const current = getPointer(surface.data_model, path);
        if (current == null) return [];
        if (!Array.isArray(current)) {
            throw new Error(`flow-ui: file binding ${path} must be an array`);
        }
        return current;
    }

    _clearComposerValues(surfaceId) {
        const context = this.activeContext;
        const surface = context?.document?.surfaces?.[surfaceId];
        if (!surface?.data_model?.values || typeof surface.data_model.values !== 'object') {
            return;
        }
        let document = clone(context.document);
        let changed = false;
        if (Object.hasOwn(surface.data_model.values, 'message')) {
            document.surfaces[surfaceId].data_model = setPointer(
                document.surfaces[surfaceId].data_model,
                '/values/message',
                '',
            );
            changed = true;
        }
        if (Object.hasOwn(surface.data_model.values, 'files')) {
            document.surfaces[surfaceId].data_model = setPointer(
                document.surfaces[surfaceId].data_model,
                '/values/files',
                [],
            );
            changed = true;
        }
        if (!changed) return;
        // Local-only: server submit persists cleared drafts; do not enqueue autosync.
        this._commit({ type: 'document.preview', contextId: this.contextId, document });
    }

    async _sendControl(
        kind,
        mutationId,
        {
            surfaceId = 'main',
            sourceComponentId = 'root',
            actionContext = {},
            wireDocument = null,
        } = {},
    ) {
        if (this.localPreview) throw new Error(`flow-ui: ${kind} cannot run from a local preview`);
        this._assertCanInteract(kind);
        const context = this.activeContext;
        if (!context?.document) throw new Error(`flow-ui: cannot ${kind} before hydration`);
        const documentForWire = wireDocument == null ? clone(context.document) : clone(wireDocument);
        documentForWire.revision = context.serverRevision;
        // Lara standing context is required on submit (LLM tools). Sync only persists UI values.
        const variables = kind === 'submit' ? await this._resolveExtraMetadataVariables() : null;
        const metadata = variables == null ? {} : { variables };
        const command = buildFlowUIMessage({
            kind, contextId: this.contextId, document: documentForWire,
            surfaceId, sourceComponentId, actionContext,
            branchId: this.target.branchId, clientMutationId: mutationId,
            actionId: kind === 'submit' ? mutationId : createProtocolId(kind),
            metadata,
        });
        if (kind === 'submit') {
            await consumeA2AStream({
                url: a2aEndpointUrl(this.target), body: buildSendMessageBody(command, { streaming: true }),
                headers: this._headers(), credentials: this.credentials,
                signal: this.abortController?.signal,
            }, (frame) => this.applyA2AFrame(frame));
        } else {
            const frame = await sendA2ARequest({
                url: a2aEndpointUrl(this.target), body: buildSendMessageBody(command),
                headers: this._headers(), credentials: this.credentials,
                signal: this.abortController?.signal,
            });
            this.applyA2AFrame(frame);
        }
        return command;
    }

    async sync() {
        if (this.localPreview) return;
        const context = this.activeContext;
        if (!context?.document || context.pendingMutations.length === 0) return;
        this._assertCanInteract('sync');
        const mutation = context.pendingMutations.at(-1);
        const mutationIds = context.pendingMutations.map((item) => item.id);
        try {
            await this._sendControl('sync', mutation.id);
            const document = this.document;
            this._commit({
                type: 'document.ack', contextId: this.contextId, document,
                mutationId: mutation.id, mutationIds,
            });
            writeRecoveryJournal(
                { ...this.target, contextId: this.contextId },
                this.activeContext.pendingMutations,
            );
            this._emit('flow-ui-saved', { contextId: this.contextId, revision: document.revision });
        } catch (error) {
            if (flowUIIsAbortError(error)) throw error;
            this._commit({ type: 'document.conflict', contextId: this.contextId, conflict: error });
            this._emit('flow-ui-conflict', { contextId: this.contextId, error });
            throw error;
        }
    }

    async submit(surfaceId, componentId, actionContext = {}) {
        const surface = this.document?.surfaces?.[surfaceId];
        if (!surface) throw new Error(`flow-ui: unknown surface ${surfaceId}`);
        const fieldErrors = evaluateFlowUIChecks(surface, { locale: this.locale });
        if (Object.keys(fieldErrors).length > 0) {
            this.fieldErrors = Object.freeze({ ...fieldErrors });
            this._emit('flow-ui-validation-failed', {
                contextId: this.contextId,
                surfaceId,
                componentId,
                fieldErrors: this.fieldErrors,
                firstComponentId: Object.keys(fieldErrors)[0],
            });
            this.dispatchEvent(new CustomEvent('change', {
                detail: freezeDetail({
                    state: this.state,
                    event: { type: 'validation.failed', surfaceId, fieldErrors: this.fieldErrors },
                }),
            }));
            return { blocked: true, fieldErrors: this.fieldErrors };
        }
        this.fieldErrors = Object.freeze({});

        if (this.localPreview) {
            const detail = {
                contextId: this.contextId,
                surfaceId,
                componentId,
                actionContext: clone(actionContext),
                document: clone(this.document),
                preview: true,
            };
            this._clearComposerValues(surfaceId);
            this._emit('flow-ui-preview-submit', detail);
            return detail;
        }
        this._assertCanInteract('submit');
        if (this.activeContext?.submitting === true) return;
        this._commit({ type: 'submit.started', contextId: this.contextId });
        this._emit('flow-ui-submit-start', { contextId: this.contextId, surfaceId, componentId });
        try {
            await this.autosync.flushNow();
            const mutationId = createProtocolId('submit');
            const draftText = this._composerDraftText(surfaceId);
            const draftFiles = this._composerDraftFiles(surfaceId);
            if (draftText !== '' || draftFiles.length > 0) {
                this._commit({
                    type: 'turn.optimistic',
                    contextId: this.contextId,
                    turn: { id: mutationId, text: draftText, files: draftFiles },
                });
            }
            // Wire snapshot keeps submitted message; local document clears so stream
            // snapshots cannot resurrect the draft into the composer.
            const wireDocument = clone(this.document);
            this._clearComposerValues(surfaceId);
            await this._sendControl('submit', mutationId, {
                surfaceId,
                sourceComponentId: componentId,
                actionContext,
                wireDocument,
            });
        } catch (error) {
            // Host disconnect / route change aborts the SSE body; do not surface as failure.
            if (flowUIIsAbortError(error)) return;
            throw error;
        } finally {
            this._commit({ type: 'submit.finished', contextId: this.contextId });
            this._emit('flow-ui-submit-end', {
                contextId: this.contextId,
                taskId: this.activeContext?.activeTaskId,
            });
        }
    }

    _composerDraftText(surfaceId) {
        const surface = this.document?.surfaces?.[surfaceId];
        const message = surface?.data_model?.values?.message;
        if (typeof message !== 'string') return '';
        return message.trim();
    }

    _composerDraftFiles(surfaceId) {
        const surface = this.document?.surfaces?.[surfaceId];
        const files = surface?.data_model?.values?.files;
        if (!Array.isArray(files)) return [];
        return files.filter((ref) => ref && typeof ref === 'object').map((ref) => clone(ref));
    }

    async cancelActiveTask() {
        this._assertCanInteract('cancel');
        if (this.profile?.capabilities?.cancel !== true) {
            throw new Error('flow-ui: task cancellation is disabled by the interface profile');
        }
        const taskId = this.activeContext?.activeTaskId;
        if (!taskId) return;
        try {
            const frame = await sendA2ARequest({
                url: a2aEndpointUrl(this.target), body: buildCancelTaskBody(taskId),
                headers: this._headers(), credentials: this.credentials,
                signal: this.abortController?.signal,
            });
            this.applyA2AFrame(frame);
        } catch (error) {
            if (flowUIIsAbortError(error)) return;
            throw error;
        }
    }

    async startNewContext() {
        if (this.profile?.viewer?.auth_mode === 'share') {
            throw new Error('flow-ui: a shared grant is scoped to one existing context');
        }
        this._assertCanInteract('new context');
        await this.autosync.flushNow();
        this.contextId = createProtocolId('context');
        this.accumulator = createA2ATaskAccumulator();
        await this.bootstrap();
    }

    hydrateContext(snapshot) {
        const contextId = snapshot?.context_id || snapshot?.contextId;
        if (!snapshot?.document || typeof contextId !== 'string' || !contextId) {
            throw new Error('flow-ui: invalid context snapshot');
        }
        this.autosync.dispose();
        this.contextId = contextId;
        this.accumulator = createA2ATaskAccumulator();
        this._commit({
            type: 'context.hydrated',
            contextId,
            document: clone(snapshot.document),
        });
        this._emit('flow-ui-ready', { contextId, document: this.document, hydrated: true });
        return this.state;
    }

    async createShare({
        permission = 'view',
        expiresInSeconds = 86_400,
        redactedValuePaths = [],
    } = {}) {
        if (this.localPreview) throw new Error('flow-ui: local previews cannot be shared');
        if (this.profile?.viewer?.can_share !== true) {
            throw new Error('flow-ui: sharing is unavailable for this viewer');
        }
        if (!['view', 'interact'].includes(permission)) {
            throw new Error(`flow-ui: unsupported share permission ${permission}`);
        }
        if (!Array.isArray(redactedValuePaths)) {
            throw new Error('flow-ui: redactedValuePaths must be an array of JSON Pointers');
        }
        for (const path of redactedValuePaths) {
            if (typeof path !== 'string' || path.trim() === '') {
                throw new Error('flow-ui: redactedValuePaths entries must be non-empty strings');
            }
        }
        await this.autosync.flushNow();
        if (this.activeContext?.pendingMutations?.length) await this.sync();
        const context = this.activeContext;
        const document = context?.document;
        const flowId = String(this.profile?.flow_id || this.target.flowId || '').trim();
        if (!context || !document || !flowId || !this.contextId) {
            throw new Error('flow-ui: an authoritative context is required before sharing');
        }
        if (context.pendingMutations.length !== 0 || context.saveStatus !== 'saved') {
            throw new Error('flow-ui: all local changes must be acknowledged before sharing');
        }
        const response = await fetch(flowUIShareCollectionUrl(this.target), {
            method: 'POST',
            credentials: this.credentials,
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
                ...this._headers(),
            },
            body: JSON.stringify({
                flow_id: flowId,
                context_id: this.contextId,
                document_id: document.document_id,
                minimum_revision: document.revision,
                permission,
                expires_in_seconds: expiresInSeconds,
                redacted_value_paths: redactedValuePaths,
            }),
            signal: this.abortController?.signal,
        });
        let payload = null;
        try { payload = await response.json(); } catch { payload = null; }
        if (!response.ok) {
            throw new Error(String(payload?.detail || `flow-ui share: HTTP ${response.status}`));
        }
        if (typeof payload?.share_url !== 'string' || !payload.share_url) {
            throw new Error('flow-ui share: malformed response');
        }
        this._emit('flow-ui-share-created', {
            permission,
            shareUrl: payload.share_url,
            grant: payload.grant,
        });
        return payload;
    }

    async revokeShare(grantId) {
        if (this.localPreview) throw new Error('flow-ui: local previews cannot revoke shares');
        if (this.profile?.viewer?.can_share !== true) {
            throw new Error('flow-ui: sharing is unavailable for this viewer');
        }
        const trimmed = String(grantId || '').trim();
        if (!trimmed) throw new Error('flow-ui: grant_id is required to revoke a share');
        const response = await fetch(`${flowUIShareCollectionUrl(this.target)}/${encodeURIComponent(trimmed)}`, {
            method: 'DELETE',
            credentials: this.credentials,
            headers: {
                Accept: 'application/json',
                ...this._headers(),
            },
            signal: this.abortController?.signal,
        });
        if (response.status === 404) {
            throw new Error('flow-ui share: grant not found');
        }
        if (!response.ok) {
            const contentType = response.headers.get('content-type') || '';
            let detail = `HTTP ${response.status}`;
            if (contentType.includes('application/json')) {
                const payload = await response.json();
                if (typeof payload?.detail === 'string' && payload.detail) {
                    detail = payload.detail;
                }
            }
            throw new Error(`flow-ui share revoke: ${detail}`);
        }
        this._emit('flow-ui-share-revoked', { grantId: trimmed });
        return true;
    }

    _rebaseRecoveryJournal() {
        if (this.localPreview || this.profile?.viewer?.auth_mode === 'share') return;
        const pending = readRecoveryJournal({ ...this.target, contextId: this.contextId });
        for (const mutation of pending) {
            if (mutation.kind === 'navigate' && this.document?.pages?.[mutation.pageId]) {
                const document = clone(this.document);
                document.active_page_id = mutation.pageId;
                this._commit({ type: 'document.local', contextId: this.contextId, document, mutation });
            } else if (mutation.surfaceId && mutation.path?.startsWith('/values')) {
                const document = clone(this.document);
                const surface = document.surfaces?.[mutation.surfaceId];
                if (!surface) continue;
                surface.data_model = setPointer(surface.data_model, mutation.path, mutation.value);
                this._commit({ type: 'document.local', contextId: this.contextId, document, mutation });
            }
        }
        if (pending.length) this.autosync.schedule();
    }

    dispose() {
        this.autosync.dispose();
        const abortController = this.abortController;
        this.abortController = null;
        if (abortController) {
            abortController.abort();
        }
    }
}

export { FLOW_UI_ACTIONS };
