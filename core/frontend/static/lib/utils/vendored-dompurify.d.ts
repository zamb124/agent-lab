/** Vendored DOMPurify (minified ESM) — используется mail-html.ts. */
declare module '*/assets/js/dompurify/purify.es.mjs' {
    const DOMPurify: {
        sanitize(html: string, options?: Record<string, unknown>): string;
        addHook(name: string, cb: (node: Node) => void): void;
        removeHook(name: string): void;
    };
    export default DOMPurify;
}
