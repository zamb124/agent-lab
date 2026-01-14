/**
 * Debug script для проверки стилей Canvas
 * Вставьте в консоль браузера для диагностики
 */

// 1. Проверить что canvas существует
const canvas = document.querySelector('agent-canvas');
console.log('Canvas найден:', !!canvas);

// 2. Найти первую ноду
const firstNode = canvas?.querySelector('.drawflow-node');
console.log('Первая нода найдена:', !!firstNode);
if (firstNode) {
    console.log('ID ноды:', firstNode.id);
    console.log('Классы ноды:', firstNode.className);
}

// 3. Проверить что стили инжектированы
const styleTag = document.getElementById('drawflow-custom-styles');
console.log('Style tag найден:', !!styleTag);
if (styleTag) {
    const hasRunningStyles = styleTag.textContent.includes('node-running');
    console.log('Содержит стили node-running:', hasRunningStyles);
}

// 4. Функция для ручной проверки статуса
window.testNodeStatus = function(nodeId, status) {
    const canvas = document.querySelector('agent-canvas');
    if (!canvas) {
        console.error('Canvas не найден');
        return;
    }
    
    // Найти ноду
    let nodeEl = null;
    canvas.querySelectorAll('.drawflow-node').forEach(node => {
        if (node.id.includes(nodeId)) {
            nodeEl = node;
        }
    });
    
    if (!nodeEl) {
        console.error('Нода не найдена:', nodeId);
        return;
    }
    
    console.log('Нода найдена:', nodeEl.id);
    console.log('Классы ДО:', nodeEl.className);
    
    // Применить статус
    nodeEl.classList.remove('node-running', 'node-completed', 'node-error');
    if (status) {
        nodeEl.classList.add(`node-${status}`);
    }
    
    console.log('Классы ПОСЛЕ:', nodeEl.className);
    
    // Проверить computed styles
    const computedStyle = getComputedStyle(nodeEl);
    console.log('Computed border:', computedStyle.border);
    console.log('Computed box-shadow:', computedStyle.boxShadow);
    console.log('Computed z-index:', computedStyle.zIndex);
    console.log('Computed animation:', computedStyle.animation);
    
    return nodeEl;
};

console.log('');
console.log('=== Доступные команды ===');
console.log('testNodeStatus("start", "running") - тест running статуса');
console.log('testNodeStatus("start", "completed") - тест completed статуса');
console.log('testNodeStatus("start", null) - очистить статус');

