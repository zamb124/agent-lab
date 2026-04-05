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
 * @typedef {Object} InlineToolSavedDetail
 * @property {string} toolId
 * @property {Record<string, unknown>} config
 */

/**
 * @typedef {Object} OpenInlineToolModalOptions
 * @property {'create' | 'edit'} mode
 * @property {string} toolType
 * @property {Record<string, unknown>} [toolConfig]
 * @property {Record<string, unknown>} [flowVariables]
 * @property {string} [flowId]
 * @property {string} [skillId]
 * @property {unknown} [previewExecutionState]
 * @property {(detail: InlineToolSavedDetail) => void} [onToolSaved]
 */

/**
 * @param {OpenInlineToolModalOptions} options
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

    const handleSaved = (e) => {
        onToolSaved?.(e.detail);
    };
    modal.addEventListener('tool-saved', handleSaved);
    document.body.appendChild(modal);
    modal.showModal();
    modal.addEventListener(
        'close',
        () => {
            modal.removeEventListener('tool-saved', handleSaved);
            modal.remove();
        },
        { once: true },
    );
}
