/**
 * Эффект files — загрузка/получение через Files API текущего сервиса.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { CoreEvents } from '../contract.js';
import { FILES_EVENTS } from '../reducers/files.js';
import { uploadPlatformFile } from '../../utils/platform-file-upload.js';
import { resolvePlatformFilesApiBase } from '../../utils/platform-files-url.js';

function _filesApiPrefix() {
    return resolvePlatformFilesApiBase();
}

function _fileIdFromPayload(payload: unknown): string {
    const p = payload as { file?: unknown; file_id?: unknown; id?: unknown } | null;
    const file = p && p.file && typeof p.file === 'object' ? p.file as Record<string, unknown> : p;
    if (!file || typeof file !== 'object') return '';
    const id = file.file_id || file.id;
    return typeof id === 'string' && id.length > 0 ? id : '';
}

function _fileObjectFromPayload(payload: unknown, fileId: string): Record<string, unknown> {
    const p = payload as { file?: unknown } | null;
    const file = p && p.file && typeof p.file === 'object' ? p.file : p;
    if (file && typeof file === 'object') {
        return { ...(file as Record<string, unknown>), file_id: fileId };
    }
    return { file_id: fileId };
}

function _errorMessage(err: unknown): string {
    return String(err && (err as Error).message ? (err as Error).message : err);
}

export function createFilesEffect(): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    return async function filesEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case FILES_EVENTS.UPLOAD_REQUESTED: {
                const p = (event.payload ?? {}) as { file?: unknown; spec?: unknown };
                const file = p.file;
                if (!(file instanceof File)) throw new Error('files.effect: payload.file required');
                const specJson = p.spec;
                if (typeof specJson !== 'string' || specJson.length === 0) {
                    throw new Error('files.effect: payload.spec (JSON FileCreateSpec) required');
                }
                try {
                    const result = await uploadPlatformFile({ file, spec: specJson });
                    ctx.dispatch(FILES_EVENTS.UPLOAD_COMPLETED, { file: result }, { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(FILES_EVENTS.UPLOAD_FAILED, { message: _errorMessage(err) }, { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' });
                }
                return;
            }
            case FILES_EVENTS.LOAD_REQUESTED: {
                const fileId = ((event.payload ?? {}) as { file_id?: unknown }).file_id;
                if (typeof fileId !== 'string' || !fileId) throw new Error('files.effect: file_id required');
                try {
                    const file = await httpRequest({ method: 'GET', url: `${_filesApiPrefix()}/${encodeURIComponent(fileId)}` });
                    ctx.dispatch(FILES_EVENTS.LOADED, { file }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(FILES_EVENTS.LOAD_FAILED, { file_id: fileId, message: _errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case FILES_EVENTS.OPEN_REQUESTED: {
                const fileId = _fileIdFromPayload(event.payload);
                if (!fileId) throw new Error('files.effect: file_id required for open');
                const file = _fileObjectFromPayload(event.payload, fileId);
                try {
                    const config = await httpRequest({
                        method: 'GET',
                        url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/editor-config`,
                    });
                    ctx.dispatch(
                        CoreEvents.UI_MODAL_OPEN,
                        { kind: 'platform.file_viewer', props: { fileId, file, config } },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    const message = _errorMessage(err);
                    ctx.dispatch(
                        FILES_EVENTS.OPEN_FAILED,
                        { file_id: fileId, message },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(
                        CoreEvents.UI_TOAST_SHOW,
                        {
                            type: 'error',
                            i18n_key: 'platform:file_viewer.open_failed',
                            i18n_vars: { message },
                            duration: 4500,
                        },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case FILES_EVENTS.EDITOR_SYNC_REQUESTED: {
                const p = (event.payload ?? {}) as { file_id?: unknown; close?: unknown; settle_ms?: unknown; dirty?: unknown };
                const fileId = p.file_id;
                if (typeof fileId !== 'string' || !fileId) throw new Error('files.effect: file_id required for editor sync');
                try {
                    const result = await httpRequest({
                        method: 'POST',
                        url: `/documents/api/v1/files/${encodeURIComponent(fileId)}/sync`,
                        body: {
                            close: p.close === true,
                            settle_ms: typeof p.settle_ms === 'number' && Number.isFinite(p.settle_ms) ? p.settle_ms : 750,
                            dirty: p.dirty === true ? true : (p.dirty === false ? false : null),
                        },
                    });
                    ctx.dispatch(
                        FILES_EVENTS.EDITOR_SYNC_COMPLETED,
                        { file_id: fileId, result },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        FILES_EVENTS.EDITOR_SYNC_FAILED,
                        { file_id: fileId, message: _errorMessage(err) },
                        { correlation_id: event.meta.correlation_id || event.id, causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            default:
                return;
        }
    };
}
