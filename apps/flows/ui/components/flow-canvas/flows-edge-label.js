/**
 * flows-edge-label — SVG-overlay подпись условия на ребре.
 *
 * Рендерится прямо в SVG родителя как `<g>`. Координаты приходят из
 * `flows-flow-canvas`, которая уже посчитала midpoint ребра. Click по
 * подписи открывает настройки ребра (модалка условия; onOpen).
 *
 * `condition` может быть:
 *   - строкой legacy-выражения (`route == 'order'`);
 *   - объектом `{type: 'simple', variable, operator, value}`;
 *   - legacy-объектом `{type: 'python', code}`;
 *   - объектом `{type: 'code', language, code}`.
 */

import { svg } from 'lit';
import { flowCodeLanguageShortLabel } from '../../_helpers/flows-code-languages.js';

const MAX_VISIBLE = 36;

function quoteValue(value) {
    if (value === null || value === undefined) return "''";
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return String(value);
    const str = String(value);
    if (str.length === 0) return "''";
    if (!Number.isNaN(Number(str))) return str;
    return `'${str}'`;
}

export function formatEdgeCondition(condition) {
    if (condition === null || condition === undefined) return '';
    if (typeof condition === 'string') return condition;
    if (typeof condition !== 'object') return '';
    const type = condition.type;
    if (type === 'simple') {
        const variable = typeof condition.variable === 'string' ? condition.variable : '';
        const operator = typeof condition.operator === 'string' ? condition.operator : '==';
        const value = quoteValue(condition.value);
        if (variable.length === 0) return '';
        return `${variable} ${operator} ${value}`;
    }
    if (type === 'python') {
        return 'check(state)';
    }
    if (type === 'code') {
        const label = flowCodeLanguageShortLabel(condition.language);
        return `check · ${label}`;
    }
    return '';
}

export function renderEdgeLabel({ edgeId, x, y, condition, onOpen }) {
    const fromCond = formatEdgeCondition(condition);
    const isPlaceholder = fromCond.length === 0;
    const text = isPlaceholder ? '\u2014' : fromCond;
    const padding = 6;
    const charWidth = 6;
    const visible = text.length > MAX_VISIBLE ? `${text.slice(0, MAX_VISIBLE - 3)}…` : text;
    const width = Math.min(220, Math.max(visible.length * charWidth + padding * 2, 36));
    const height = 20;
    const gClass = isPlaceholder ? 'edge-label edge-label--empty' : 'edge-label';
    return svg`
        <g
            class=${gClass}
            data-edge-id=${edgeId}
            ?data-placeholder=${isPlaceholder}
            transform=${`translate(${x - width / 2}, ${y - height / 2})`}
            @pointerdown=${(e) => e.stopPropagation()}
            @click=${(e) => {
                e.stopPropagation();
                onOpen();
            }}
        >
            <rect class="label-bg" x="0" y="0" width=${width} height=${height} rx="6" ry="6"></rect>
            <text class="label-text" x=${width / 2} y=${height / 2 + 4} text-anchor="middle">${visible}</text>
        </g>
    `;
}
