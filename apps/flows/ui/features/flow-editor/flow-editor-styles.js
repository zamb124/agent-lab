/**
 * Flow Editor Page Styles
 * Light DOM стили для компонента редактора flow
 */

let stylesInjected = false;

const editorStyles = `
flow-editor-page {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
}

flow-editor-page .editor-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
}

flow-editor-page .editor-body {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

flow-editor-page .node-types-sidebar {
    width: 220px;
    flex-shrink: 0;
    border-right: 1px solid var(--border-subtle);
    background: var(--glass-solid-subtle);
    overflow-y: auto;
}

flow-editor-page .canvas-area {
    flex: 1;
    position: relative;
    min-width: 0;
    min-height: 0;
    background: var(--bg-secondary);
    overflow: hidden;
}

flow-editor-page .panel-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0);
    z-index: 99;
    pointer-events: none;
    transition: background 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

flow-editor-page .panel-backdrop.visible {
    background: rgba(0, 0, 0, 0.6);
    pointer-events: auto;
    backdrop-filter: blur(4px);
}

flow-editor-page .floating-panel {
    position: absolute;
    top: var(--space-4, 16px);
    right: var(--space-4, 16px);
    width: 340px;
    max-height: calc(100% - var(--space-8, 32px));
    background: var(--glass-solid-strong, rgba(40, 40, 64, 0.95));
    border: 1px solid var(--border-default, rgba(255,255,255,0.1));
    border-radius: var(--radius-xl, 16px);
    box-shadow: var(--glass-shadow-strong, 0 16px 48px rgba(0,0,0,0.4));
    overflow: hidden;
    z-index: 20;
    display: flex;
    flex-direction: column;
    transition: 
        top 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        right 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        left 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        width 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        height 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        transform 0.4s cubic-bezier(0.4, 0, 0.2, 1),
        box-shadow 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

flow-editor-page .floating-panel.entering {
    animation: slideInPanel 0.3s ease-out;
}

@keyframes slideInPanel {
    from {
        opacity: 0;
        transform: translateX(40px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateX(0) scale(1);
    }
}

flow-editor-page .floating-panel.expanded {
    position: fixed;
    top: 3vh !important;
    left: 50% !important;
    right: auto !important;
    transform: translateX(-50%);
    width: min(1200px, 94vw);
    height: 94vh;
    max-height: 94vh;
    z-index: 100;
    box-shadow: 0 32px 100px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255,255,255,0.1);
}

flow-editor-page .floating-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
    flex-shrink: 0;
}

flow-editor-page .floating-panel.expanded .floating-panel-header {
    padding: 16px 24px;
}

flow-editor-page .floating-panel-title {
    display: flex;
    align-items: center;
    gap: 8px;
}

flow-editor-page .floating-panel-icon {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
}

flow-editor-page .floating-panel.expanded .floating-panel-icon {
    width: 36px;
    height: 36px;
    border-radius: 10px;
}

flow-editor-page .floating-panel-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary, rgba(255,255,255,0.95));
}

flow-editor-page .floating-panel.expanded .floating-panel-name {
    font-size: 18px;
}

flow-editor-page .floating-panel-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

flow-editor-page .floating-panel-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: var(--text-tertiary, rgba(255,255,255,0.4));
    cursor: pointer;
    transition: all 0.2s ease;
}

flow-editor-page .floating-panel-btn:hover {
    background: rgba(255,255,255,0.08);
    color: var(--text-primary, rgba(255,255,255,0.95));
}

flow-editor-page .floating-panel-btn.expand-btn:hover {
    color: var(--accent, #6366f1);
}

flow-editor-page .floating-panel-body {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--space-4, 16px);
}

@media (max-width: 480px) {
    flow-editor-page .floating-panel-body {
        padding: var(--space-2, 8px);
    }
}
`;

export function injectEditorStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    
    const style = document.createElement('style');
    style.id = 'flow-editor-page-styles';
    style.textContent = editorStyles;
    document.head.appendChild(style);
}

