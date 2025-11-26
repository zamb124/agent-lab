# Builder v3.0 - ООП Архитектура

## 📐 Структура проекта

```
builder/static/js/
├── builder.module.js          # Главный модуль (точка входа)
├── canvas/
│   └── CanvasCore.js          # Координатор всех компонентов
├── core/
│   ├── EventEmitter.js        # Базовый класс событий
│   ├── BaseNode.js            # Базовый класс нод
│   ├── Port.js                # Порт для соединений
│   └── NodeFactory.js         # Фабрика создания нод
├── nodes/
│   ├── FlowNode.js            # Нода Flow (entry point)
│   ├── AgentNode.js           # Нода Agent
│   ├── ToolNode.js            # Нода Tool
│   ├── MessageNode.js         # Нода Message
│   ├── FunctionNode.js        # Нода Function
│   └── RouterNode.js          # Нода Router (множественные порты)
├── managers/
│   ├── ConnectionManager.js   # Управление связями
│   ├── SelectionManager.js    # Управление выделением
│   └── InteractionManager.js  # Zoom, pan, drag
└── utils/                     # Утилиты (если нужны)
```

## 🏗️ Архитектурные принципы

### 1. **Объектно-ориентированный подход**
- Каждая нода - это класс с lifecycle hooks
- Каждый порт - отдельный объект с событиями
- Менеджеры отвечают за конкретную область

### 2. **Event-Driven Architecture**
- Все взаимодействия через события
- Слабая связанность компонентов
- Легко отследить flow данных

### 3. **Single Responsibility**
- `CanvasCore` - координация
- `NodeFactory` - создание нод
- `ConnectionManager` - связи
- `SelectionManager` - выделение
- `InteractionManager` - взаимодействия

### 4. **Расширяемость**
- Новый тип ноды = новый класс
- Легко добавлять функционал
- Плагинная архитектура

## 🔄 Lifecycle нод

```javascript
// 1. Создание
const node = await nodeFactory.createNode(data);

// 2. Монтирование
node.mount(container);

// 3. Обновление
node.update(newData);

// 4. Уничтожение
node.destroy();
```

## 📡 События

### Canvas Events
- `canvas:ready` - Canvas готов
- `graph:loaded` - Граф загружен
- `graph:cleared` - Граф очищен

### Node Events
- `node:added` - Нода добавлена
- `node:removed` - Нода удалена
- `node:moved` - Нода перемещена
- `node:selected` - Нода выделена
- `node:deselected` - Выделение снято

### Port Events
- `port:mousedown` - Клик по порту

### Edge Events
- `edge:created` - Связь создана
- `edge:removed` - Связь удалена

### Selection Events
- `selection:changed` - Выделение изменено
- `selection:cleared` - Выделение снято
- `selection:deleted` - Выделенное удалено

### Interaction Events
- `zoom:changed` - Zoom изменен
- `pan:start` / `pan:end` - Панорамирование
- `drag:start` / `drag:end` - Перетаскивание

## 🎯 Пример использования

### Создание кастомной ноды

```javascript
import { BaseNode } from '../core/BaseNode.js';

export class CustomNode extends BaseNode {
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node custom-node';
        element.innerHTML = `
            <div class="node-content">
                <h3>${this.data.params?.name}</h3>
            </div>
        `;
        return element;
    }
    
    async createPorts() {
        this.createPort('input', 'input');
        this.createPort('output', 'output');
        this.mountPorts();
    }
}

// Регистрация
nodeFactory.register('custom_node', CustomNode);
```

### Подписка на события

```javascript
canvas.on('node:added', ({ node }) => {
    console.log('Добавлена нода:', node.id);
});

canvas.on('selection:changed', ({ nodes }) => {
    console.log('Выделено нод:', nodes.length);
});
```

### Программное создание графа

```javascript
// Создать ноды
const flowNode = await canvas.addNode({
    id: 'flow_1',
    type: 'flow_node',
    params: { name: 'My Flow' },
    ui: { x: 100, y: 100 }
});

const agentNode = await canvas.addNode({
    id: 'agent_1',
    type: 'agent_node',
    params: { agent_id: 'my_agent' },
    ui: { x: 300, y: 100 }
});

// Создать связь
canvas.connectionManager.createEdge('flow_1', 'agent_1');
```

## 🧪 Тестирование

```javascript
// Пример unit-теста
import { BaseNode } from './core/BaseNode.js';

test('BaseNode создается корректно', () => {
    const node = new BaseNode({ id: 'test', type: 'test_node' }, canvas);
    expect(node.id).toBe('test');
    expect(node.ports.size).toBe(0);
});
```

## 🚀 Миграция со старой версии

### Было (v2.0):
```javascript
canvas.addNode(nodeData);  // Ручное создание DOM
```

### Стало (v3.0):
```javascript
const node = await canvas.addNode(nodeData);  // ООП объект
node.on('click', () => console.log('Clicked!'));
```

## 💡 Best Practices

1. **Не модифицируй DOM напрямую** - используй методы нод
2. **Подписывайся на события** - не используй прямые вызовы
3. **Используй lifecycle hooks** - onCreate, onUpdate, onDestroy
4. **Создавай кастомные ноды через наследование** от BaseNode
5. **Cleanup при destroy** - удаляй listeners, очищай память

## 🐛 Отладка

```javascript
// Включить детальное логирование
canvas.on('*', (event, data) => {
    console.log('[Canvas Event]', event, data);
});

// Инспекция состояния
console.log('Nodes:', canvas.nodes);
console.log('Edges:', canvas.connectionManager.getAllEdges());
console.log('Selected:', canvas.selectionManager.getSelectedNodes());
```

## 📚 Дополнительно

- Все классы имеют JSDoc комментарии
- Используй TypeScript hints через JSDoc
- Events следуют паттерну `domain:action`
- Менеджеры независимы друг от друга

