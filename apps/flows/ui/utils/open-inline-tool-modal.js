import '../modals/inline-tool-modal.js';

/**
 * Старые конфиги могли хранить type tool|function вместо code.
 * @param {string | undefined} type
 * @returns {string}
 */
export function normalizeInlineEditorToolType(type) {
    if (!type || type === 'tool' || type === 'function') {
        return 'code';
    }
    return type;
}

/**
 * @typedef {Object} FlowLlmToolSavedDetail
 * @property {string} toolId
 * @property {Record<string, unknown>} config
 */

/**
 * @typedef {Object} FlowLlmToolModalClosedResult
 * @property {boolean} saved
 * @property {FlowLlmToolSavedDetail | null} [detail]
 */

/**
 * @typedef {Object} OpenFlowLlmToolModalOptions
 * @property {'create' | 'edit'} mode
 * @property {string} toolType
 * @property {Record<string, unknown>} [toolConfig]
 * @property {Record<string, unknown>} [flowVariables]
 * @property {string} [flowId]
 * @property {string} [skillId]
 * @property {unknown} [previewExecutionState]
 * @property {(detail: FlowLlmToolSavedDetail) => void} [onToolSaved]
 * @property {(result: FlowLlmToolModalClosedResult) => void | Promise<void>} [onModalClosed]
 *     Вызывается после закрытия модалки (сохранение или отмена); можно вернуть Promise — DOM-узел удалится после await.
 */

/**
 * @param {OpenFlowLlmToolModalOptions} options
 */
export function openInlineToolModal(options) {
    const {
        mode,
        toolType,
        toolConfig,
        flowVariables,
        flowId,
        skillId,
        previewExecutionState,
        onToolSaved,
        onModalClosed,
    } = options;

    const modal = document.createElement('inline-tool-modal');
    modal.mode = mode;
    modal.toolType = normalizeInlineEditorToolType(toolType);
    if (toolConfig !== undefined) {
        modal.toolConfig = toolConfig;
    }
    modal.flowVariables = flowVariables ?? {};
    modal.flowId = flowId ?? '';
    modal.skillId = skillId ?? '';
    modal.previewExecutionState = previewExecutionState ?? null;

    /** @type {FlowLlmToolModalClosedResult} */
    let closedResult = { saved: false, detail: null };

    const handleSaved = (e) => {
        closedResult = { saved: true, detail: e.detail };
        onToolSaved?.(e.detail);
    };
    modal.addEventListener('tool-saved', handleSaved);
    document.body.appendChild(modal);
    modal.showModal();
    modal.addEventListener(
        'close',
        () => {
            modal.removeEventListener('tool-saved', handleSaved);
            void (async () => {
                try {
                    if (onModalClosed) {
                        await onModalClosed(closedResult);
                    }
                } finally {
                    modal.remove();
                }
            })();
        },
        { once: true },
    );
}
