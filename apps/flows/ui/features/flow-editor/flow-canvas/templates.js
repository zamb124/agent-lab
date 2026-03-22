/**
 * Agent Canvas Templates
 * HTML шаблоны для канваса
 */
import { html } from 'lit';

export function renderCanvas(component) {
    return html`
        <div class="canvas-container">
            <div id="drawflow-area"></div>
            
            ${renderZoomControls(component)}
            ${component.contextMenu ? renderContextMenu(component) : ''}
            ${component.connectionContextMenu ? renderConnectionContextMenu(component) : ''}
            ${component.resourceContextMenu ? renderResourceContextMenu(component) : ''}
        </div>
    `;
}

function renderZoomControls(component) {
    return html`
        <div class="zoom-controls">
            <button class="zoom-btn" @click=${component._zoomIn} title="Zoom In">
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
            <button class="zoom-btn" @click=${component._zoomOut} title="Zoom Out">
                <platform-icon name="minus" size="16"></platform-icon>
            </button>
            <button class="zoom-btn" @click=${component._zoomReset} title="Reset Zoom">
                <platform-icon name="refresh" size="16"></platform-icon>
            </button>
        </div>
    `;
}

function renderContextMenu(component) {
    const menu = component.contextMenu;
    
    return html`
        <div 
            class="context-menu"
            style="left: ${menu.x}px; top: ${menu.y}px;"
            @click=${(e) => e.stopPropagation()}
        >
            <div 
                class="context-menu-item ${menu.isEntry ? 'active' : ''}"
                @click=${component._setAsEntryPoint}
            >
                <platform-icon name="play" size="14"></platform-icon>
                ${menu.isEntry ? 'Entry Point ✓' : 'Set as Entry Point'}
            </div>
            <div class="context-menu-separator"></div>
            <div 
                class="context-menu-item"
                @click=${component._toggleBreakpoint}
            >
                <platform-icon name="breakpoint" size="14"></platform-icon>
                ${menu.hasBreakpoint ? 'Remove Breakpoint' : 'Toggle Breakpoint'}
            </div>
            <div class="context-menu-separator"></div>
            <div class="context-menu-item" @click=${component._duplicateNode}>
                <platform-icon name="copy" size="14"></platform-icon>
                Duplicate
            </div>
            <div class="context-menu-item danger" @click=${component._deleteNode}>
                <platform-icon name="trash" size="14"></platform-icon>
                Delete
            </div>
        </div>
    `;
}

function renderConnectionContextMenu(component) {
    const menu = component.connectionContextMenu;
    
    return html`
        <div 
            class="context-menu"
            style="left: ${menu.x}px; top: ${menu.y}px;"
            @click=${(e) => e.stopPropagation()}
        >
            <div 
                class="context-menu-item"
                @click=${component._onEditConnectionCondition}
            >
                <platform-icon name="edit" size="14"></platform-icon>
                ${menu.currentCondition ? 'Edit Condition' : 'Add Condition'}
            </div>
            <div class="context-menu-separator"></div>
            <div 
                class="context-menu-item danger" 
                @click=${component._onDeleteConnection}
            >
                <platform-icon name="trash" size="14"></platform-icon>
                Delete Connection
            </div>
        </div>
    `;
}

function renderResourceContextMenu(component) {
    const menu = component.resourceContextMenu;
    
    return html`
        <div 
            class="context-menu"
            style="left: ${menu.x}px; top: ${menu.y}px;"
            @click=${(e) => e.stopPropagation()}
        >
            <div 
                class="context-menu-item danger" 
                @click=${component._deleteResource}
            >
                <platform-icon name="trash" size="14"></platform-icon>
                Delete Resource
            </div>
        </div>
    `;
}