/**
 * Общие THREE-хелперы для мини-графа и (при необходимости) основного канваса.
 */

// Базовый промежуточный радиус (до умножения на nodeRelSize) для каждого уровня.
// Итоговый радиус = r * nodeRelSize * 0.5; r = base + ratio * BONUS.
// Хранится как r^3, чтобы Math.cbrt в canvas вернул ровно r.
export const GRAPH_NODE_BASE_RADIUS_ROOT = 1.5;
export const GRAPH_NODE_BASE_RADIUS_LEVEL = 1.0;
export const GRAPH_NODE_WEIGHT_BONUS_MAX = 2.5;

// Алиасы для обратной совместимости с импортами, если есть
export const GRAPH_NODE_SIZE_BASE_ROOT = GRAPH_NODE_BASE_RADIUS_ROOT;
export const GRAPH_NODE_SIZE_BASE_LEVEL = GRAPH_NODE_BASE_RADIUS_LEVEL;

/**
 * Сумма весов инцидентных рёбер по id узла для текущего среза графа.
 * Петля (source === target) учитывает вес один раз.
 */
export function aggregateIncidentWeightsByNode(edges) {
    const map = new Map();
    if (!Array.isArray(edges)) {
        return map;
    }
    for (const edge of edges) {
        const sourceId = edge.source_id || edge.source_entity_id || edge.source;
        const targetId = edge.target_id || edge.target_entity_id || edge.target;
        if (typeof sourceId !== 'string' || typeof targetId !== 'string') {
            continue;
        }
        const edgeWeight = typeof edge.weight === 'number' && Number.isFinite(edge.weight) ? edge.weight : 1;
        if (sourceId === targetId) {
            map.set(sourceId, (map.get(sourceId) || 0) + edgeWeight);
        } else {
            map.set(sourceId, (map.get(sourceId) || 0) + edgeWeight);
            map.set(targetId, (map.get(targetId) || 0) + edgeWeight);
        }
    }
    return map;
}

export function maxIncidentWeightOrOne(weightByNodeId) {
    let max = 0;
    for (const v of weightByNodeId.values()) {
        if (v > max) {
            max = v;
        }
    }
    return Math.max(1, max);
}

export function computeGraphNodeDisplaySize(level, totalWeight, maxWeight) {
    const baseR = level === 0 ? GRAPH_NODE_BASE_RADIUS_ROOT : GRAPH_NODE_BASE_RADIUS_LEVEL;
    const safeMax = maxWeight > 0 ? maxWeight : 1;
    const weightRatio = Math.min(1, totalWeight / safeMax);
    const r = baseR + weightRatio * GRAPH_NODE_WEIGHT_BONUS_MAX;
    // Возвращаем куб r, чтобы Math.cbrt(size) в canvas вернул ровно r.
    // Итоговый визуальный радиус = r * nodeRelSize * 0.5.
    return r * r * r;
}

export function createGraphTextSprite(text, color, fontSize = 16, maxLength = 20) {
    if (!window.THREE || typeof window.THREE.CanvasTexture !== 'function' || typeof window.THREE.Sprite !== 'function') {
        throw new Error('THREE.js is not available for text sprite rendering');
    }
    const baseText = typeof text === 'string' && text.trim().length > 0 ? text.trim() : 'entity';
    const labelText = baseText.length > maxLength ? `${baseText.slice(0, maxLength - 1)}\u2026` : baseText;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) {
        throw new Error('Cannot create 2d canvas context for text sprite');
    }
    context.font = `700 ${fontSize}px Inter, sans-serif`;
    const textWidth = Math.max(24, Math.ceil(context.measureText(labelText).width));
    canvas.width = textWidth + 18;
    canvas.height = fontSize + 12;
    context.font = `700 ${fontSize}px Inter, sans-serif`;
    context.fillStyle = color;
    context.textBaseline = 'middle';
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    context.shadowColor = isDark ? 'rgba(5, 7, 12, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    context.shadowBlur = 6;
    context.lineWidth = 4;
    context.strokeStyle = isDark ? 'rgba(5, 7, 12, 0.92)' : 'rgba(255, 255, 255, 0.92)';
    context.strokeText(labelText, 8, canvas.height / 2);
    context.fillText(labelText, 8, canvas.height / 2);
    const texture = new window.THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    const material = new window.THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const sprite = new window.THREE.Sprite(material);
    const scale = fontSize >= 20 ? 0.07 : 0.06;
    sprite.scale.set(canvas.width * scale, canvas.height * scale, 1);
    sprite.renderOrder = 999;
    return sprite;
}

/**
 * Подпись узла: основная строка + опциональная вторая (например суммарный вес связей).
 */
export function createGraphNodeLabelSprite(options) {
    const {
        title,
        subtitle,
        titleColor,
        subtitleColor,
        titleFontSize = 24,
        subtitleFontSize = 14,
        maxTitleLength = 28,
        maxSubtitleLength = 32,
    } = options;
    const sub = typeof subtitle === 'string' && subtitle.trim().length > 0 ? subtitle.trim() : '';
    if (!sub) {
        return createGraphTextSprite(title, titleColor, titleFontSize, maxTitleLength);
    }
    if (!window.THREE || typeof window.THREE.CanvasTexture !== 'function' || typeof window.THREE.Sprite !== 'function') {
        throw new Error('THREE.js is not available for text sprite rendering');
    }
    const baseTitle = typeof title === 'string' && title.trim().length > 0 ? title.trim() : 'entity';
    const line1 = baseTitle.length > maxTitleLength ? `${baseTitle.slice(0, maxTitleLength - 1)}\u2026` : baseTitle;
    const line2 = sub.length > maxSubtitleLength ? `${sub.slice(0, maxSubtitleLength - 1)}\u2026` : sub;

    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) {
        throw new Error('Cannot create 2d canvas context for text sprite');
    }
    const padX = 8;
    const padY = 6;
    const gap = 2;
    context.font = `700 ${titleFontSize}px Inter, sans-serif`;
    const w1 = Math.ceil(context.measureText(line1).width);
    context.font = `600 ${subtitleFontSize}px Inter, sans-serif`;
    const w2 = Math.ceil(context.measureText(line2).width);
    const innerW = Math.max(24, w1, w2);
    canvas.width = innerW + padX * 2;
    canvas.height = padY + titleFontSize + gap + subtitleFontSize + padY;

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const strokeCol = isDark ? 'rgba(5, 7, 12, 0.92)' : 'rgba(255, 255, 255, 0.92)';
    const shadowCol = isDark ? 'rgba(5, 7, 12, 0.95)' : 'rgba(255, 255, 255, 0.95)';

    context.textBaseline = 'top';
    context.shadowColor = shadowCol;
    context.shadowBlur = 6;

    context.font = `700 ${titleFontSize}px Inter, sans-serif`;
    context.fillStyle = titleColor;
    context.lineWidth = 4;
    context.strokeStyle = strokeCol;
    const y1 = padY;
    context.strokeText(line1, padX, y1);
    context.fillText(line1, padX, y1);

    const subCol = typeof subtitleColor === 'string' && subtitleColor.trim().length > 0
        ? subtitleColor.trim()
        : titleColor;
    context.font = `600 ${subtitleFontSize}px Inter, sans-serif`;
    context.fillStyle = subCol;
    context.lineWidth = 3;
    const y2 = padY + titleFontSize + gap;
    context.strokeText(line2, padX, y2);
    context.fillText(line2, padX, y2);

    const texture = new window.THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    const material = new window.THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const sprite = new window.THREE.Sprite(material);
    const scale = titleFontSize >= 20 ? 0.07 : 0.06;
    sprite.scale.set(canvas.width * scale, canvas.height * scale, 1);
    sprite.renderOrder = 999;
    return sprite;
}

/**
 * Матовая сфера + подпись, как на основном graph-canvas.
 */
export function createMatteSphereNodeGroup(node, options) {
    const THREE = window.THREE;
    if (!THREE) {
        throw new Error('THREE.js is not available');
    }
    const nodeRelSize = typeof options.nodeRelSize === 'number' ? options.nodeRelSize : 4;
    const labelColor = typeof options.labelColor === 'string' ? options.labelColor : '#f0f4ff';
    const labelFontSize = typeof options.labelFontSize === 'number' ? options.labelFontSize : 16;
    const subtitleColor = typeof options.subtitleColor === 'string' ? options.subtitleColor : labelColor;
    const radius = Math.cbrt(node.size || 1) * nodeRelSize * 0.5;
    const geometry = new THREE.SphereGeometry(radius, 32, 24);
    const material = new THREE.MeshStandardMaterial({
        color: node.color || '#bca8ff',
        roughness: 0.75,
        metalness: 0.05,
    });
    const sphere = new THREE.Mesh(geometry, material);
    const group = new THREE.Group();
    group.add(sphere);
    const subtitle = typeof node.graph_weight_subtitle === 'string' && node.graph_weight_subtitle.trim().length > 0
        ? node.graph_weight_subtitle.trim()
        : '';
    const sprite = subtitle
        ? createGraphNodeLabelSprite({
            title: node.name || node.id || '',
            subtitle,
            titleColor: labelColor,
            subtitleColor,
            titleFontSize: labelFontSize,
            subtitleFontSize: Math.max(11, Math.floor(labelFontSize * 0.58)),
            maxTitleLength: 20,
            maxSubtitleLength: 28,
        })
        : createGraphTextSprite(node.name || node.id || '', labelColor, labelFontSize, 20);
    sprite.position.set(0, radius + 3, 0);
    group.add(sprite);
    return group;
}
