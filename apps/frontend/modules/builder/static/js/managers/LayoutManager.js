/**
 * LayoutManager - автоматическое размещение нод при разворачивании
 */
export class LayoutManager {
    constructor() {
        this.horizontalSpacing = 300;
        this.verticalSpacing = 150;
        this.currentLevel = 0;
        this.nodesPerLevel = new Map();
    }
    
    /**
     * Получение следующей позиции для ноды
     */
    getNextPosition(parentNode) {
        const level = this.currentLevel + 1;
        
        // Количество нод на этом уровне
        const nodesAtLevel = this.nodesPerLevel.get(level) || 0;
        this.nodesPerLevel.set(level, nodesAtLevel + 1);
        
        // Позиция: справа от родителя + смещение вниз для каждой следующей ноды
        const x = parentNode.x + this.horizontalSpacing;
        const y = parentNode.y + (nodesAtLevel * this.verticalSpacing);
        
        return { x, y };
    }
    
    /**
     * Сброс уровня (при переходе к новой ветке)
     */
    resetLevel() {
        this.currentLevel = 0;
        this.nodesPerLevel.clear();
    }
    
    /**
     * Увеличение уровня вложенности
     */
    increaseLevel() {
        this.currentLevel++;
    }
    
    /**
     * Уменьшение уровня вложенности
     */
    decreaseLevel() {
        this.currentLevel = Math.max(0, this.currentLevel - 1);
    }
}

