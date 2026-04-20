/**
 * flows-edge-label — SVG-overlay подпись условия на ребре.
 *
 * Рендерится прямо в SVG родителя как `<g>`. Координаты приходят из
 * `flows-flow-canvas`, которая уже посчитала midpoint ребра. Click по
 * подписи открывает модалку условия (callback приходит сверху).
 *
 * `condition` может быть:
 *   - строкой legacy-выражения (`route == 'order'`);
 *   - объектом `{type: 'simple', variable, operator, value}`;
 *   - объектом `{type: 'python', code}`.
 */

import { svg } from 'lit';

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
    return '';
}

export function renderEdgeLabel({ edgeId, x, y, condition, onClick }) {
    const text = formatEdgeCondition(condition);
    if (text.length === 0) return svg``;
    const padding = 6;
    const charWidth = 6;
    const visible = text.length > MAX_VISIBLE ? `${text.slice(0, MAX_VISIBLE - 3)}…` : text;
    const width = Math.min(220, visible.length * charWidth + padding * 2);
    const height = 20;
    return svg`
        <g class="edge-label" data-edge-id=${edgeId} @click=${onClick} transform=${`translate(${x - width / 2}, ${y - height / 2})`}>
            <rect class="label-bg" x="0" y="0" width=${width} height=${height} rx="6" ry="6"></rect>
            <text class="label-text" x=${width / 2} y=${height / 2 + 4} text-anchor="middle">${visible}</text>
        </g>
    `;
}
