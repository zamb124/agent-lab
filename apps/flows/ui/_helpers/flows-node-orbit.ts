/**
 * SVG orbit path для running/breakpoint-hit нод на канвасе flow editor.
 */

/**
 * @param {number} width
 * @param {number} height
 * @param {number} radius
 * @param {number} [inset=-3] — отрицательный расширяет orbit наружу от карточки
 * @returns {string}
 */
export function buildNodeOrbitPath(width: any, height: any, radius: any, inset = -3) {
    const x = inset;
    const y = inset;
    const orbitW = width - 2 * inset;
    const orbitH = height - 2 * inset;
    const maxR = Math.min(orbitW / 2, orbitH / 2);
    const r = Math.min(radius - inset, maxR);
    const left = x + r;
    const top = y;
    const right = x + orbitW - r;
    const bottom = y + orbitH;
    const rightX = x + orbitW;
    const bottomY = y + orbitH - r;
    const leftX = x;
    const topY = y + r;

    return [
        `M ${left} ${top}`,
        `L ${right} ${top}`,
        `A ${r} ${r} 0 0 1 ${rightX} ${topY}`,
        `L ${rightX} ${bottomY}`,
        `A ${r} ${r} 0 0 1 ${right} ${bottom}`,
        `L ${left} ${bottom}`,
        `A ${r} ${r} 0 0 1 ${leftX} ${bottomY}`,
        `L ${leftX} ${topY}`,
        `A ${r} ${r} 0 0 1 ${left} ${top}`,
        'Z',
    ].join(' ');
}

/**
 * @param {number} width
 * @param {number} height
 * @param {number} radius
 * @param {number} [inset=-3]
 * @returns {number}
 */
export function nodeOrbitPerimeter(width: any, height: any, radius: any, inset = -3) {
    const orbitW = width - 2 * inset;
    const orbitH = height - 2 * inset;
    const maxR = Math.min(orbitW / 2, orbitH / 2);
    const r = Math.min(radius - inset, maxR);
    return 2 * (orbitW - 2 * r) + 2 * (orbitH - 2 * r) + 2 * Math.PI * r;
}
