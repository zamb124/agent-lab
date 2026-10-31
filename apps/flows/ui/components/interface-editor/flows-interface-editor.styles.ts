import { css } from 'lit';

export const interfaceEditorStyles = css`
    :host { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; min-height: 0; height: 100%; background: var(--bg-elevated); outline: none; }
    .body { display: grid; grid-template-columns: minmax(280px, 320px) minmax(0, 1fr); min-height: 0; }
    .sidebar { min-height: 0; overflow: auto; border-right: 1px solid var(--border-subtle); background: var(--glass-solid-medium); display: grid; grid-template-rows: auto minmax(0, 1fr); }
    .sidebar-tabs { display: block; margin: 8px 10px 0; }
    .canvas { position: relative; min-width: 0; min-height: 0; overflow: auto; padding: 28px 24px 120px; background:
        radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--text-tertiary) 22%, transparent) 1px, transparent 0) 0 0 / 22px 22px; }
    .frame { position: relative; margin: 0 auto; min-height: 480px; border-radius: 16px; border: 1px solid var(--border-subtle); background: var(--bg-primary); box-shadow: var(--glass-shadow-medium); transition: width 180ms ease; overflow: visible; }
    .frame platform-flow-ui { display: block; height: auto; min-height: 480px; border-radius: inherit; overflow: visible; }
    .selection { position: absolute; pointer-events: none; border: 2px solid var(--flow-ui-editor-select); border-radius: 8px; z-index: 3; }
    .selection .label { position: absolute; top: -26px; left: -2px; display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 6px 6px 6px 0; background: var(--flow-ui-editor-select); color: var(--flow-ui-editor-label-fg); font-size: 11px; font-weight: 650; white-space: nowrap; pointer-events: auto; }
    .selection .label .handle { cursor: grab; display: inline-grid; place-items: center; }
    .selection .label .kebab { color: inherit; }
    .drop-line { position: absolute; height: 3px; margin-top: -1px; border-radius: 3px; background: var(--flow-ui-editor-insert); box-shadow: 0 0 0 3px var(--flow-ui-editor-insert-fill); pointer-events: none; z-index: 4; }
    .inline-edit { position: absolute; z-index: 5; box-sizing: border-box; padding: 6px 8px; border: 2px solid var(--flow-ui-editor-select); border-radius: 8px; background: var(--bg-primary); color: var(--text-primary); font: inherit; font-size: 14px; line-height: 1.4; resize: none; outline: none; box-shadow: var(--glass-shadow-medium); }
    .loading { display: grid; place-items: center; height: 100%; color: var(--text-tertiary); font-size: 13px; }
    @media (max-width: 1000px) { .body { grid-template-columns: 240px minmax(0, 1fr); } }
`;
