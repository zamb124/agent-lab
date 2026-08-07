import { cloneSerializable } from '../utils/clone.js';

function clone(value) {
    return cloneSerializable(value);
}

export function projectA2APart(part, index = 0) {
    if (!part || typeof part !== 'object') return { kind: 'unknown', index, value: clone(part) };
    if (typeof part.text === 'string') return { kind: 'text', index, text: part.text, mediaType: part.mediaType || 'text/plain', metadata: clone(part.metadata || {}) };
    const file = part.file || null;
    if (file || typeof part.url === 'string') {
        return {
            kind: 'file', index,
            url: part.url || file?.uri || file?.url || null,
            bytes: file?.bytes || null,
            filename: part.filename || file?.name || null,
            mediaType: part.mediaType || file?.mimeType || null,
            metadata: clone(part.metadata || {}),
        };
    }
    if (Object.prototype.hasOwnProperty.call(part, 'data')) return { kind: 'data', index, data: clone(part.data), mediaType: part.mediaType || 'application/json', metadata: clone(part.metadata || {}) };
    if (Object.prototype.hasOwnProperty.call(part, 'raw')) return { kind: 'raw', index, raw: part.raw, mediaType: part.mediaType || 'application/octet-stream', metadata: clone(part.metadata || {}) };
    return { kind: 'unknown', index, value: clone(part) };
}

export function projectA2AArtifact(artifact) {
    return {
        artifactId: artifact?.artifactId || artifact?.artifact_id || '',
        name: artifact?.name || '',
        description: artifact?.description || '',
        extensions: clone(artifact?.extensions || []),
        metadata: clone(artifact?.metadata || {}),
        parts: (artifact?.parts || []).map(projectA2APart),
    };
}
