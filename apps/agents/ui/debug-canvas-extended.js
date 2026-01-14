/**
 * Расширенная диагностика стилей Canvas
 * Вставьте в консоль браузера
 */

console.log('=== ДИАГНОСТИКА СТИЛЕЙ CANVAS ===\n');

// 1. Проверить style tag
const styleTag = document.getElementById('drawflow-custom-styles');
console.log('1. Style tag найден:', !!styleTag);

if (styleTag) {
    const content = styleTag.textContent;
    console.log('2. Размер контента:', content.length, 'символов');
    
    // Проверить конкретные правила
    const hasNodeRunning = content.includes('.drawflow .drawflow-node.node-running');
    const hasNodeCompleted = content.includes('.drawflow .drawflow-node.node-completed');
    const hasAnimation = content.includes('@keyframes node-pulse-running');
    
    console.log('3. Содержит .node-running:', hasNodeRunning);
    console.log('4. Содержит .node-completed:', hasNodeCompleted);
    console.log('5. Содержит @keyframes:', hasAnimation);
    
    // Извлечь правило для node-running
    if (hasNodeRunning) {
        const match = content.match(/\.drawflow \.drawflow-node\.node-running\s*\{[^}]+\}/);
        if (match) {
            console.log('\n6. Правило node-running:');
            console.log(match[0]);
        }
    }
}

// 2. Найти ноду и применить стиль вручную
console.log('\n=== ТЕСТ ПРИМЕНЕНИЯ СТИЛЕЙ ===\n');

const canvas = document.querySelector('agent-canvas');
const firstNode = canvas?.querySelector('.drawflow-node');

if (firstNode) {
    console.log('7. Нода найдена:', firstNode.id);
    console.log('8. Классы ДО:', firstNode.className);
    
    // Получить computed styles ДО
    const stylesBefore = getComputedStyle(firstNode);
    console.log('\n9. COMPUTED STYLES ДО:');
    console.log('   border:', stylesBefore.border);
    console.log('   border-width:', stylesBefore.borderWidth);
    console.log('   border-color:', stylesBefore.borderColor);
    console.log('   border-style:', stylesBefore.borderStyle);
    console.log('   box-shadow:', stylesBefore.boxShadow);
    console.log('   z-index:', stylesBefore.zIndex);
    
    // Применить класс
    firstNode.classList.add('node-running');
    console.log('\n10. Классы ПОСЛЕ добавления:', firstNode.className);
    
    // Получить computed styles ПОСЛЕ
    const stylesAfter = getComputedStyle(firstNode);
    console.log('\n11. COMPUTED STYLES ПОСЛЕ:');
    console.log('   border:', stylesAfter.border);
    console.log('   border-width:', stylesAfter.borderWidth);
    console.log('   border-color:', stylesAfter.borderColor);
    console.log('   border-style:', stylesAfter.borderStyle);
    console.log('   box-shadow:', stylesAfter.boxShadow);
    console.log('   z-index:', stylesAfter.zIndex);
    console.log('   animation:', stylesAfter.animation);
    
    // Проверить изменились ли стили
    const borderChanged = stylesBefore.border !== stylesAfter.border;
    const shadowChanged = stylesBefore.boxShadow !== stylesAfter.boxShadow;
    
    console.log('\n12. РЕЗУЛЬТАТ:');
    console.log('   Border изменился:', borderChanged);
    console.log('   Box-shadow изменился:', shadowChanged);
    
    if (!borderChanged && !shadowChanged) {
        console.error('\n❌ СТИЛИ НЕ ПРИМЕНИЛИСЬ!');
        console.log('\nВозможные причины:');
        console.log('1. Другие CSS правила перебивают (проверьте в DevTools)');
        console.log('2. Style tag не тот (проверьте содержимое)');
        console.log('3. Селектор не совпадает (проверьте структуру DOM)');
        
        // Попробовать применить inline стили напрямую
        console.log('\n13. Попытка применить inline стили...');
        firstNode.style.border = '3px solid rgb(59, 130, 246)';
        firstNode.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.3), 0 0 20px rgba(59, 130, 246, 0.8)';
        
        const inlineStylesAfter = getComputedStyle(firstNode);
        console.log('14. После inline стилей border:', inlineStylesAfter.border);
        
        if (inlineStylesAfter.borderWidth === '3px') {
            console.log('✅ Inline стили работают! Проблема в CSS селекторе или специфичности');
        } else {
            console.log('❌ Даже inline стили не работают! Что-то очень странное...');
        }
    } else {
        console.log('\n✅ СТИЛИ ПРИМЕНИЛИСЬ УСПЕШНО!');
    }
} else {
    console.error('❌ Нода не найдена!');
}

console.log('\n=== КОНЕЦ ДИАГНОСТИКИ ===');

