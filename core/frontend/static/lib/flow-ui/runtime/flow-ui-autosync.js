export class FlowUIAutosync {
    constructor(flush, delay = 320) {
        if (typeof flush !== 'function') {
            throw new Error('FlowUIAutosync requires a flush function');
        }
        if (!Number.isFinite(delay) || delay < 0) {
            throw new Error('FlowUIAutosync delay must be a non-negative number');
        }
        this.flush = flush;
        this.delay = delay;
        this.timer = null;
        this.chain = Promise.resolve();
        this.disposed = false;
    }

    _runFlush() {
        return Promise.resolve()
            .then(() => {
                if (this.disposed) return undefined;
                return this.flush();
            })
            .catch((error) => {
                // Dispose/abort mid-request must not become an unhandled rejection.
                if (this.disposed || (error && typeof error === 'object' && error.name === 'AbortError')) {
                    return undefined;
                }
                throw error;
            });
    }

    schedule() {
        if (this.disposed) return;
        if (this.timer !== null) clearTimeout(this.timer);
        this.timer = setTimeout(() => {
            this.timer = null;
            if (this.disposed) return;
            this.chain = this.chain.then(() => this._runFlush(), () => this._runFlush());
        }, this.delay);
    }

    async flushNow() {
        if (this.disposed) return;
        if (this.timer !== null) {
            clearTimeout(this.timer);
            this.timer = null;
        }
        this.chain = this.chain.then(() => this._runFlush(), () => this._runFlush());
        await this.chain;
    }

    dispose() {
        this.disposed = true;
        if (this.timer !== null) clearTimeout(this.timer);
        this.timer = null;
        this.chain = this.chain.then(() => undefined, () => undefined);
    }
}
