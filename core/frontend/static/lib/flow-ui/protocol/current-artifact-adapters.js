/**
 * Named A2A artifact → typed projection for ArtifactFeed / TaskFeed.
 * Does not open a second SSE store — adapters only reshape existing task artifacts.
 */

const TOOL_CALL_PREFIX = 'tool_call:';
const TOOL_RESULT_PREFIX = 'tool_result:';
const SKILL_ACTIVITY = 'skill_activity';
const RUN_TRACE = 'run_trace';
const FILES = 'files';
const UI_DOCUMENT = 'ui.document';

/**
 * @param {unknown} artifact
 * @returns {{ kind: string, artifact_id: string, name: string, payload: unknown } | null}
 */
export function adaptCurrentArtifact(artifact) {
    if (!artifact || typeof artifact !== 'object') {
        throw new Error('flow-ui: adaptCurrentArtifact requires artifact object');
    }
    const name = typeof artifact.name === 'string' ? artifact.name : '';
    const artifactId = typeof artifact.artifactId === 'string'
        ? artifact.artifactId
        : (typeof artifact.artifact_id === 'string' ? artifact.artifact_id : '');
    if (!artifactId) {
        throw new Error('flow-ui: artifact.artifactId is required');
    }
    if (name === UI_DOCUMENT || name.startsWith('a2ui.')) {
        return null;
    }
    if (name.startsWith(TOOL_CALL_PREFIX) || artifactId.startsWith(TOOL_CALL_PREFIX)) {
        return {
            kind: 'tool_call',
            artifact_id: artifactId,
            name,
            payload: _firstDataPayload(artifact),
        };
    }
    if (name.startsWith(TOOL_RESULT_PREFIX) || artifactId.startsWith(TOOL_RESULT_PREFIX)) {
        return {
            kind: 'tool_result',
            artifact_id: artifactId,
            name,
            payload: _firstDataPayload(artifact),
        };
    }
    if (name === SKILL_ACTIVITY || artifactId.startsWith(`${SKILL_ACTIVITY}:`)) {
        return {
            kind: 'skill_activity',
            artifact_id: artifactId,
            name,
            payload: _firstDataPayload(artifact),
        };
    }
    if (name === RUN_TRACE || artifactId.startsWith(`${RUN_TRACE}:`)) {
        return {
            kind: 'run_trace',
            artifact_id: artifactId,
            name,
            payload: _firstDataPayload(artifact),
        };
    }
    if (name === FILES || artifactId.startsWith(`${FILES}:`)) {
        return {
            kind: 'files',
            artifact_id: artifactId,
            name,
            payload: _fileParts(artifact),
        };
    }
    return {
        kind: 'generic',
        artifact_id: artifactId,
        name: name || artifactId,
        payload: artifact,
    };
}

/**
 * @param {unknown[]} artifacts
 */
export function adaptCurrentArtifacts(artifacts) {
    if (!Array.isArray(artifacts)) {
        throw new Error('flow-ui: adaptCurrentArtifacts requires an array');
    }
    return artifacts
        .map((artifact) => adaptCurrentArtifact(artifact))
        .filter((item) => item !== null);
}

function _firstDataPayload(artifact) {
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    for (const part of parts) {
        if (part && typeof part === 'object' && part.data != null) {
            return part.data;
        }
        if (part && typeof part === 'object' && typeof part.text === 'string') {
            return { text: part.text };
        }
    }
    return null;
}

function _fileParts(artifact) {
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    return parts
        .filter((part) => part && typeof part === 'object' && (part.kind === 'file' || part.file || part.url))
        .map((part) => ({
            filename: part.filename || part.file?.name || part.original_name,
            url: part.url || part.file?.uri,
            mediaType: part.mediaType || part.content_type,
            file_id: part.file_id,
        }));
}
