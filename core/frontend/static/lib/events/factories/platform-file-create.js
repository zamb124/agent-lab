/**
 * Единая upload factory платформы → chunked `/{segment}/api/v1/files/uploads`.
 */

import { createAsyncOp } from './async-op.js';
import { uploadPlatformFile } from '../../utils/platform-file-upload.js';

export function createPlatformFileCreateOp(config = {}) {
    const name = typeof config.name === 'string' && config.name.length > 0
        ? config.name
        : 'platform/file_create';

    return createAsyncOp({
        name,
        transport: 'http',
        silent: true,
        request: async ({ payload }) => {
            if (!payload || typeof payload !== 'object' || !(payload.file instanceof File)) {
                throw new Error(`${name}: payload.file (File) required`);
            }
            if (typeof payload.spec !== 'string' || payload.spec.length === 0) {
                throw new Error(`${name}: payload.spec (JSON FileCreateSpec) required`);
            }
            return uploadPlatformFile({
                file: payload.file,
                spec: payload.spec,
                onProgress: typeof payload.onProgress === 'function' ? payload.onProgress : undefined,
            });
        },
    });
}

export const platformFileCreateOp = createPlatformFileCreateOp();
