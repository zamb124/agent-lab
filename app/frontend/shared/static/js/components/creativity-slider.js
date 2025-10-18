/**
 * Creativity Slider Component
 * Управление слайдером креативности с визуальной обратной связью
 */

console.log('🎨 creativity-slider.js загружен');

(function() {
    'use strict';
    
    console.log('🎨 IIFE начал выполняться');

class CreativitySlider {
    constructor(container) {
        this.container = container;
        this.slider = container.querySelector('.creativity-slider');
        this.fill = container.querySelector('.creativity-fill');
        this.segments = container.querySelectorAll('.segment');
        this.modeLabel = container.querySelector('.creativity-mode');
        this.valueLabel = container.querySelector('.creativity-value');
        
        console.log('🎨 CreativitySlider инициализирован:', {
            slider: !!this.slider,
            fill: !!this.fill,
            segments: this.segments.length,
            modeLabel: !!this.modeLabel,
            valueLabel: !!this.valueLabel
        });
        
        this.labels = {
            '0.1-0.5': 'Строгий',
            '0.5-0.7': 'Умеренный',
            '0.8-1.0': 'Креативный'
        };
        
        try {
            const dataLabels = this.slider.dataset.labels;
            if (dataLabels && dataLabels !== '{}') {
                this.labels = JSON.parse(dataLabels);
            }
        } catch (e) {
            console.warn('Не удалось распарсить labels, используем дефолтные');
        }
        
        this.init();
    }
    
    init() {
        console.log('🎨 CreativitySlider.init() вызван, текущее значение:', this.slider.value);
        this.updateUI();
        
        this.slider.addEventListener('input', () => {
            console.log('🎨 Slider input event:', this.slider.value);
            this.updateUI();
        });
        
        this.slider.addEventListener('change', () => {
            console.log('🎨 Slider change event:', this.slider.value);
            this.updateUI();
        });
    }
    
    updateUI() {
        const value = parseFloat(this.slider.value);
        const min = parseFloat(this.slider.min);
        const max = parseFloat(this.slider.max);
        
        const percentage = ((value - min) / (max - min)) * 100;
        
        this.fill.style.width = `${percentage}%`;
        
        const activeCount = Math.ceil(percentage / 10);
        this.segments.forEach((segment, index) => {
            if (index < activeCount) {
                segment.classList.add('active');
            } else {
                segment.classList.remove('active');
            }
        });
        
        const { mode, className } = this.getModeForValue(value);
        
        // Обновляем label в контейнере (старый способ)
        if (this.modeLabel) {
            this.modeLabel.textContent = mode;
            this.modeLabel.className = `creativity-mode ${className}`;
        }
        
        if (this.valueLabel) {
            this.valueLabel.textContent = value.toFixed(1);
        }
        
        // Обновляем inline label в заголовке (новый способ)
        const inlineLabel = document.getElementById('creativity-mode-label');
        if (inlineLabel) {
            inlineLabel.textContent = `[${mode.toLowerCase()}]`;
            inlineLabel.className = `creativity-mode-inline ${className}`;
        }
    }
    
    getModeForValue(value) {
        if (value >= 0.1 && value < 0.5) {
            return { mode: this.labels['0.1-0.5'] || 'Строгий', className: 'strict' };
        } else if (value >= 0.5 && value < 0.8) {
            return { mode: this.labels['0.5-0.7'] || 'Умеренный', className: 'moderate' };
        } else {
            return { mode: this.labels['0.8-1.0'] || 'Креативный', className: 'creative' };
        }
    }
    
    getValue() {
        return parseFloat(this.slider.value);
    }
    
    setValue(value) {
        this.slider.value = value;
        this.updateUI();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('🎨 DOMContentLoaded - ищем слайдеры...');
    const containers = document.querySelectorAll('.creativity-slider-container');
    console.log('🎨 Найдено контейнеров:', containers.length);
    containers.forEach((container, index) => {
        console.log(`🎨 Инициализация слайдера #${index}`);
        new CreativitySlider(container);
    });
});

document.addEventListener('htmx:afterSettle', (event) => {
    console.log('🎨 htmx:afterSettle - ищем новые слайдеры...');
    console.log('🎨 Event target:', event.target);
    console.log('🎨 Event detail:', event.detail);
    
    // Даем время DOM обновиться
    setTimeout(() => {
        const containers = document.querySelectorAll('.creativity-slider-container');
        console.log('🎨 Найдено контейнеров после afterSettle:', containers.length);
        
        if (containers.length === 0) {
            console.log('🎨 Проверим что вообще есть в DOM:');
            console.log('🎨 bot-llm-temperature:', document.getElementById('bot-llm-temperature'));
            console.log('🎨 control-value:', document.querySelectorAll('.control-value').length);
        }
        
        containers.forEach(container => {
            if (!container.dataset.initialized) {
                console.log('🎨 Инициализируем слайдер!');
                new CreativitySlider(container);
                container.dataset.initialized = 'true';
            }
        });
    }, 100);
});

// MutationObserver для отслеживания новых элементов
const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
            if (node.nodeType === 1) {
                // Проверяем сам элемент
                if (node.classList && node.classList.contains('creativity-slider-container') && !node.dataset.initialized) {
                    console.log('🎨 MutationObserver: найден новый слайдер!');
                    new CreativitySlider(node);
                    node.dataset.initialized = 'true';
                }
                // Проверяем дочерние элементы
                const containers = node.querySelectorAll && node.querySelectorAll('.creativity-slider-container');
                if (containers) {
                    containers.forEach(container => {
                        if (!container.dataset.initialized) {
                            console.log('🎨 MutationObserver: найден слайдер в дочерних элементах!');
                            new CreativitySlider(container);
                            container.dataset.initialized = 'true';
                        }
                    });
                }
            }
        });
    });
});

// Начинаем наблюдение за изменениями в DOM
observer.observe(document.body, {
    childList: true,
    subtree: true
});

console.log('🎨 MutationObserver запущен');

// Экспорт для использования в других модулях
window.CreativitySlider = CreativitySlider;

})();

