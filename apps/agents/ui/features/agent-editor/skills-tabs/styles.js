import { css } from 'lit';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';

export const skillsTabsBarStyles = css`
    ${glassStyles}
    
    :host {
        display: block;
        background: var(--glass-solid-subtle);
        border-bottom: 1px solid var(--border-subtle);
    }
    
    .skills-tabs-bar {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-2) var(--space-4);
        overflow: hidden;
    }
    
    .skills-tabs {
        display: flex;
        align-items: center;
        gap: var(--space-1);
        flex: 1;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-width: none;
    }
    
    .skills-tabs::-webkit-scrollbar {
        display: none;
    }
    
    .skill-tab {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-2) var(--space-3);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--text-tertiary);
        background: transparent;
        border: none;
        border-radius: var(--radius-full);
        cursor: pointer;
        transition: all var(--duration-fast) var(--easing-default);
        white-space: nowrap;
        flex-shrink: 0;
    }
    
    .skill-tab:hover {
        color: var(--text-secondary);
        background: var(--glass-tint-subtle);
    }
    
    .skill-tab.active {
        color: var(--text-primary);
        background: var(--bg-elevated);
        box-shadow: var(--glass-shadow-subtle);
    }
    
    .skill-close-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        color: var(--text-tertiary);
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        cursor: pointer;
        transition: all var(--duration-fast) var(--easing-default);
    }
    
    .skill-close-btn:hover {
        color: var(--error);
        background: var(--error-bg);
    }
    
    .add-skill-btn {
        display: flex;
        align-items: center;
        gap: var(--space-1);
        padding: var(--space-2) var(--space-3);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--text-tertiary);
        background: transparent;
        border: 1px dashed var(--border-subtle);
        border-radius: var(--radius-full);
        cursor: pointer;
        transition: all var(--duration-fast) var(--easing-default);
        white-space: nowrap;
        flex-shrink: 0;
    }
    
    .add-skill-btn:hover {
        color: var(--accent);
        border-color: var(--accent);
        background: var(--glass-tint-subtle);
    }
`;
