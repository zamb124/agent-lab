/**
 * Простой EventEmitter для управления событиями
 */
export class EventEmitter {
    constructor() {
        this.events = new Map();
    }
    
    on(event, handler) {
        if (!this.events.has(event)) {
            this.events.set(event, []);
        }
        this.events.get(event).push(handler);
        
        return () => this.off(event, handler);
    }
    
    off(event, handler) {
        if (!this.events.has(event)) return;
        
        const handlers = this.events.get(event);
        const index = handlers.indexOf(handler);
        if (index > -1) {
            handlers.splice(index, 1);
        }
        
        if (handlers.length === 0) {
            this.events.delete(event);
        }
    }
    
    emit(event, data) {
        if (!this.events.has(event)) return;
        
        const handlers = this.events.get(event);
        handlers.forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                console.error(`Ошибка в обработчике события "${event}":`, error);
            }
        });
    }
    
    once(event, handler) {
        const onceHandler = (data) => {
            handler(data);
            this.off(event, onceHandler);
        };
        this.on(event, onceHandler);
    }
    
    removeAllListeners(event) {
        if (event) {
            this.events.delete(event);
        } else {
            this.events.clear();
        }
    }
}

