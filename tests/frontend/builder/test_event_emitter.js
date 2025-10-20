/**
 * Unit-тесты для EventEmitter
 */

import { EventEmitter } from '../../../app/frontend/modules/builder/static/js/core/EventEmitter.js';

describe('EventEmitter', () => {
    let emitter;
    
    beforeEach(() => {
        emitter = new EventEmitter();
    });
    
    test('должен создаваться корректно', () => {
        expect(emitter).toBeInstanceOf(EventEmitter);
        expect(emitter.events).toBeInstanceOf(Map);
        expect(emitter.events.size).toBe(0);
    });
    
    test('должен регистрировать обработчик события', () => {
        const handler = jest.fn();
        emitter.on('test', handler);
        
        expect(emitter.events.has('test')).toBe(true);
        expect(emitter.events.get('test')).toContain(handler);
    });
    
    test('должен вызывать обработчик при emit', () => {
        const handler = jest.fn();
        emitter.on('test', handler);
        
        emitter.emit('test', { data: 'value' });
        
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler).toHaveBeenCalledWith({ data: 'value' });
    });
    
    test('должен вызывать множественные обработчики', () => {
        const handler1 = jest.fn();
        const handler2 = jest.fn();
        
        emitter.on('test', handler1);
        emitter.on('test', handler2);
        
        emitter.emit('test');
        
        expect(handler1).toHaveBeenCalledTimes(1);
        expect(handler2).toHaveBeenCalledTimes(1);
    });
    
    test('должен удалять обработчик через off', () => {
        const handler = jest.fn();
        emitter.on('test', handler);
        emitter.off('test', handler);
        
        emitter.emit('test');
        
        expect(handler).not.toHaveBeenCalled();
    });
    
    test('должен удалять обработчик через unsubscribe функцию', () => {
        const handler = jest.fn();
        const unsubscribe = emitter.on('test', handler);
        
        unsubscribe();
        emitter.emit('test');
        
        expect(handler).not.toHaveBeenCalled();
    });
    
    test('должен вызывать once обработчик только один раз', () => {
        const handler = jest.fn();
        emitter.once('test', handler);
        
        emitter.emit('test');
        emitter.emit('test');
        emitter.emit('test');
        
        expect(handler).toHaveBeenCalledTimes(1);
    });
    
    test('должен удалять все обработчики события', () => {
        const handler1 = jest.fn();
        const handler2 = jest.fn();
        
        emitter.on('test', handler1);
        emitter.on('test', handler2);
        
        emitter.removeAllListeners('test');
        emitter.emit('test');
        
        expect(handler1).not.toHaveBeenCalled();
        expect(handler2).not.toHaveBeenCalled();
        expect(emitter.events.has('test')).toBe(false);
    });
    
    test('должен удалять все события при removeAllListeners без параметра', () => {
        emitter.on('event1', jest.fn());
        emitter.on('event2', jest.fn());
        
        emitter.removeAllListeners();
        
        expect(emitter.events.size).toBe(0);
    });
    
    test('должен обрабатывать ошибки в обработчиках', () => {
        const errorHandler = () => { throw new Error('Test error'); };
        const normalHandler = jest.fn();
        
        const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
        
        emitter.on('test', errorHandler);
        emitter.on('test', normalHandler);
        
        emitter.emit('test');
        
        expect(consoleSpy).toHaveBeenCalled();
        expect(normalHandler).toHaveBeenCalled();
        
        consoleSpy.mockRestore();
    });
    
    test('не должен падать при emit несуществующего события', () => {
        expect(() => {
            emitter.emit('nonexistent');
        }).not.toThrow();
    });
});

