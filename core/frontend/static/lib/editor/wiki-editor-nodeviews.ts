/**
 * NodeView для блоков wiki-редактора: toggle, task_item, code_block, platform_file.
 *
 * Сворачивание toggle живёт только в DOM — в схему его не пишем: состояние
 * просмотра не часть документа. Блок кода рисует CodeMirror 6 из уже
 * собранного бандла платформы.
 */

import { isPlainRecord } from '../events/payload.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { resolvePlatformFilesApiBase } from '../utils/platform-files-url.js';
import type { CmCompartmentLike, CmEditorViewLike, CmModule } from '../codemirror/variable-extensions.js';
import type { PmNodeLike, PmViewLike } from './pm-types.js';
import { attrString } from './wiki-schema-builder.js';
import '../components/platform-icon.js';

/** Base path `/{segment}/api/v1/files/download/` для текущего SPA. */
export function resolveDefaultFileUrlBase(): string {
    return `${resolvePlatformFilesApiBase()}/download/`;
}

export const CODE_BLOCK_LANGUAGES = Object.freeze([
    { id: '', label: 'plain' },
    { id: 'python', label: 'python' },
    { id: 'javascript', label: 'javascript' },
    { id: 'json', label: 'json' },
    { id: 'go', label: 'go' },
    { id: 'csharp', label: 'csharp' },
]);

let _cmBundlePromise: Promise<CmModule> | null = null;

function isOfMethod(value: unknown): boolean {
    return isPlainRecord(value) && typeof value.of === 'function';
}

function isCmModule(value: unknown): value is CmModule {
    if (!isPlainRecord(value)) return false;
    const editorState = value.EditorState;
    if (typeof editorState !== 'function' || !('create' in editorState) || typeof editorState.create !== 'function') return false;
    if (!('readOnly' in editorState) || !isOfMethod(editorState.readOnly)) return false;
    if (typeof value.EditorView !== 'function') return false;
    if (!('theme' in value.EditorView) || typeof value.EditorView.theme !== 'function') return false;
    if (!('updateListener' in value.EditorView) || !isOfMethod(value.EditorView.updateListener)) return false;
    if (!('lineWrapping' in value.EditorView)) return false;
    if (typeof value.Compartment !== 'function' || typeof value.json !== 'function') return false;
    if (typeof value.history !== 'function' || typeof value.syntaxHighlighting !== 'function') return false;
    if (!isPlainRecord(value.keymap) || typeof value.keymap.of !== 'function') return false;
    if (!Array.isArray(value.defaultKeymap) || !Array.isArray(value.historyKeymap)) return false;
    return 'defaultHighlightStyle' in value;
}

export function loadCodeMirrorBundle(): Promise<CmModule> {
    if (_cmBundlePromise === null) {
        _cmBundlePromise = import('../codemirror/codemirror-lazy.js').then((mod: unknown) => {
            if (!isCmModule(mod)) {
                throw new Error('wiki-editor-nodeviews: codemirror bundle is not CmModule');
            }
            return mod;
        });
    }
    return _cmBundlePromise;
}

function languageExtension(cm: CmModule, language: string): unknown {
    if (language === 'python') return cm.python?.();
    if (language === 'javascript') return cm.javascript?.();
    if (language === 'json') return cm.json();
    if (language === 'go') return cm.go?.();
    if (language === 'csharp') return cm.csharp?.();
    return [];
}

function fileHref(fileUrlBase: string, fileId: string): string {
    if (typeof fileUrlBase !== 'string' || fileUrlBase.length === 0) {
        throw new Error('wiki-editor-nodeviews: fileUrlBase required');
    }
    if (typeof fileId !== 'string' || fileId.length === 0) {
        throw new Error('wiki-editor-nodeviews: file_id required');
    }
    return fileUrlBase.endsWith('/') ? `${fileUrlBase}${fileId}` : `${fileUrlBase}/${fileId}`;
}

export interface WikiNodeViewsOptions {
    cm: CmModule | null;
    getFileUrlBase: () => string;
    isEditable: () => boolean;
    onOpenFile?: (fileId: string) => void;
}

type GetPos = () => number | undefined;

type NodeViewFactory = (node: PmNodeLike, view: PmViewLike, getPos: GetPos) => object;

export function buildWikiNodeViews(options: WikiNodeViewsOptions): Record<string, NodeViewFactory> {
    if (!options || typeof options !== 'object') {
        throw new Error('buildWikiNodeViews: options required');
    }
    if (typeof options.getFileUrlBase !== 'function') {
        throw new Error('buildWikiNodeViews: getFileUrlBase required');
    }
    if (typeof options.isEditable !== 'function') {
        throw new Error('buildWikiNodeViews: isEditable required');
    }
    return {
        toggle: (node: PmNodeLike, view: PmViewLike, getPos: GetPos) => new ToggleNodeView(node, view, getPos),
        task_item: (node, view, getPos) => new TaskItemNodeView(node, view, getPos, options),
        code_block: (node, view, getPos) => new CodeBlockNodeView(node, view, getPos, options),
        platform_file: (node, view, getPos) => new PlatformFileNodeView(node, view, getPos, options),
    };
}

class ToggleNodeView {
    node: PmNodeLike;
    view: PmViewLike;
    getPos: GetPos;
    collapsed: boolean;
    dom: HTMLElement;
    chevron: HTMLButtonElement;
    contentDOM: HTMLElement;

    constructor(node: PmNodeLike, view: PmViewLike, getPos: GetPos) {
        this.node = node;
        this.view = view;
        this.getPos = getPos;
        this.collapsed = false;

        this.dom = document.createElement('div');
        this.dom.className = 'pm-toggle';
        this.dom.dataset.toggle = 'true';

        this.chevron = document.createElement('button');
        this.chevron.type = 'button';
        this.chevron.className = 'pm-toggle-chevron';
        this.chevron.setAttribute('aria-expanded', 'true');
        this.chevron.addEventListener('mousedown', (event) => event.preventDefault());
        this.chevron.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._setCollapsed(!this.collapsed);
        });

        this.contentDOM = document.createElement('div');
        this.contentDOM.className = 'pm-toggle-body';

        this.dom.append(this.chevron, this.contentDOM);
        this._setCollapsed(false);
    }

    _setCollapsed(collapsed: boolean): void {
        this.collapsed = collapsed;
        this.dom.classList.toggle('is-collapsed', collapsed);
        this.chevron.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    update(node: PmNodeLike): boolean {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        return true;
    }

    stopEvent(event: Event): boolean {
        return event.target instanceof Node && this.chevron.contains(event.target);
    }

    ignoreMutation() {
        return true;
    }
}

class TaskItemNodeView {
    node: PmNodeLike;
    view: PmViewLike;
    getPos: GetPos;
    options: WikiNodeViewsOptions;
    dom: HTMLElement;
    checkbox: HTMLInputElement;
    contentDOM: HTMLElement;

    constructor(node: PmNodeLike, view: PmViewLike, getPos: GetPos, options: WikiNodeViewsOptions) {
        this.node = node;
        this.view = view;
        this.getPos = getPos;
        this.options = options;

        this.dom = document.createElement('li');
        this.dom.className = 'pm-task-item';
        this.dom.dataset.taskItem = 'true';

        this.checkbox = document.createElement('input');
        this.checkbox.type = 'checkbox';
        this.checkbox.className = 'pm-task-checkbox';
        this.checkbox.contentEditable = 'false';
        this.checkbox.checked = Boolean(node.attrs.checked);
        this.checkbox.disabled = !options.isEditable();
        this.checkbox.addEventListener('mousedown', (event) => {
            // mousedown, не click: иначе ProseMirror успевает перехватить жест,
            // а preventDefault на click ещё и гасит смену checked в DOM.
            event.preventDefault();
            event.stopPropagation();
            if (!this.options.isEditable()) {
                return;
            }
            const pos = this.getPos();
            if (typeof pos !== 'number') {
                throw new Error('TaskItemNodeView: getPos returned no position');
            }
            this.view.dispatch(
                this.view.state.tr.setNodeMarkup(pos, undefined, {
                    checked: !this.node.attrs.checked,
                }),
            );

        });

        this.contentDOM = document.createElement('div');
        this.contentDOM.className = 'pm-task-content';

        this.dom.append(this.checkbox, this.contentDOM);
        this._syncChecked();
    }

    _syncChecked(): void {
        const checked = Boolean(this.node.attrs.checked);
        this.checkbox.checked = checked;
        this.dom.dataset.checked = checked ? 'true' : 'false';
        this.checkbox.disabled = !this.options.isEditable();
    }

    update(node: PmNodeLike): boolean {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this._syncChecked();
        return true;
    }

    stopEvent(event: Event): boolean {
        return event.target instanceof Node && this.checkbox.contains(event.target);
    }

    ignoreMutation(mutation: MutationRecord): boolean {
        return mutation.type === 'attributes' && mutation.target === this.checkbox;
    }
}

class CodeBlockNodeView {
    node: PmNodeLike;
    view: PmViewLike;
    getPos: GetPos;
    options: WikiNodeViewsOptions;
    updating: boolean;
    destroyed: boolean;
    cm: CmEditorViewLike | null;
    _cmModule: CmModule | null;
    languageCompartment: CmCompartmentLike | null;
    readonlyCompartment: CmCompartmentLike | null;
    dom: HTMLElement;
    toolbar: HTMLElement;
    select: HTMLSelectElement;
    cmHost: HTMLElement;

    constructor(node: PmNodeLike, view: PmViewLike, getPos: GetPos, options: WikiNodeViewsOptions) {
        this.node = node;
        this.view = view;
        this.getPos = getPos;
        this.options = options;
        this.updating = false;
        this.destroyed = false;
        this.cm = null;
        this._cmModule = null;
        this.languageCompartment = null;
        this.readonlyCompartment = null;

        this.dom = document.createElement('div');
        this.dom.className = 'pm-code-block';
        this.dom.dataset.language = attrString(node.attrs.language);

        this.toolbar = document.createElement('div');
        this.toolbar.className = 'pm-code-block-toolbar';

        this.select = document.createElement('select');
        this.select.className = 'pm-code-block-lang';
        this.select.setAttribute('aria-label', 'language');
        for (const language of CODE_BLOCK_LANGUAGES) {
            const option = document.createElement('option');
            option.value = language.id;
            option.textContent = language.label;
            this.select.appendChild(option);
        }
        this.select.value = attrString(node.attrs.language);
        this.select.disabled = !options.isEditable();
        this.select.addEventListener('mousedown', (event) => event.stopPropagation());
        this.select.addEventListener('change', (event) => {
            event.stopPropagation();
            event.stopImmediatePropagation();
            if (!this.options.isEditable()) {
                return;
            }
            const pos = this.getPos();
            if (typeof pos !== 'number') {
                throw new Error('CodeBlockNodeView: getPos returned no position');
            }
            this.view.dispatch(
                this.view.state.tr.setNodeMarkup(pos, undefined, {
                    ...this.node.attrs,
                    language: this.select.value,
                }),
            );
            this._reconfigureLanguage(this.select.value);
        });

        this.cmHost = document.createElement('div');
        this.cmHost.className = 'pm-code-block-cm';

        this.toolbar.appendChild(this.select);
        this.dom.append(this.toolbar, this.cmHost);

        void this._mountCodeMirror();
    }

    async _mountCodeMirror(): Promise<void> {
        // NodeView ещё не в дереве, пока конструктор не вернётся в ProseMirror.
        // Без паузы getRootNode() не ShadowRoot страницы — стили oneDark уезжают
        // в document и подсветка внутри wiki-page-view невидима.
        await Promise.resolve();
        if (!this.dom.isConnected) {
            await new Promise<void>((resolve) => {
                requestAnimationFrame(() => resolve());
            });
        }
        if (this.destroyed || this.cm !== null) {
            return;
        }
        const cm = this.options.cm || (await loadCodeMirrorBundle());
        if (this.cm !== null || this.destroyed) {
            return;
        }
        this.languageCompartment = new cm.Compartment();
        this.readonlyCompartment = new cm.Compartment();
        const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
        // oneDark уже несёт подсветку для тёмной темы; defaultHighlightStyle — только light.
        const themeExtensions = isDark
            ? [cm.oneDark]
            : [cm.syntaxHighlighting(cm.defaultHighlightStyle, { fallback: true })];
        const styleRoot = this.cmHost.getRootNode();
        const viewRoot = styleRoot instanceof ShadowRoot ? styleRoot : undefined;

        this.cm = new cm.EditorView({
            doc: this.node.textContent,
            extensions: [
                cm.keymap.of([...cm.defaultKeymap, ...cm.historyKeymap]),
                cm.history(),
                cm.EditorView.lineWrapping,
                this.languageCompartment.of(languageExtension(cm, attrString(this.node.attrs.language))),
                this.readonlyCompartment.of(cm.EditorState.readOnly.of(!this.options.isEditable())),
                ...themeExtensions,
                cm.EditorView.updateListener.of((update) => {
                    if (!update.docChanged || this.updating) {
                        return;
                    }
                    this._forwardToProseMirror();
                }),
            ],
            parent: this.cmHost,
            root: viewRoot,
        });
        this._cmModule = cm;
        const connectedRoot = this.cmHost.getRootNode();
        if (connectedRoot instanceof ShadowRoot && this.cm.root !== connectedRoot) {
            this.cm.setRoot(connectedRoot);
        }
    }

    _reconfigureLanguage(language: string): void {
        if (this.cm === null || this.languageCompartment === null || this._cmModule === null) {
            return;
        }
        this.cm.dispatch({
            effects: this.languageCompartment.reconfigure(
                languageExtension(this._cmModule, language),
            ),
        });
        this.dom.dataset.language = language;
    }

    _forwardToProseMirror(): void {
        const pos = this.getPos();
        if (typeof pos !== 'number') {
            throw new Error('CodeBlockNodeView: getPos returned no position');
        }
        const start = pos + 1;
        const end = start + this.node.nodeSize - 2;
        const text = this.cm ? this.cm.state.doc.toString() : '';
        if (this.view.state.doc.textBetween(start, end) === text) {
            return;
        }
        const content: unknown = text === '' ? [] : this.view.state.schema.text(text);
        this.updating = true;
        this.view.dispatch(this.view.state.tr.replaceWith(start, end, content));
        this.updating = false;
    }

    update(node: PmNodeLike): boolean {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this.select.value = attrString(node.attrs.language);
        this.select.disabled = !this.options.isEditable();
        this.dom.dataset.language = attrString(node.attrs.language);

        if (this.cm !== null && this.readonlyCompartment !== null && this._cmModule !== null) {
            this.cm.dispatch({
                effects: this.readonlyCompartment.reconfigure(
                    this._cmModule.EditorState.readOnly.of(!this.options.isEditable()),
                ),
            });
            this._reconfigureLanguage(attrString(node.attrs.language));
            const text = node.textContent;
            if (this.cm.state.doc.toString() !== text) {
                this.updating = true;
                this.cm.dispatch({
                    changes: { from: 0, to: this.cm.state.doc.length, insert: text },
                });
                this.updating = false;
            }
        }
        return true;
    }

    selectNode(): void {
        this.dom.classList.add('ProseMirror-selectednode');
    }

    deselectNode(): void {
        this.dom.classList.remove('ProseMirror-selectednode');
    }

    stopEvent(): boolean {
        return true;
    }

    ignoreMutation(): boolean {
        return true;
    }

    destroy(): void {
        this.destroyed = true;
        if (this.cm !== null) {
            this.cm.destroy();
            this.cm = null;
        }
    }
}

class PlatformFileNodeView {
    node: PmNodeLike;
    view: PmViewLike;
    getPos: GetPos;
    options: WikiNodeViewsOptions;
    dom: HTMLElement;
    _icon: HTMLElement;
    _meta: HTMLElement;
    _name: HTMLElement;
    _onActivate: (event: Event) => void;

    constructor(node: PmNodeLike, view: PmViewLike, getPos: GetPos, options: WikiNodeViewsOptions) {
        this.node = node;
        this.view = view;
        this.getPos = getPos;
        this.options = options;

        this.dom = document.createElement('div');
        this.dom.className = 'pm-file-attachment';
        this.dom.dataset.platformFile = 'true';
        this.dom.setAttribute('role', 'button');
        this.dom.tabIndex = 0;

        this._icon = document.createElement('platform-icon');
        this._icon.setAttribute('file-icon', '');
        this._icon.setAttribute('size', '20');

        this._meta = document.createElement('span');
        this._meta.className = 'pm-file-attachment-meta';

        this._name = document.createElement('span');
        this._name.className = 'pm-file-attachment-name';

        this._meta.appendChild(this._name);
        this.dom.appendChild(this._icon);
        this.dom.appendChild(this._meta);

        this._onActivate = (event: Event) => {
            event.preventDefault();
            this._open();
        };
        this.dom.addEventListener('click', this._onActivate);
        this.dom.addEventListener('keydown', (event: Event) => {
            if (!(event instanceof KeyboardEvent)) {
                return;
            }
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                this._open();
            }
        });

        this._sync();
    }

    _open(): void {
        const fileId = attrString(this.node.attrs.file_id);
        if (typeof this.options.onOpenFile === 'function') {
            this.options.onOpenFile(fileId);
            return;
        }
        window.location.assign(fileHref(this.options.getFileUrlBase(), fileId));
    }

    _sync(): void {
        const fileId = attrString(this.node.attrs.file_id);
        const name = String(this.node.attrs.original_name || fileId);
        const contentType = attrString(this.node.attrs.content_type);
        this.dom.dataset.fileId = fileId;
        this.dom.dataset.name = attrString(this.node.attrs.original_name);
        this.dom.dataset.contentType = contentType;
        this.dom.setAttribute('aria-label', name);
        this._name.textContent = name;
        this._icon.setAttribute('name', resolveFileIconKey(name, contentType));
    }

    update(node: PmNodeLike): boolean {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this._sync();
        return true;
    }

    stopEvent(event: Event): boolean {
        return event.type === 'mousedown' || event.type === 'click' || event.type === 'keydown';
    }

    ignoreMutation(): boolean {
        return true;
    }

    destroy(): void {
        this.dom.removeEventListener('click', this._onActivate);
    }
}
