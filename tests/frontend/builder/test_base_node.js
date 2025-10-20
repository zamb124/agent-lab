/**
 * Unit-тесты для BaseNode
 */

import { BaseNode } from '../../../app/frontend/modules/builder/static/js/core/BaseNode.js';

describe('BaseNode', () => {
    let node;
    let mockCanvas;
    
    beforeEach(() => {
        mockCanvas = {
            zoom: 1,
            panX: 0,
            panY: 0,
            overlay: document.createElement('div'),
            connectionManager: {
                updateNodeEdges: jest.fn()
            }
        };
        
        const nodeData = {
            id: 'test_node',
            type: 'test_type',
            params: { name: 'Test Node' },
            ui: { x: 100, y: 200, width: 150, height: 80 }
        };
        
        node = new BaseNode(nodeData, mockCanvas);
    });
    
    test('должен создаваться корректно', () => {
        expect(node.id).toBe('test_node');
        expect(node.type).toBe('test_type');
        expect(node.x).toBe(100);
        expect(node.y).toBe(200);
        expect(node.width).toBe(150);
        expect(node.height).toBe(80);
        expect(node.canvas).toBe(mockCanvas);
        expect(node.selected).toBe(false);
        expect(node.dragging).toBe(false);
        expect(node.ports.size).toBe(0);
    });
    
    test('должен использовать дефолтные значения', () => {
        const simpleNode = new BaseNode({ id: 'simple', type: 'simple' }, mockCanvas);
        
        expect(simpleNode.x).toBe(0);
        expect(simpleNode.y).toBe(0);
        expect(simpleNode.width).toBe(200);
        expect(simpleNode.height).toBe(100);
    });
    
    test('должен создавать порт', () => {
        const port = node.createPort('input', 'input');
        
        expect(node.ports.size).toBe(1);
        expect(node.ports.has('input')).toBe(true);
        expect(port.id).toBe('input');
        expect(port.type).toBe('input');
        expect(port.node).toBe(node);
    });
    
    test('должен создавать порт с label', () => {
        const port = node.createPort('true', 'output', 'True');
        
        expect(port.label).toBe('True');
    });
    
    test('должен получать порт по ID', () => {
        node.createPort('input', 'input');
        
        const port = node.getPort('input');
        
        expect(port).toBeTruthy();
        expect(port.id).toBe('input');
    });
    
    test('должен эмитить событие при создании порта', () => {
        const handler = jest.fn();
        node.on('port:mousedown', handler);
        
        const port = node.createPort('input', 'input');
        const mockEvent = new MouseEvent('mousedown');
        
        port.emit('port:mousedown', { port, event: mockEvent });
        
        expect(handler).toHaveBeenCalled();
    });
    
    test('должен обновлять позицию', () => {
        node.element = document.createElement('div');
        const handler = jest.fn();
        node.on('node:moved', handler);
        
        node.setPosition(300, 400);
        
        expect(node.x).toBe(300);
        expect(node.y).toBe(400);
        expect(handler).toHaveBeenCalledWith({
            node,
            x: 300,
            y: 400
        });
    });
    
    test('должен выделяться и сниматься выделение', () => {
        node.element = document.createElement('div');
        const selectHandler = jest.fn();
        const deselectHandler = jest.fn();
        
        node.on('node:selected', selectHandler);
        node.on('node:deselected', deselectHandler);
        
        node.select();
        expect(node.selected).toBe(true);
        expect(node.element.classList.contains('selected')).toBe(true);
        expect(selectHandler).toHaveBeenCalled();
        
        node.deselect();
        expect(node.selected).toBe(false);
        expect(node.element.classList.contains('selected')).toBe(false);
        expect(deselectHandler).toHaveBeenCalled();
    });
    
    test('не должен повторно выделяться', () => {
        node.element = document.createElement('div');
        const handler = jest.fn();
        node.on('node:selected', handler);
        
        node.select();
        node.select();
        
        expect(handler).toHaveBeenCalledTimes(1);
    });
    
    test('должен начинать и завершать перетаскивание', () => {
        node.element = document.createElement('div');
        
        node.startDrag();
        expect(node.dragging).toBe(true);
        expect(node.element.classList.contains('dragging')).toBe(true);
        
        node.stopDrag();
        expect(node.dragging).toBe(false);
        expect(node.element.classList.contains('dragging')).toBe(false);
    });
    
    test('должен возвращать центральную точку', () => {
        const center = node.getCenter();
        
        expect(center.x).toBe(175); // 100 + 150/2
        expect(center.y).toBe(240); // 200 + 80/2
    });
    
    test('должен возвращать точку соединения', () => {
        const inputPoint = node.getConnectionPoint('input');
        const outputPoint = node.getConnectionPoint('output');
        
        expect(inputPoint.x).toBe(100); // x
        expect(inputPoint.y).toBe(240); // center y
        
        expect(outputPoint.x).toBe(250); // x + width
        expect(outputPoint.y).toBe(240); // center y
    });
    
    test('должен сериализоваться в JSON', () => {
        const json = node.toJSON();
        
        expect(json.id).toBe('test_node');
        expect(json.type).toBe('test_type');
        expect(json.ui.x).toBe(100);
        expect(json.ui.y).toBe(200);
        expect(json.ui.width).toBe(150);
        expect(json.ui.height).toBe(80);
    });
    
    test('должен корректно очищаться при destroy', () => {
        node.element = document.createElement('div');
        node.createPort('input', 'input');
        node.createPort('output', 'output');
        
        const handler = jest.fn();
        node.on('test', handler);
        
        node.destroy();
        
        expect(node.element).toBeNull();
        expect(node.ports.size).toBe(0);
        
        node.emit('test');
        expect(handler).not.toHaveBeenCalled();
    });
    
    test('должен выбрасывать ошибку если не реализован createDOMElement', async () => {
        await expect(node.createDOMElement()).rejects.toThrow('must be implemented');
    });
    
    test('должен выбрасывать ошибку если не реализован createPorts', async () => {
        await expect(node.createPorts()).rejects.toThrow('must be implemented');
    });
});

