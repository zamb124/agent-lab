/**
 * GET /flows/api/v1/flows/{flow_id}/voice-session-query — готовые query-параметры Voice WS.
 *
 * Ответ `query` содержит все непустые поля из мержа профиля речи flow+ветки (STT/TTS/VAD,
 * `language`, частоты и т.д.), сериализованные как для `apps/voice/api/session.py`. На
 * бэкенде дополнительно tier-резолвится и подставляется в `tts_voice` то же значение, что
 * дал бы `voice_resolver` для WS (профиль → company → deployment). Параметры STT/TTS/VAD,
 * которых нет в профиле, в `query` не попадают — на шлюзе voice они по-прежнему резолвятся
 * из company/settings при подключении сокета.
 */

/**
 * @param {string|null|undefined} branchId
 * @returns {string}
 */
export function normalizeBranchIdForFlowVoiceSessionQuery(branchId) {
    const raw = typeof branchId === 'string' && branchId.trim() !== '' ? branchId.trim() : '';
    if (raw === '' || raw === 'base') {
        return 'default';
    }
    return raw;
}

/**
 * @param {unknown} query
 * @returns {Record<string, string>}
 */
export function voiceSessionQueryToStringRecord(query) {
    if (!query || typeof query !== 'object' || Array.isArray(query)) {
        throw new Error('voiceSessionQueryToStringRecord: query object required');
    }
    /** @type {Record<string, string>} */
    const out = {};
    for (const [k, v] of Object.entries(query)) {
        if (typeof k === 'string' && k !== '' && v !== null && v !== undefined && String(v) !== '') {
            out[k] = String(v);
        }
    }
    return out;
}

/**
 * @param {object} p
 * @param {string} p.flowsApiRoot — префикс API flows без завершающего `/` (например `/flows`)
 * @param {string} p.flowId
 * @param {string|null|undefined} [p.branchId]
 * @param {RequestCredentials} [p.credentials]
 * @param {() => Promise<Record<string, string>>} [p.getHeaders]
 * @returns {Promise<Record<string, string>>}
 */
export async function fetchFlowVoiceSessionQueryDict(p) {
    const fid = String(p.flowId || '').trim();
    const root = String(p.flowsApiRoot || '').replace(/\/$/, '');
    if (fid === '' || root === '') {
        throw new Error('fetchFlowVoiceSessionQueryDict: flowId and flowsApiRoot required');
    }
    const bid = normalizeBranchIdForFlowVoiceSessionQuery(p.branchId);
    const url = `${root}/api/v1/flows/${encodeURIComponent(fid)}/voice-session-query?branch_id=${encodeURIComponent(bid)}`;
    const credentials = p.credentials === 'omit' ? 'omit' : 'include';
    const headersRaw =
        typeof p.getHeaders === 'function' ? await p.getHeaders() : {};
    const headers =
        headersRaw && typeof headersRaw === 'object' && !Array.isArray(headersRaw)
            ? headersRaw
            : {};
    const res = await fetch(url, {
        method: 'GET',
        credentials,
        headers,
    });
    if (!res.ok) {
        const t = await res.text();
        throw new Error(`voice-session-query HTTP ${res.status}: ${t}`);
    }
    const body = await res.json();
    if (!body || typeof body !== 'object' || !body.query || typeof body.query !== 'object') {
        throw new Error('voice-session-query: invalid response body');
    }
    return voiceSessionQueryToStringRecord(body.query);
}
