/**
 * Сохранение flow из редактора: одно место для кнопки «Опубликовать» в шапке
 * на всех ракурсах. Тело запроса — ``buildFlowPublishBody`` из состояния ``flows/editor``.
 * UI-черновик коммитится в flowConfig до вызова (``commitDraft`` / slice).
 */

import { buildFlowPublishBody } from './flows-resolvers.js';

/**
 * @param {{ state: object, setSaving: (payload: { saving: boolean }) => void, setDirty: (payload: { dirty: boolean }) => void }} editor
 *   контроллер slice ``flows/editor``
 * @param {{ run: (payload: { flow_id: string, body: object }) => Promise<unknown> }} updateOp контроллер ``flows/flow_update``
 * @param {string} flowId
 * @returns {Promise<boolean>} сохранение выполнено (``false`` — нечего сохранять или запрос отклонён)
 */
export async function saveEditorFlow(editor, updateOp, flowId) {
    const state = editor.state;
    if (!state || !state.flowConfig || !flowId) return false;
    const body = buildFlowPublishBody(state);
    if (!body) return false;
    editor.setSaving({ saving: true });
    const result = await updateOp.run({ flow_id: flowId, body });
    editor.setSaving({ saving: false });
    if (result === null) return false;
    editor.setDirty({ dirty: false });
    return true;
}
