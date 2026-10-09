/**
 * Speakable-контракт (JS-зеркало apps/flows/src/streaming/speakable.py).
 *
 * Flows помечает A2A-артефакты как «озвучиваемые» именем артефакта +
 * опциональным флагом `metadata.speak`. На клиенте тот же whitelist использует
 * `a2a-result-tts.js` (через `stream-tts-registry.js`), чтобы решить, какие куски текста
 * из кадра A2A отправить в `apps/voice` WS-командой
 * `speak`. Именно **этот файл** — единственный источник правды на стороне клиента для
 * имён артефактов и negative-override; для потока без поля `name` при наличии
 * text part действует то же правило, что и у `speakable.py` (как `response`).
 *
 * Парность (`speakable.py` ↔ `speakable.js`) проверяется CI
 * (`scripts/check_speakable_parity.py`).
 */

export const SPEAKABLE_ARTIFACT_NAMES: ReadonlySet<string> = Object.freeze(new Set([
    'response',
    'operator_reply',
]));

export interface A2aArtifactLike extends Record<string, unknown> {
    name?: unknown;
    parts?: unknown;
    metadata?: unknown;
}

export interface A2aArtifactUpdateEventLike extends Record<string, unknown> {
    artifact?: unknown;
}

export const SPEAK_FLAG_KEY = 'speak';

/**
 * @param {object} artifact
 * @returns {boolean}
 */
function artifactHasAnyTextPart(artifact: A2aArtifactLike): boolean {
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        const rec = part as Record<string, unknown>;
        const root = rec.root !== undefined ? rec.root : rec;
        if (root === null || typeof root !== 'object') {
            continue;
        }
        const text = (root as Record<string, unknown>).text;
        if (typeof text === 'string' && text !== '') {
            return true;
        }
    }
    return false;
}

/**
 * @param {object} artifact A2A `artifact` object (из `TaskArtifactUpdateEvent`).
 * @returns {boolean}
 */
export function isSpeakableArtifact(artifact: unknown): artifact is A2aArtifactLike {
    if (artifact === null || typeof artifact !== 'object') {
        return false;
    }
    const art = artifact as A2aArtifactLike;
    let name = typeof art.name === 'string' ? art.name : '';
    if (name === '') {
        if (!artifactHasAnyTextPart(art)) {
            return false;
        }
        name = 'response';
    }
    if (!SPEAKABLE_ARTIFACT_NAMES.has(name)) {
        return false;
    }
    const metadata = art.metadata;
    if (metadata !== null && typeof metadata === 'object') {
        if ((metadata as Record<string, unknown>)[SPEAK_FLAG_KEY] === false) {
            return false;
        }
    }
    return true;
}

/**
 * Выдать только текстовые части speakable-артефакта.
 *
 * Non-text parts (`data` / `raw` / `url`) пропускаются — озвучивание таких
 * частей теряет смысл.
 *
 * @param {object} artifact
 * @returns {string[]}
 */
export function iterSpeakableTextParts(artifact: A2aArtifactLike): string[] {
    if (!isSpeakableArtifact(artifact)) {
        return [];
    }
    const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
    const out: string[] = [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        const rec = part as Record<string, unknown>;
        const root = rec.root !== undefined ? rec.root : rec;
        if (root === null || typeof root !== 'object') {
            continue;
        }
        const text = (root as Record<string, unknown>).text;
        if (typeof text !== 'string') {
            continue;
        }
        if (text !== '') {
            out.push(text);
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
export function extractSpeakableText(event: unknown): string | null {
    if (event === null || typeof event !== 'object') {
        return null;
    }
    const artifact = (event as A2aArtifactUpdateEventLike).artifact;
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
