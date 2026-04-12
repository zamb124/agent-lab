/**
 * BreakpointManager - управление breakpoints (только логика, БЕЗ визуализации)
 * Независимый компонент для управления точками остановки в графах
 * 
 * Public API:
 * - Properties: .nodeIds
 * - Methods: toggleBreakpoint(), setBreakpoint(), clearBreakpoint(), getBreakpointsObject(), hasBreakpoint()
 * - Events: breakpoint-toggled, breakpoint-hit, breakpoint-cleared
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class BreakpointManager extends PlatformElement {
    static properties = {
        nodeIds: { type: Array },
    };

    constructor() {
        super();
        this.nodeIds = [];
        this._breakpoints = new Map();
        this._activeBreakpoint = null;
        this._breakpointState = null;
    }

    render() {
        return null;
    }

    /**
     * Проверяет, установлен ли breakpoint на ноде
     */
    hasBreakpoint(nodeId) {
        return this._breakpoints.get(nodeId) === true;
    }

    /**
     * Проверяет, активен ли breakpoint на ноде (сработал)
     */
    isBreakpointActive(nodeId) {
        return this._activeBreakpoint === nodeId;
    }

    /**
     * Переключает breakpoint на ноде (toggle)
     */
    toggleBreakpoint(nodeId) {
        const isEnabled = this.hasBreakpoint(nodeId);
        this.setBreakpoint(nodeId, !isEnabled);
    }

    /**
     * Устанавливает или снимает breakpoint
     */
    setBreakpoint(nodeId, enabled) {
        if (enabled) {
            this._breakpoints.set(nodeId, true);
            console.log(`[BreakpointManager] Breakpoint set on node "${nodeId}"`);
        } else {
            this._breakpoints.delete(nodeId);
            console.log(`[BreakpointManager] Breakpoint cleared on node "${nodeId}"`);
        }
        
        this.emit('breakpoint-toggled', { nodeId, enabled });
    }

    clearBreakpoint(nodeId) {
        if (this._breakpoints.has(nodeId)) {
            this._breakpoints.delete(nodeId);
            this.emit('breakpoint-cleared', { nodeId });
        }
    }

    clearAll() {
        this._breakpoints.clear();
        this.clearActiveBreakpoint();
        console.log('[BreakpointManager] All breakpoints cleared');
    }

    /**
     * Возвращает breakpoints как объект для передачи в metadata
     */
    getBreakpointsObject() {
        const result = {};
        for (const [nodeId, enabled] of this._breakpoints.entries()) {
            if (enabled) {
                result[nodeId] = true;
            }
        }
        return result;
    }

    /**
     * Обрабатывает событие breakpoint hit
     */
    handleBreakpointHit(nodeId, nodeType, stateSnapshot) {
        console.log('[BreakpointManager] Breakpoint hit:', { nodeId, nodeType });

        this._activeBreakpoint = nodeId;
        this._breakpointState = stateSnapshot;

        this.emit('breakpoint-hit', { nodeId, nodeType, stateSnapshot });
    }

    clearActiveBreakpoint() {
        const previousActive = this._activeBreakpoint;
        this._activeBreakpoint = null;
        this._breakpointState = null;

        if (previousActive) {
            this.emit('breakpoint-cleared', { nodeId: previousActive });
        }
    }

    /**
     * Получает state для текущего breakpoint
     */
    getBreakpointState() {
        return this._breakpointState;
    }

    /**
     * Получает активный breakpoint nodeId
     */
    getActiveBreakpoint() {
        return this._activeBreakpoint;
    }

    /**
     * Получает все breakpoints как Map
     */
    getBreakpointsMap() {
        return new Map(this._breakpoints);
    }
}

customElements.define('breakpoint-manager', BreakpointManager);

