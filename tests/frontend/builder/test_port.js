/**
 * Unit-тесты для Port
 */

import { Port } from '../../../app/frontend/modules/builder/static/js/core/Port.js';

describe('Port', () => {
    let port;
    let mockNode;
    
    beforeEach(() => {
        mockNode = {
            id: 'test_node',
            canvas: {
                zoom: 1,
                panX: 0,
                panY: 0
            }
        };
        
        port = new Port({
            id: 'test_port',
            type: 'output',
            node: mockNode
        });
    });
    
    test('должен создаваться корректно', () => {
        expect(port.id).toBe('test_port');
        expect(port.type).toBe('output');
        expect(port.node).toBe(mockNode);
        expect(port.element).toBeNull();
        expect(port.connections.size).toBe(0);
    });
    
    test('должен поддерживать label', () => {
        const portWithLabel = new Port({
            id: 'labeled_port',
            type: 'output',
            node: mockNode,
            label: 'True'
        });
        
        expect(portWithLabel.label).toBe('True');
    });
    
    test('должен создавать DOM элемент', () => {
        const element = port.createElement();
        
        expect(element).toBeInstanceOf(HTMLElement);
        expect(element.className).toContain('port');
        expect(element.className).toContain('output-port');
        expect(element.dataset.portType).toBe('output');
        expect(element.dataset.portId).toBe('test_port');
        expect(element.querySelector('.port-dot')).toBeTruthy();
    });
    
    test('должен создавать элемент с label', () => {
        const portWithLabel = new Port({
            id: 'labeled',
            type: 'output',
            node: mockNode,
            label: 'Success'
        });
        
        const element = portWithLabel.createElement();
        const labelEl = element.querySelector('.port-label');
        
        expect(labelEl).toBeTruthy();
        expect(labelEl.textContent).toBe('Success');
    });
    
    test('должен добавлять соединение', () => {
        port.addConnection('edge_1');
        
        expect(port.connections.has('edge_1')).toBe(true);
        expect(port.connections.size).toBe(1);
    });
    
    test('должен удалять соединение', () => {
        port.addConnection('edge_1');
        port.addConnection('edge_2');
        port.removeConnection('edge_1');
        
        expect(port.connections.has('edge_1')).toBe(false);
        expect(port.connections.has('edge_2')).toBe(true);
        expect(port.connections.size).toBe(1);
    });
    
    test('должен эмитить событие port:mousedown', () => {
        const handler = jest.fn();
        port.on('port:mousedown', handler);
        
        const mockEvent = new MouseEvent('mousedown');
        port.onMouseDown(mockEvent);
        
        expect(handler).toHaveBeenCalledWith({
            port,
            event: mockEvent
        });
    });
    
    test('должен подсвечиваться', () => {
        port.element = document.createElement('div');
        
        port.highlight();
        expect(port.element.classList.contains('highlight')).toBe(true);
        
        port.unhighlight();
        expect(port.element.classList.contains('highlight')).toBe(false);
    });
    
    test('должен устанавливать состояние connecting', () => {
        port.element = document.createElement('div');
        
        port.setConnecting(true);
        expect(port.element.classList.contains('connecting')).toBe(true);
        
        port.setConnecting(false);
        expect(port.element.classList.contains('connecting')).toBe(false);
    });
    
    test('должен корректно очищаться при destroy', () => {
        port.element = document.createElement('div');
        document.body.appendChild(port.element);
        port.addConnection('edge_1');
        
        const handler = jest.fn();
        port.on('test', handler);
        
        port.destroy();
        
        expect(port.element).toBeNull();
        expect(port.connections.size).toBe(0);
        
        port.emit('test');
        expect(handler).not.toHaveBeenCalled();
    });
});

