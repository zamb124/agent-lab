/**
 * Поля голоса заметки из `NamespaceCRMSettings` (namespace и шаблон namespace).
 */

/**
 * @param {object|null|undefined} cs
 * @returns {{ defaultNoteVoiceMode: 'self'|'none'|'last', showNoteVoiceUi: boolean }}
 */
export function parseNoteVoiceDefaultsFromCrmSettings(cs) {
    let defaultNoteVoiceMode = 'self';
    let showNoteVoiceUi = true;
    if (cs !== undefined && cs !== null && typeof cs === 'object') {
        if (typeof cs.default_note_voice === 'string') {
            const m = cs.default_note_voice;
            if (m === 'none' || m === 'last' || m === 'self') {
                defaultNoteVoiceMode = m;
            }
        }
        showNoteVoiceUi = !(cs.show_note_voice_ui === false);
    }
    return { defaultNoteVoiceMode, showNoteVoiceUi };
}

/** @param {unknown} raw */
export function normalizeDefaultNoteVoiceMode(raw) {
    if (raw === 'none' || raw === 'last' || raw === 'self') {
        return raw;
    }
    return 'self';
}
