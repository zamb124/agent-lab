/**
 * Drawflow Styles Injector
 * Инжектирует глобальные стили Drawflow в document.head один раз
 */

let injected = false;

const drawflowStyles = `
/* Agent Canvas Drawflow Styles - Global (Light DOM) */

flow-canvas {
    display: block;
    position: relative;
    flex: 1;
    min-height: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
}

flow-canvas .canvas-container {
    width: 100%;
    height: 100%;
    position: relative;
    display: flex;
    flex-direction: column;
}

flow-canvas #drawflow-area {
    flex: 1;
    width: 100%;
    min-height: 0;
    position: relative;
}

/* DRAWFLOW BASE STYLES (required for lib to work) */
.parent-drawflow {
    width: 100% !important;
    height: 100% !important;
    position: relative !important;
    overflow: hidden !important;
    outline: none !important;
    background-color: var(--bg-secondary, #151520) !important;
    background-image: radial-gradient(circle, rgba(255,255,255,0.05) 1px, transparent 1px) !important;
    background-size: 24px 24px !important;
}

.drawflow {
    width: 100% !important;
    height: 100% !important;
    position: relative !important;
    background: transparent !important;
    user-select: none !important;
}

.drawflow .drawflow-node {
    display: flex !important;
    align-items: center !important;
    position: absolute !important;
    background: linear-gradient(135deg, rgba(40, 40, 60, 0.95) 0%, rgba(28, 28, 46, 0.98) 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px !important;
    min-width: 180px !important;
    color: #fff !important;
    z-index: 3 !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    padding: 0 !important;
    cursor: move !important;
    transition: border 0.3s ease, box-shadow 0.3s ease, transform 0.2s ease !important;
}

.drawflow .drawflow-node:hover {
    border-color: rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5) !important;
}

.drawflow .drawflow-node.selected {
    border-color: #10b981 !important;
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.3), 0 8px 32px rgba(0, 0, 0, 0.4) !important;
}

.drawflow .drawflow_content_node {
    width: 100% !important;
    display: block !important;
    position: relative !important;
}

/* Inputs/Outputs connectors */
.drawflow .drawflow-node .inputs,
.drawflow .drawflow-node .outputs {
    position: absolute !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    display: flex !important;
    flex-direction: column !important;
    gap: 8px !important;
}

.drawflow .drawflow-node .inputs {
    left: -8px !important;
}

.drawflow .drawflow-node .outputs {
    right: -8px !important;
}

.drawflow .drawflow-node .input,
.drawflow .drawflow-node .output {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: #1c1c2e !important;
    border: 2px solid rgba(255, 255, 255, 0.3) !important;
    cursor: crosshair !important;
    position: relative !important;
}

.drawflow .drawflow-node .input:hover,
.drawflow .drawflow-node .output:hover {
    background: rgba(16, 185, 129, 0.3) !important;
    border-color: #10b981 !important;
    transform: scale(1.2) !important;
}

/* Connection lines (SVG) */
.drawflow svg {
    z-index: 1 !important;
    position: absolute !important;
    overflow: visible !important;
}

.drawflow .connection {
    position: absolute !important;
    pointer-events: none !important;
    overflow: visible !important;
}

.drawflow .connection .main-path {
    fill: none !important;
    stroke-width: 2px !important;
    stroke: rgba(255, 255, 255, 0.25) !important;
    pointer-events: all !important;
}

.drawflow .connection .main-path:hover {
    stroke: #10b981 !important;
    stroke-width: 3px !important;
}

.drawflow .connection.selected .main-path {
    stroke: #10b981 !important;
}

.drawflow .drawflow-node .virtual-end-bundle {
    position: absolute !important;
    left: calc(100% - 14px) !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    pointer-events: none !important;
    z-index: 4 !important;
}

.drawflow .drawflow-node .virtual-end-line {
    width: 28px !important;
    height: 2px !important;
    flex-shrink: 0 !important;
    background: rgba(255, 255, 255, 0.25) !important;
    border-radius: 1px !important;
}

.drawflow .drawflow-node .virtual-end-marker {
    width: 30px !important;
    height: 30px !important;
    flex-shrink: 0 !important;
    margin-left: 2px !important;
    border-radius: 50% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    color: rgba(255, 255, 255, 0.45) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    background: rgba(255, 255, 255, 0.06) !important;
    box-sizing: border-box !important;
}

.drawflow .drawflow-delete {
    display: none !important;
}

flow-canvas .zoom-controls {
    position: absolute;
    top: 12px;
    right: 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    z-index: 10;
}

flow-canvas .zoom-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
    border: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
    border-radius: 8px;
    color: var(--text-secondary, rgba(255,255,255,0.65));
    cursor: pointer;
    transition: all 0.15s ease;
}

flow-canvas .zoom-btn:hover {
    background: var(--glass-solid-strong, rgba(40, 40, 64, 0.92));
    color: var(--text-primary, rgba(255,255,255,0.95));
}

/* Context Menu */
flow-canvas .context-menu {
    position: fixed;
    background: var(--glass-solid-strong, rgba(40, 40, 64, 0.95));
    border: 1px solid var(--border-default, rgba(255,255,255,0.1));
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
    min-width: 180px;
    padding: 4px;
    z-index: 1000;
    animation: fadeIn 0.1s ease-out;
}

@keyframes fadeIn {
    from { opacity: 0; transform: scale(0.95); }
    to { opacity: 1; transform: scale(1); }
}

flow-canvas .context-menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    font-size: 13px;
    color: var(--text-primary, rgba(255,255,255,0.95));
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
}

flow-canvas .context-menu-item:hover {
    background: rgba(255,255,255,0.08);
}

flow-canvas .context-menu-item.danger {
    color: #f43f5e;
}

flow-canvas .context-menu-item.danger:hover {
    background: rgba(244, 63, 94, 0.12);
}

flow-canvas .context-menu-item.active {
    color: #10b981;
}

flow-canvas .context-menu-separator {
    height: 1px;
    background: rgba(255,255,255,0.08);
    margin: 4px 0;
}

/* AGENT NODE CONTENT STYLES */
.drawflow .agent-node {
    padding: 14px 18px !important;
    display: flex !important;
    align-items: center !important;
    gap: 14px !important;
    position: relative !important;
}

.drawflow .agent-node-icon {
    width: 36px !important;
    height: 36px !important;
    border-radius: 10px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex-shrink: 0 !important;
}

.drawflow .agent-node-info {
    flex: 1 !important;
    min-width: 0 !important;
}

.drawflow .agent-node-name {
    font-size: 14px !important;
    font-weight: 600 !important;
    color: rgba(255, 255, 255, 0.95) !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

.drawflow .agent-node-type {
    font-size: 11px !important;
    color: rgba(255, 255, 255, 0.45) !important;
    margin-top: 3px !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

/* Entry Point badge */
.drawflow .agent-node-entry-badge {
    position: absolute !important;
    top: -8px !important;
    right: -8px !important;
    width: 20px !important;
    height: 20px !important;
    background: #10b981 !important;
    border-radius: 50% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 10px !important;
    color: white !important;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.4) !important;
}

/* Inherited from base badge */
.drawflow .agent-node-inherited-badge {
    position: absolute !important;
    top: -6px !important;
    left: -6px !important;
    width: 18px !important;
    height: 18px !important;
    background: linear-gradient(135deg, rgba(107, 114, 128, 0.95), rgba(75, 85, 99, 1)) !important;
    border: 1.5px solid rgba(156, 163, 175, 0.8) !important;
    border-radius: 4px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: rgba(229, 231, 235, 0.95) !important;
    font-size: 10px !important;
    z-index: 10 !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
}

/* Language badge for code nodes */
.drawflow .agent-node-lang-badge {
    position: absolute !important;
    bottom: -4px !important;
    right: -4px !important;
    width: 18px !important;
    height: 18px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    z-index: 10 !important;
}

.drawflow .agent-node-lang-badge platform-icon {
    width: 18px !important;
    height: 18px !important;
}

.drawflow .drawflow-node.node-inherited {
    border-color: rgba(107, 114, 128, 0.4) !important;
    opacity: 0.85 !important;
}

.drawflow .drawflow-node.is-entry-node {
    border-color: #10b981;
}

.drawflow .drawflow-node.is-entry-node .inputs {
    display: none !important;
}

.drawflow .drawflow-node.node-running {
    border: 3px solid #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3), 0 0 20px rgba(59, 130, 246, 0.8) !important;
    animation: node-pulse-running 1.5s infinite !important;
    z-index: 100 !important;
    transition: none !important;
}

.drawflow .drawflow-node.node-completed {
    border: 3px solid #10b981 !important;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.3), 0 0 20px rgba(16, 185, 129, 0.8) !important;
    z-index: 100 !important;
    transition: none !important;
}

.drawflow .drawflow-node.node-error {
    border: 3px solid #ef4444 !important;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.3), 0 0 20px rgba(239, 68, 68, 0.8) !important;
    z-index: 100 !important;
    transition: none !important;
}

@keyframes node-pulse-running {
    0%, 100% { 
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3), 0 0 20px rgba(59, 130, 246, 0.8) !important;
        transform: scale(1) !important;
    }
    50% { 
        box-shadow: 0 0 0 6px rgba(59, 130, 246, 0.1), 0 0 30px rgba(59, 130, 246, 1) !important;
        transform: scale(1.02) !important;
    }
}

/* Breakpoint Styles */
.drawflow .node-breakpoint-indicator {
    position: absolute !important;
    bottom: -6px !important;
    left: -6px !important;
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: #ef4444 !important;
    border: 2px solid #fff !important;
    z-index: 10 !important;
    pointer-events: none !important;
}

.drawflow-node.breakpoint-active {
    outline: 3px solid #ef4444 !important;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { 
        outline-color: #ef4444; 
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4);
    }
    50% { 
        outline-color: #f87171;
        box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
    }
}

/* Light theme node status styles */
[data-theme="light"] .drawflow .drawflow-node.node-running {
    border: 3px solid #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3), 0 0 20px rgba(59, 130, 246, 0.5) !important;
    animation: node-pulse-running 1.5s infinite !important;
    z-index: 100 !important;
    transition: none !important;
}

[data-theme="light"] .drawflow .drawflow-node.node-completed {
    border: 3px solid #10b981 !important;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.3), 0 0 20px rgba(16, 185, 129, 0.5) !important;
    z-index: 100 !important;
    transition: none !important;
}

[data-theme="light"] .drawflow .drawflow-node.node-error {
    border: 3px solid #ef4444 !important;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.3), 0 0 20px rgba(239, 68, 68, 0.5) !important;
    z-index: 100 !important;
    transition: none !important;
}

/* Light theme support */
[data-theme="light"] .parent-drawflow {
    background-color: #f8fafc !important;
    background-image: radial-gradient(circle, rgba(0,0,0,0.06) 1px, transparent 1px) !important;
}

[data-theme="light"] .drawflow .drawflow-node {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%) !important;
    border: 1px solid rgba(15, 23, 42, 0.12) !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08) !important;
    color: #0f172a !important;
}

[data-theme="light"] .drawflow .drawflow-node:hover {
    border-color: rgba(15, 23, 42, 0.2) !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12) !important;
}

[data-theme="light"] .drawflow .drawflow-node.selected {
    border-color: #10b981 !important;
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2), 0 8px 24px rgba(0, 0, 0, 0.1) !important;
}

[data-theme="light"] .drawflow .agent-node-name {
    color: #0f172a !important;
}

[data-theme="light"] .drawflow .agent-node-type {
    color: #64748b !important;
}

[data-theme="light"] .drawflow .drawflow-node .input,
[data-theme="light"] .drawflow .drawflow-node .output {
    background: #ffffff !important;
    border-color: rgba(15, 23, 42, 0.2) !important;
}

[data-theme="light"] .drawflow .drawflow-node .input:hover,
[data-theme="light"] .drawflow .drawflow-node .output:hover {
    background: rgba(16, 185, 129, 0.15) !important;
    border-color: #10b981 !important;
}

[data-theme="light"] .drawflow .connection .main-path {
    stroke: rgba(15, 23, 42, 0.2) !important;
}

[data-theme="light"] .drawflow .connection .main-path:hover {
    stroke: #10b981 !important;
}

[data-theme="light"] .drawflow .drawflow-node .virtual-end-line {
    background: rgba(15, 23, 42, 0.2) !important;
}

[data-theme="light"] .drawflow .drawflow-node .virtual-end-marker {
    color: rgba(15, 23, 42, 0.45) !important;
    border-color: rgba(15, 23, 42, 0.18) !important;
    background: rgba(15, 23, 42, 0.04) !important;
}

/* Edge Labels */
.edge-labels-container {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 2;
}

.edge-label {
    position: absolute;
    z-index: 2;
    padding: 4px 10px;
    background: var(--glass-solid-strong, rgba(40, 40, 64, 0.95));
    border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
    border-radius: 8px;
    font-size: 11px;
    color: var(--text-primary, rgba(255, 255, 255, 0.95));
    cursor: pointer;
    pointer-events: auto;
    white-space: nowrap;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    transition: all 0.15s ease;
    font-family: var(--font-mono, 'Courier New', monospace);
}

.edge-label:hover {
    background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
    border-color: var(--accent, #10b981);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    transform: translate(-50%, -50%) scale(1.05);
}

[data-theme="light"] .edge-label {
    background: rgba(255, 255, 255, 0.95);
    border-color: rgba(15, 23, 42, 0.12);
    color: #0f172a;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

[data-theme="light"] .edge-label:hover {
    background: #ffffff;
    border-color: #10b981;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* Node Error Tooltips Container */
.node-error-tooltips-container {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 10000;
}

/* Node Error Tooltip */
.node-error-tooltip {
    position: fixed;
    z-index: 10001;
    min-width: 250px;
    max-width: 400px;
    pointer-events: auto;
    animation: errorTooltipFadeIn 0.3s ease-out;
}

.node-error-tooltip.hiding {
    animation: errorTooltipFadeOut 0.3s ease-out forwards;
}

@keyframes errorTooltipFadeIn {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes errorTooltipFadeOut {
    from {
        opacity: 1;
        transform: translateY(0);
    }
    to {
        opacity: 0;
        transform: translateY(8px);
    }
}

.node-error-tooltip::before {
    content: '';
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 8px solid transparent;
    border-right: 8px solid transparent;
    border-top: 8px solid rgba(239, 68, 68, 0.95);
}

.node-error-content {
    background: rgba(239, 68, 68, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 8px;
    padding: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(10px);
}

.node-error-message {
    color: #ffffff;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 8px;
    word-wrap: break-word;
    font-family: var(--font-mono, 'Courier New', monospace);
}

.node-error-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
}

.node-error-copy,
.node-error-close {
    background: rgba(255, 255, 255, 0.15);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 4px;
    color: #ffffff;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
}

.node-error-copy:hover,
.node-error-close:hover {
    background: rgba(255, 255, 255, 0.25);
    border-color: rgba(255, 255, 255, 0.4);
}

.node-error-close {
    font-size: 18px;
    line-height: 1;
    width: 24px;
    height: 24px;
    padding: 0;
}
`;

export function injectDrawflowStyles() {
    if (injected) return;
    
    const existingStyle = document.getElementById('drawflow-custom-styles');
    if (existingStyle) {
        existingStyle.remove();
    }
    
    injected = true;
    
    const style = document.createElement('style');
    style.id = 'drawflow-custom-styles';
    style.textContent = drawflowStyles;
    document.head.appendChild(style);
    
    console.log('[FlowCanvas] Drawflow styles injected');
}
