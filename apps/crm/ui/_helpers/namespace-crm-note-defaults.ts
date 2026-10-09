/**
 * Поля голоса заметки из `NamespaceCRMSettings` (namespace и шаблон namespace).
 */

/**
 * @param {object|null|undefined} cs
 * @returns {{ defaultNoteVoiceMode: 'self'|'none'|'last', showNoteVoiceUi: boolean }}
 */
export function parseNoteVoiceDefaultsFromCrmSettings(cs: Record<string, unknown> | null | undefined): { defaultNoteVoiceMode: 'self' | 'none' | 'last'; showNoteVoiceUi: boolean } {
    let defaultNoteVoiceMode: 'self' | 'none' | 'last' = 'self';
    let showNoteVoiceUi = true;
    if (cs !== undefined && cs !== null && typeof cs === 'object') {
        if (typeof cs.default_note_voice === 'string') {
            const m = cs.default_note_voice as 'none' | 'last' | 'self';
            if (m === 'none' || m === 'last' || m === 'self') {
                defaultNoteVoiceMode = m;
            }
        }
        showNoteVoiceUi = !(cs.show_note_voice_ui === false);
    }
    return { defaultNoteVoiceMode, showNoteVoiceUi };
}

/** @param {unknown} raw */
export function normalizeDefaultNoteVoiceMode(raw: unknown): 'none' | 'last' | 'self' {
    if (raw === 'none' || raw === 'last' || raw === 'self') {
        return raw;
    }
    return 'self';
}
