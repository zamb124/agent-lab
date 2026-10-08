/**
 * Единая upload factory платформы → chunked `/{segment}/api/v1/files/uploads`.
 */

import { createAsyncOp } from './async-op.js';
import { uploadPlatformFile } from '../../utils/platform-file-upload.js';

export function createPlatformFileCreateOp(config: { name?: string } = {}) {
    const name = typeof config.name === 'string' && config.name.length > 0
        ? config.name
        : 'platform/file_create';

    return createAsyncOp({
        name,
        transport: 'http',
        silent: true,
        request: async ({ payload }: { payload: unknown }) => {
            const p = payload as { file?: unknown; spec?: unknown; onProgress?: unknown };
            if (!p || typeof p !== 'object' || !(p.file instanceof File)) {
                throw new Error(`${name}: payload.file (File) required`);
            }
            if (typeof p.spec !== 'string' || p.spec.length === 0) {
                throw new Error(`${name}: payload.spec (JSON FileCreateSpec) required`);
            }
            return uploadPlatformFile({
                file: p.file,
                spec: p.spec,
                onProgress: typeof p.onProgress === 'function' ? p.onProgress as (p: { loaded: number; total: number }) => void : undefined,
            });
        },
    });
}

export const platformFileCreateOp = createPlatformFileCreateOp();
