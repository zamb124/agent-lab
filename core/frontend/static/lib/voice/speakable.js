/**
 * Speakable-контракт (JS-зеркало apps/flows/src/streaming/speakable.py).
 *
 * Flows помечает A2A-артефакты как «озвучиваемые» именем артефакта +
 * опциональным флагом `metadata.speak`. На клиенте тот же whitelist использует
 * `a2a-result-tts.js` (через `stream-tts-registry.js`), чтобы решить, какие куски текста
 * из кадра A2A отправить в `apps/voice` WS-командой
 * `speak`. Именно **этот файл** — единственный источник правды на стороне клиента для
 * имён артефактов и negative-override; для потока без поля `name` при наличии
 * `TextPart` действует то же правило, что и у `speakable.py` (как `response`).
 *
 * Парность (`speakable.py` ↔ `speakable.js`) проверяется CI
 * (`scripts/check_speakable_parity.py`).
 */

export const SPEAKABLE_ARTIFACT_NAMES = Object.freeze(new Set([
    'response',
    'operator_reply',
]));

export const SPEAK_FLAG_KEY = 'speak';

/**
 * @param {object} artifact
 * @returns {boolean}
 */
function artifactHasAnyTextPart(artifact) {
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        const root = part.root !== undefined ? part.root : part;
        if (root === null || typeof root !== 'object') {
            continue;
        }
        const kind = typeof root.kind === 'string' ? root.kind : '';
        if (kind !== 'text') {
            continue;
        }
        if (typeof root.text === 'string' && root.text !== '') {
            return true;
        }
    }
    return false;
}

/**
 * @param {object} artifact A2A `artifact` object (из `TaskArtifactUpdateEvent`).
 * @returns {boolean}
 */
export function isSpeakableArtifact(artifact) {
    if (artifact === null || typeof artifact !== 'object') {
        return false;
    }
    let name = typeof artifact.name === 'string' ? artifact.name : '';
    if (name === '') {
        if (!artifactHasAnyTextPart(artifact)) {
            return false;
        }
        name = 'response';
    }
    if (!SPEAKABLE_ARTIFACT_NAMES.has(name)) {
        return false;
    }
    const metadata = artifact.metadata;
    if (metadata !== null && typeof metadata === 'object') {
        if (metadata[SPEAK_FLAG_KEY] === false) {
            return false;
        }
    }
    return true;
}

/**
 * Выдать только текстовые части speakable-артефакта.
 *
 * `DataPart` / `FilePart` пропускаются — озвучивание таких частей
 * теряет смысл.
 *
 * @param {object} artifact
 * @returns {string[]}
 */
export function iterSpeakableTextParts(artifact) {
    if (!isSpeakableArtifact(artifact)) {
        return [];
    }
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    const out = [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        const root = part.root !== undefined ? part.root : part;
        if (root === null || typeof root !== 'object') {
            continue;
        }
        const kind = typeof root.kind === 'string' ? root.kind : '';
        if (kind !== 'text') {
            continue;
        }
        if (typeof root.text !== 'string') {
            continue;
        }
        if (root.text !== '') {
            out.push(root.text);
        }
    }
    return out;
}

/**
 * Склеить весь speakable-текст из `TaskArtifactUpdateEvent`.
 *
 * @param {object} event A2A TaskArtifactUpdateEvent (как из SSE).
 * @returns {string|null} склеенный текст или `null` если не speakable / нет текста.
 */
export function extractSpeakableText(event) {
    if (event === null || typeof event !== 'object') {
        return null;
    }
    const artifact = event.artifact;
    if (!artifact) {
        return null;
    }
    if (!isSpeakableArtifact(artifact)) {
        return null;
    }
    const parts = iterSpeakableTextParts(artifact);
    if (parts.length === 0) {
        return null;
    }
    const joined = parts.join('');
    return joined === '' ? null : joined;
}
