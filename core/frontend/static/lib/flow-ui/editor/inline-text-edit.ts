/**
 * Inline-редактирование текста блока на холсте: двойной клик открывает поле поверх блока,
 * ``Enter``/blur — фиксация как ``set_property``, ``Escape`` — отмена.
 */

const INLINE_TEXT_PROPERTY = Object.freeze({
    heading: 'text',
    text: 'markdown',
    button: 'label',
    link: 'label',
    metric: 'value',
    badge: 'label',
    status: 'label',
    alert: 'message',
    empty_state: 'message',
    section: 'title',
    slot: 'title',
    code: 'code',
    reflection: 'text',
    progress: 'label',
    text_input: 'label',
    number_input: 'label',
    select: 'label',
    checkbox: 'label',
    switch: 'label',
    slider: 'label',
    date_input: 'label',
    datetime_input: 'label',
    file_upload: 'label',
    voice_input: 'label',
    activity: 'title',
    action_preview: 'title',
    action_result: 'title',
    skill_activity: 'title',
    agent_identity: 'title',
    avatar: 'name',
});

const MULTILINE_TYPES = new Set(['text', 'code', 'alert', 'empty_state', 'reflection']);

/** Свойство блока, редактируемое inline, или ``null``, если у типа нет основного текста. */
export function inlineTextProperty(blockType: string): string | null {
    return Object.hasOwn(INLINE_TEXT_PROPERTY, blockType) ? INLINE_TEXT_PROPERTY[blockType as keyof typeof INLINE_TEXT_PROPERTY] : null;
}

export function inlineTextIsMultiline(blockType: string): boolean {
    return MULTILINE_TYPES.has(blockType);
}

/** ``'commit'`` | ``'cancel'`` | ``null`` для keydown внутри inline-поля. */
export function inlineEditKeyAction(event: KeyboardEvent, multiline: boolean): 'commit' | 'cancel' | null {
    if (event.key === 'Escape') return 'cancel';
    if (event.key === 'Enter' && (!multiline || event.metaKey || event.ctrlKey)) return 'commit';
    return null;
}
