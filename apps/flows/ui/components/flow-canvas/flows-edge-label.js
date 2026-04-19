/**
 * flows-edge-label — SVG-overlay подпись условия на ребре.
 *
 * Рендерится прямо в SVG родителя как `<g>`. Координаты приходят из
 * `flows-flow-canvas`, которая уже посчитала pmidpoint ребра. Click по
 * подписи диспатчит `edit-condition` для родителя.
 */

import { svg } from 'lit';

export function renderEdgeLabel({ edgeId, x, y, condition, onClick }) {
    const text = typeof condition === 'string' && condition.length > 0 ? condition : '';
    if (text.length === 0) return svg``;
    const padding = 6;
    const charWidth = 6;
    const width = Math.min(220, text.length * charWidth + padding * 2);
    const height = 20;
    return svg`
        <g class="edge-label" data-edge-id=${edgeId} @click=${onClick} transform=${`translate(${x - width / 2}, ${y - height / 2})`}>
            <rect class="label-bg" x="0" y="0" width=${width} height=${height} rx="6" ry="6"></rect>
            <text class="label-text" x=${width / 2} y=${height / 2 + 4} text-anchor="middle">${text.length > 36 ? text.slice(0, 33) + '…' : text}</text>
        </g>
    `;
}
