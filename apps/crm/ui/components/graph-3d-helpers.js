/**
 * Общие THREE-хелперы для мини-графа и (при необходимости) основного канваса.
 */

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
    const sprite = createGraphTextSprite(node.name || node.id || '', labelColor, labelFontSize, 20);
    sprite.position.set(0, radius + 3, 0);
    group.add(sprite);
    return group;
}
