/**
 * NodeView для блоков wiki-редактора: toggle, task_item, code_block, platform_file.
 *
 * Сворачивание toggle живёт только в DOM — в схему его не пишем: состояние
 * просмотра не часть документа. Блок кода рисует CodeMirror 6 из уже
 * собранного бандла платформы.
 */

export const CODEMIRROR_BUNDLE_URL = '/static/core/assets/codemirror/codemirror-bundle.js';

export const DEFAULT_FILE_URL_BASE = '/frontend/api/v1/files/download/';

export const CODE_BLOCK_LANGUAGES = Object.freeze([
    { id: '', label: 'plain' },
    { id: 'python', label: 'python' },
    { id: 'javascript', label: 'javascript' },
    { id: 'json', label: 'json' },
    { id: 'go', label: 'go' },
    { id: 'csharp', label: 'csharp' },
]);

let _cmBundlePromise = null;

export function loadCodeMirrorBundle() {
    if (_cmBundlePromise === null) {
        _cmBundlePromise = import(CODEMIRROR_BUNDLE_URL);
    }
    return _cmBundlePromise;
}

function languageExtension(cm, language) {
    if (language === 'python') return cm.python();
    if (language === 'javascript') return cm.javascript();
    if (language === 'json') return cm.json();
    if (language === 'go') return cm.go();
    if (language === 'csharp') return cm.csharp();
    return [];
}

function fileHref(fileUrlBase, fileId) {
    if (typeof fileUrlBase !== 'string' || fileUrlBase.length === 0) {
        throw new Error('wiki-editor-nodeviews: fileUrlBase required');
    }
    if (typeof fileId !== 'string' || fileId.length === 0) {
        throw new Error('wiki-editor-nodeviews: file_id required');
    }
    return fileUrlBase.endsWith('/') ? `${fileUrlBase}${fileId}` : `${fileUrlBase}/${fileId}`;
}

/**
 * @param {{
 *   cm: object | null,
 *   getFileUrlBase: () => string,
 *   isEditable: () => boolean,
 * }} options
 */
export function buildWikiNodeViews(options) {
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
        toggle: (node, view, getPos) => new ToggleNodeView(node, view, getPos),
        task_item: (node, view, getPos) => new TaskItemNodeView(node, view, getPos, options),
        code_block: (node, view, getPos) => new CodeBlockNodeView(node, view, getPos, options),
        platform_file: (node, view, getPos) => new PlatformFileNodeView(node, view, getPos, options),
    };
}

class ToggleNodeView {
    constructor(node, view, getPos) {
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

    _setCollapsed(collapsed) {
        this.collapsed = collapsed;
        this.dom.classList.toggle('is-collapsed', collapsed);
        this.chevron.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    update(node) {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        return true;
    }

    stopEvent(event) {
        return this.chevron.contains(event.target);
    }

    ignoreMutation() {
        return true;
    }
}

class TaskItemNodeView {
    constructor(node, view, getPos, options) {
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

    _syncChecked() {
        const checked = Boolean(this.node.attrs.checked);
        this.checkbox.checked = checked;
        this.dom.dataset.checked = checked ? 'true' : 'false';
        this.checkbox.disabled = !this.options.isEditable();
    }

    update(node) {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this._syncChecked();
        return true;
    }

    stopEvent(event) {
        return this.checkbox.contains(event.target);
    }

    ignoreMutation(mutation) {
        return mutation.type === 'attributes' && mutation.target === this.checkbox;
    }
}

class CodeBlockNodeView {
    constructor(node, view, getPos, options) {
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
        this.dom.dataset.language = node.attrs.language || '';

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
        this.select.value = node.attrs.language || '';
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

    async _mountCodeMirror() {
        // NodeView ещё не в дереве, пока конструктор не вернётся в ProseMirror.
        // Без паузы getRootNode() не ShadowRoot страницы — стили oneDark уезжают
        // в document и подсветка внутри wiki-page-view невидима.
        await Promise.resolve();
        if (!this.dom.isConnected) {
            await new Promise((resolve) => {
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
                this.languageCompartment.of(languageExtension(cm, this.node.attrs.language || '')),
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

    _reconfigureLanguage(language) {
        if (this.cm === null || this.languageCompartment === null || this._cmModule === null) {
            return;
        }
        this.cm.dispatch({
            effects: this.languageCompartment.reconfigure(
                languageExtension(this._cmModule, language || ''),
            ),
        });
        this.dom.dataset.language = language || '';
    }

    _forwardToProseMirror() {
        const pos = this.getPos();
        if (typeof pos !== 'number') {
            throw new Error('CodeBlockNodeView: getPos returned no position');
        }
        const start = pos + 1;
        const end = start + this.node.nodeSize - 2;
        const text = this.cm.state.doc.toString();
        if (this.view.state.doc.textBetween(start, end) === text) {
            return;
        }
        const content = text === '' ? [] : this.view.state.schema.text(text);
        this.updating = true;
        this.view.dispatch(this.view.state.tr.replaceWith(start, end, content));
        this.updating = false;
    }

    update(node) {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this.select.value = node.attrs.language || '';
        this.select.disabled = !this.options.isEditable();
        this.dom.dataset.language = node.attrs.language || '';

        if (this.cm !== null && this.readonlyCompartment !== null && this._cmModule !== null) {
            this.cm.dispatch({
                effects: this.readonlyCompartment.reconfigure(
                    this._cmModule.EditorState.readOnly.of(!this.options.isEditable()),
                ),
            });
            this._reconfigureLanguage(node.attrs.language || '');
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

    selectNode() {
        this.dom.classList.add('ProseMirror-selectednode');
    }

    deselectNode() {
        this.dom.classList.remove('ProseMirror-selectednode');
    }

    stopEvent() {
        return true;
    }

    ignoreMutation() {
        return true;
    }

    destroy() {
        this.destroyed = true;
        if (this.cm !== null) {
            this.cm.destroy();
            this.cm = null;
        }
    }
}

class PlatformFileNodeView {
    constructor(node, view, getPos, options) {
        this.node = node;
        this.view = view;
        this.getPos = getPos;
        this.options = options;

        this.dom = document.createElement('a');
        this.dom.className = 'pm-file-chip';
        this.dom.dataset.platformFile = 'true';
        this.dom.rel = 'noopener noreferrer';
        this._sync();
    }

    _sync() {
        const fileId = this.node.attrs.file_id;
        const name = this.node.attrs.original_name || fileId;
        this.dom.dataset.fileId = fileId;
        this.dom.dataset.name = this.node.attrs.original_name || '';
        this.dom.dataset.contentType = this.node.attrs.content_type || '';
        this.dom.href = fileHref(this.options.getFileUrlBase(), fileId);
        this.dom.textContent = name;
        this.dom.download = name;
    }

    update(node) {
        if (node.type !== this.node.type) {
            return false;
        }
        this.node = node;
        this._sync();
        return true;
    }

    stopEvent(event) {
        return event.type === 'mousedown' || event.type === 'click';
    }

    ignoreMutation() {
        return true;
    }
}
