/**
 * Единая upload factory платформы → chunked `/{segment}/api/v1/files/uploads`.
 */

import { isPlainRecord } from '../payload.js';
import { createAsyncOp } from './async-op.js';
import { uploadPlatformFile } from '../../utils/platform-file-upload.js';

type UploadProgress = (progress: { loaded: number; total: number }) => void;

function isUploadProgress(value: unknown): value is UploadProgress {
    return typeof value === 'function';
}

function uploadProgress(value: unknown, opName: string): UploadProgress | undefined {
    if (value === undefined) return undefined;
    if (!isUploadProgress(value)) {
        throw new Error(`${opName}: payload.onProgress must be a function`);
    }
    return value;
}

export function createPlatformFileCreateOp(config: { name?: string } = {}) {
    const name = typeof config.name === 'string' && config.name.length > 0
        ? config.name
        : 'platform/file_create';

    return createAsyncOp({
        name,
        transport: 'http',
        silent: true,
        request: async ({ payload }: { payload: unknown }) => {
            if (!isPlainRecord(payload) || !(payload.file instanceof File)) {
                throw new Error(`${name}: payload.file (File) required`);
            }
            const spec = payload.spec;
            if (typeof spec !== 'string' || spec.length === 0) {
                throw new Error(`${name}: payload.spec (JSON FileCreateSpec) required`);
            }
            return uploadPlatformFile({
                file: payload.file,
                spec,
                onProgress: uploadProgress(payload.onProgress, name),
            });
        },
    });
}

export const platformFileCreateOp = createPlatformFileCreateOp();

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'platform/file_create': typeof platformFileCreateOp;
    }
}
