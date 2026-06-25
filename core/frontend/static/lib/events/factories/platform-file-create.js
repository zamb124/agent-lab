/**
 * Единая upload factory для всей платформы → POST /frontend/api/v1/files/
 */

import { createAsyncOp } from './async-op.js';

const FILES_CREATE_URL = '/frontend/api/v1/files/';

export function createPlatformFileCreateOp(config = {}) {
    const name = typeof config.name === 'string' && config.name.length > 0
        ? config.name
        : 'platform/file_create';

    return createAsyncOp({
        name,
        transport: 'http',
        silent: true,
        restMirror: { method: 'POST', path: FILES_CREATE_URL },
        request: async ({ payload }) => {
            const { httpRequest } = await import('../http.js');
            if (!payload || typeof payload !== 'object' || !(payload.file instanceof File)) {
                throw new Error(`${name}: payload.file (File) required`);
            }
            if (typeof payload.spec !== 'string' || payload.spec.length === 0) {
                throw new Error(`${name}: payload.spec (JSON FileCreateSpec) required`);
            }
            const formData = new FormData();
            formData.append('file', payload.file, payload.file.name);
            formData.append('spec', payload.spec);
            return httpRequest({
                method: 'POST',
                url: FILES_CREATE_URL,
                body: formData,
            });
        },
    });
}

export const platformFileCreateOp = createPlatformFileCreateOp();
