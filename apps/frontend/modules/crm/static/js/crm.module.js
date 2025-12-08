/**
 * CRM Module - Networkle
 * Основной JavaScript модуль для CRM функциональности
 */

export default class CRMModule {
    constructor(app) {
        this.app = app;
        this.name = 'crm';
        this.version = '1.0.0';
        this.apiBase = '/crm/api/v1';
        this.graph = null;
        this.pendingFiles = [];
    }
    
    async init() {
        console.log('CRM Module initialized');
        this.setupMarked();
        this.setupEventListeners();
        this.setupNotificationHandlers();
        this.initToggleGroups();
        
        // Initial render for existing content
        this.renderMarkdownContent(document);
        
        // Re-init toggle groups after HTMX content load
        document.body.addEventListener('htmx:afterSettle', () => {
            this.initToggleGroups();
        });
        
        // Глобальные объекты для обратной совместимости с HTML
        this._setupGlobalObjects();
        
        return this;
    }
    
    _setupGlobalObjects() {
        window.crmModule = this;
        window.CRM = this._createGlobalAPI();
    }
    
    setupNotificationHandlers() {
        // Listen to HTMX WebSocket messages (connection managed by base.html)
        document.body.addEventListener('htmx:wsAfterMessage', (event) => {
            try {
                const data = JSON.parse(event.detail.message);
                this.handleNotification(data);
            } catch (e) {
                // Not a JSON message, ignore
            }
        });
    }
    
    handleNotification(data) {
        if (data.type === 'access_request') {
            // Trigger HTMX event to reload access requests badge
            htmx.trigger(document.body, 'accessRequestUpdated');
            
            // Show notification
            this.showNotification(data.message || 'New access request', 'info');
        } else if (data.type === 'task_assigned') {
            htmx.trigger(document.body, 'taskUpdated');
            this.showNotification(data.message || 'Task assigned to you', 'info');
        }
    }
    
    setupMarked() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false
            });
        }
    }
    
    setupEventListeners() {
        // HTMX события
        document.body.addEventListener('htmx:afterSwap', (e) => {
            this.onContentSwap(e);
        });
        
        // Закрытие модалки по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
        
        // Закрытие модалки по клику на overlay
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) {
                this.closeModal();
            }
        });
    }
    
    onContentSwap(event) {
        const target = event.detail.target;
        
        // Инициализация графа если загружена страница графа
        if (target.querySelector('.crm-graph-container')) {
            this.initGraph();
        }
        
        // Инициализация редактора заметок
        if (target.querySelector('.crm-note-textarea')) {
            this.initNoteEditor();
        }
        
        // Инициализация dropzone
        if (target.querySelector('.crm-dropzone')) {
            this.initDropzone();
        }
        
        // Рендеринг markdown контента
        this.renderMarkdownContent(target);
    }
    
    renderMarkdownContent(container) {
        if (typeof marked === 'undefined') return;
        
        const markdownElements = container.querySelectorAll('[data-markdown]');
        markdownElements.forEach(el => {
            const rawContent = el.getAttribute('data-markdown');
            if (rawContent) {
                el.innerHTML = marked.parse(rawContent);
            }
        });
    }
    
    // === API Methods ===
    
    async apiRequest(endpoint, options = {}) {
        const url = `${this.apiBase}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        try {
            const response = await fetch(url, { ...defaultOptions, ...options });
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('CRM API error:', error);
            this.showNotification('Ошибка при выполнении запроса', 'error');
            throw error;
        }
    }
    
    // === Notes ===
    
    initNoteEditor() {
        const textarea = document.querySelector('.crm-note-textarea');
        if (!textarea) return;
        
        // Auto-resize
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        });
        
        // Markdown preview tabs
        this.initMarkdownTabs();
        
        // @mention autocomplete
        this.initMentionAutocomplete(textarea);
    }
    
    // === @Mention Autocomplete ===
    
    initMentionAutocomplete(textarea) {
        this.mentionState = {
            active: false,
            startPos: 0,
            query: '',
            selectedIndex: 0,
            results: []
        };
        
        // Создаём dropdown контейнер
        let dropdown = document.getElementById('mention-dropdown');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.id = 'mention-dropdown';
            dropdown.className = 'crm-mention-dropdown';
            dropdown.style.display = 'none';
            textarea.parentNode.style.position = 'relative';
            textarea.parentNode.appendChild(dropdown);
        }
        this.mentionDropdown = dropdown;
        
        // Обработчик ввода
        textarea.addEventListener('input', (e) => this.handleMentionInput(e));
        textarea.addEventListener('keydown', (e) => this.handleMentionKeydown(e));
        textarea.addEventListener('blur', () => {
            setTimeout(() => this.hideMentionDropdown(), 200);
        });
        
        // Клик по элементу dropdown
        dropdown.addEventListener('click', (e) => {
            const item = e.target.closest('.crm-mention-item');
            if (item) {
                const index = parseInt(item.dataset.index);
                this.selectMention(index);
            }
        });
    }
    
    handleMentionInput(e) {
        const textarea = e.target;
        const value = textarea.value;
        const cursorPos = textarea.selectionStart;
        
        // Ищем @ перед курсором
        const textBeforeCursor = value.substring(0, cursorPos);
        const atMatch = textBeforeCursor.match(/@([^\s@]*)$/);
        
        if (atMatch) {
            this.mentionState.active = true;
            this.mentionState.startPos = cursorPos - atMatch[0].length;
            this.mentionState.query = atMatch[1];
            this.searchMentions(atMatch[1]);
        } else {
            this.hideMentionDropdown();
        }
    }
    
    handleMentionKeydown(e) {
        if (!this.mentionState.active || !this.mentionState.results.length) return;
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.mentionState.selectedIndex = 
                    (this.mentionState.selectedIndex + 1) % this.mentionState.results.length;
                this.renderMentionDropdown();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.mentionState.selectedIndex = 
                    (this.mentionState.selectedIndex - 1 + this.mentionState.results.length) % this.mentionState.results.length;
                this.renderMentionDropdown();
                break;
            case 'Enter':
            case 'Tab':
                if (this.mentionState.active && this.mentionState.results.length) {
                    e.preventDefault();
                    this.selectMention(this.mentionState.selectedIndex);
                }
                break;
            case 'Escape':
                this.hideMentionDropdown();
                break;
        }
    }
    
    async searchMentions(query) {
        if (query.length < 1) {
            this.mentionState.results = [];
            this.hideMentionDropdown();
            return;
        }
        
        try {
            const results = await this.apiRequest(`/entities/autocomplete?q=${encodeURIComponent(query)}&limit=8`);
            this.mentionState.results = results;
            this.mentionState.selectedIndex = 0;
            
            if (results.length > 0) {
                this.renderMentionDropdown();
            } else {
                this.hideMentionDropdown();
            }
        } catch (error) {
            console.error('Mention search error:', error);
            this.hideMentionDropdown();
        }
    }
    
    renderMentionDropdown() {
        const { results, selectedIndex } = this.mentionState;
        
        if (!results.length) {
            this.hideMentionDropdown();
            return;
        }
        
        const typeIcons = {
            person: 'ti-user',
            company: 'ti-building',
            project: 'ti-folder'
        };
        
        const typeColors = {
            person: 'var(--crm-blue)',
            company: 'var(--crm-purple)',
            project: 'var(--crm-green)'
        };
        
        this.mentionDropdown.innerHTML = results.map((entity, index) => `
            <div class="crm-mention-item ${index === selectedIndex ? 'selected' : ''}" 
                 data-index="${index}"
                 data-id="${entity.entity_id || entity.id}">
                <div class="crm-mention-icon" style="color: ${typeColors[entity.type] || 'var(--crm-teal)'}">
                    <i class="ti ${typeIcons[entity.type] || 'ti-tag'}"></i>
                </div>
                <div class="crm-mention-info">
                    <div class="crm-mention-name">${this.escapeHtml(entity.name)}</div>
                    <div class="crm-mention-type">${entity.type}</div>
                </div>
            </div>
        `).join('');
        
        this.mentionDropdown.style.display = 'block';
    }
    
    selectMention(index) {
        const entity = this.mentionState.results[index];
        if (!entity) return;
        
        const textarea = document.querySelector('.crm-note-textarea');
        if (!textarea) return;
        
        const value = textarea.value;
        const beforeMention = value.substring(0, this.mentionState.startPos);
        const afterMention = value.substring(textarea.selectionStart);
        
        // Вставляем ссылку на сущность: [@Name](entity:id)
        const mentionText = `[@${entity.name}](entity:${entity.entity_id || entity.id})`;
        
        textarea.value = beforeMention + mentionText + afterMention;
        
        // Перемещаем курсор после вставки
        const newPos = beforeMention.length + mentionText.length;
        textarea.setSelectionRange(newPos, newPos);
        textarea.focus();
        
        this.hideMentionDropdown();
        this.showNotification(`Добавлена ссылка на ${entity.name}`, 'success');
    }
    
    hideMentionDropdown() {
        this.mentionState.active = false;
        this.mentionState.results = [];
        if (this.mentionDropdown) {
            this.mentionDropdown.style.display = 'none';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    initMarkdownTabs() {
        const tabs = document.querySelectorAll('.crm-markdown-tab');
        const editor = document.getElementById('note-content-editor');
        const preview = document.getElementById('note-content-preview');
        
        if (!tabs.length || !editor || !preview) return;
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const mode = tab.getAttribute('data-tab');
                
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                if (mode === 'edit') {
                    editor.style.display = 'block';
                    preview.style.display = 'none';
                } else {
                    editor.style.display = 'none';
                    preview.style.display = 'block';
                    
                    if (typeof marked !== 'undefined') {
                        preview.innerHTML = marked.parse(editor.value || '');
                    } else {
                        preview.textContent = editor.value || '';
                    }
                }
            });
        });
    }
    
    // === File Dropzone ===
    
    initDropzone() {
        const dropzone = document.getElementById('note-dropzone');
        const fileInput = document.getElementById('file-input');
        
        if (!dropzone || !fileInput) return;
        
        // Click to select files
        dropzone.addEventListener('click', () => fileInput.click());
        
        // File input change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadFiles(e.target.files);
            }
        });
        
        // Drag and drop events
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        
        dropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            
            if (e.dataTransfer.files.length > 0) {
                this.uploadFiles(e.dataTransfer.files);
            }
        });
    }
    
    async uploadFiles(files) {
        // Get noteId from multiple sources
        const noteInput = document.querySelector('.crm-note-input');
        const noteId = noteInput?.dataset.noteId || 
                       document.querySelector('[data-note-id]')?.dataset.noteId ||
                       window.location.pathname.match(/\/notes\/([^\/]+)/)?.[1];
        
        const attachmentsList = document.getElementById('attachments-list');
        const progressContainer = document.getElementById('upload-progress');
        const progressFill = progressContainer?.querySelector('.crm-progress-fill');
        const progressText = progressContainer?.querySelector('.crm-progress-text');
        
        // Если заметка еще не создана - добавляем файлы в очередь
        if (!noteId) {
            for (const file of files) {
                this.pendingFiles.push(file);
                this.renderPendingFile(file, attachmentsList);
            }
            this.showNotification('Файлы будут загружены после сохранения заметки', 'info');
            return;
        }
        
        for (const file of files) {
            // Show progress
            if (progressContainer) {
                progressContainer.style.display = 'block';
                if (progressFill) progressFill.style.width = '0%';
                if (progressText) progressText.textContent = `Загрузка ${file.name}...`;
            }
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const response = await fetch(`/crm/api/notes/${noteId}/attachments`, {
                    method: 'POST',
                    body: formData
                });
                
                if (progressFill) progressFill.style.width = '100%';
                
                if (response.ok) {
                    // Reload full attachments list
                    if (attachmentsList) {
                        const refreshUrl = attachmentsList.getAttribute('hx-get');
                        if (refreshUrl) {
                            const listResponse = await fetch(refreshUrl, { credentials: 'same-origin' });
                            attachmentsList.innerHTML = await listResponse.text();
                        } else {
                            // Fallback: insert HTML directly
                            const html = await response.text();
                        attachmentsList.insertAdjacentHTML('beforeend', html);
                        }
                    }
                    this.showNotification(`Файл ${file.name} загружен`, 'success');
                } else {
                    this.showNotification(`Ошибка загрузки ${file.name}`, 'error');
                }
            } catch (error) {
                console.error('Upload error:', error);
                this.showNotification(`Ошибка загрузки ${file.name}`, 'error');
            }
        }
        
        // Hide progress
        if (progressContainer) {
            setTimeout(() => {
                progressContainer.style.display = 'none';
            }, 1000);
        }
    }
    
    renderPendingFile(file, container) {
        if (!container) return;
        
        const fileId = `pending-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const ext = file.name.split('.').pop().toLowerCase();
        const size = this.formatFileSize(file.size);
        const color = this.getFileColor(ext);
        const displayName = file.name.length > 12 ? file.name.substring(0, 12) + '...' : file.name;
        
        const html = `
            <div class="crm-file-icon crm-file-pending" data-pending-id="${fileId}">
                <button class="crm-file-del" onclick="event.stopPropagation(); CRM.removePendingFile('${fileId}')" title="Remove">
                    <i class="ti ti-x"></i>
                </button>
                <div class="crm-file-icon-box" style="background: ${color}; opacity: 0.7;">
                    <span class="crm-file-ext">${ext.toUpperCase()}</span>
                </div>
                <span class="crm-file-name">${displayName}</span>
                <span class="crm-file-size">${size}</span>
                <span class="crm-file-status">Pending</span>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', html);
        
        file._pendingId = fileId;
    }
    
    getFileColor(ext) {
        const colors = {
            'pdf': '#dc2626', 'doc': '#2563eb', 'docx': '#2563eb',
            'txt': '#6b7280', 'png': '#10b981', 'jpg': '#10b981', 
            'jpeg': '#10b981', 'gif': '#8b5cf6', 'xls': '#16a34a',
            'xlsx': '#16a34a', 'csv': '#16a34a'
        };
        return colors[ext] || '#6b7280';
    }
    
    removePendingFile(fileId) {
        this.pendingFiles = this.pendingFiles.filter(f => f._pendingId !== fileId);
        const el = document.querySelector(`[data-pending-id="${fileId}"]`);
        if (el) el.remove();
    }
    
    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            'pdf': 'ti-file-type-pdf',
            'doc': 'ti-file-type-doc',
            'docx': 'ti-file-type-docx',
            'xls': 'ti-file-spreadsheet',
            'xlsx': 'ti-file-spreadsheet',
            'png': 'ti-photo',
            'jpg': 'ti-photo',
            'jpeg': 'ti-photo',
            'gif': 'ti-photo',
            'txt': 'ti-file-text',
            'md': 'ti-markdown'
        };
        return icons[ext] || 'ti-file';
    }
    
    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
    
    async uploadPendingFiles(noteId) {
        if (this.pendingFiles.length === 0) return;
        
        for (const file of this.pendingFiles) {
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                await fetch(`/crm/api/notes/${noteId}/attachments`, {
                    method: 'POST',
                    body: formData
                });
            } catch (error) {
                console.error('Upload pending file error:', error);
            }
            
            // Убираем pending элемент из UI
            if (file._pendingId) {
                const el = document.querySelector(`[data-pending-id="${file._pendingId}"]`);
                if (el) el.remove();
            }
        }
        
        this.pendingFiles = [];
        this.showNotification('Файлы загружены', 'success');
    }
    
    // === Voice Input ===
    
    initVoiceInput() {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            console.warn('Speech Recognition not supported');
            return;
        }
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'ru-RU';
        
        this.recognition.onresult = (event) => {
            const textarea = document.querySelector('.crm-note-textarea');
            if (!textarea) return;
            
            let interimTranscript = '';
            let finalTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }
            
            if (finalTranscript) {
                const currentPos = textarea.selectionStart;
                const textBefore = textarea.value.substring(0, currentPos);
                const textAfter = textarea.value.substring(currentPos);
                textarea.value = textBefore + finalTranscript + ' ' + textAfter;
                textarea.setSelectionRange(currentPos + finalTranscript.length + 1, currentPos + finalTranscript.length + 1);
            }
        };
        
        this.recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            this.stopVoiceInput();
        };
        
        this.recognition.onend = () => {
            this.isRecording = false;
            this.updateVoiceButton(false);
        };
    }
    
    toggleVoiceInput() {
        if (!this.recognition) {
            this.initVoiceInput();
        }
        
        if (!this.recognition) {
            this.showNotification('Голосовой ввод не поддерживается', 'error');
            return;
        }
        
        if (this.isRecording) {
            this.stopVoiceInput();
        } else {
            this.startVoiceInput();
        }
    }
    
    startVoiceInput() {
        this.recognition.start();
        this.isRecording = true;
        this.updateVoiceButton(true);
    }
    
    stopVoiceInput() {
        this.recognition.stop();
        this.isRecording = false;
        this.updateVoiceButton(false);
    }
    
    updateVoiceButton(isActive) {
        const btn = document.querySelector('[data-voice-input]');
        if (btn) {
            btn.classList.toggle('recording', isActive);
            btn.querySelector('i').className = isActive ? 'ti ti-microphone-off' : 'ti ti-microphone';
        }
    }
    
    // Note Input Component methods
    switchInputTab(formId, tab) {
        const container = document.querySelector(`[data-note-id]`)?.closest('.crm-note-input') 
            || document.querySelector('.crm-note-input');
        if (!container) return;
        
        // Update toggle buttons state (floating or inline)
        const toggle = container.querySelector('.crm-mode-toggle-floating') 
            || container.querySelector('.crm-mode-toggle');
        if (toggle) {
            toggle.dataset.active = tab;
            const btns = toggle.querySelectorAll('.crm-mode-toggle-btn');
            btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === tab));
        }
        
        const textarea = document.getElementById(`${formId}-content`);
        const preview = document.getElementById(`${formId}-preview`);
        
        if (tab === 'edit') {
            if (textarea) textarea.style.display = 'block';
            if (preview) preview.style.display = 'none';
        } else {
            if (textarea) textarea.style.display = 'none';
            if (preview) {
                preview.style.display = 'block';
                if (typeof marked !== 'undefined') {
                    preview.innerHTML = marked.parse(textarea?.value || '');
                } else {
                    preview.textContent = textarea?.value || '';
                }
            }
        }
    }
    
    initToggleGroups() {
        document.querySelectorAll('.crm-toggle-group').forEach(group => {
            // Skip if already initialized
            if (group.dataset.initialized) return;
            group.dataset.initialized = 'true';
            
            group.addEventListener('click', (e) => {
                const btn = e.target.closest('.crm-toggle-btn');
                if (!btn) return;
                
                const toggleName = group.dataset.toggle;
                const formId = group.dataset.form;
                const value = btn.dataset.value;
                
                // Update active state
                group.querySelectorAll('.crm-toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Update hidden input
                const hiddenInput = document.querySelector(`input[name="${toggleName}"][form="${formId}"]`);
                if (hiddenInput) {
                    hiddenInput.value = value;
                }
                
                // Auto-save visibility changes (skip if handled by onclick)
                if (toggleName === 'visibility' && !group.dataset.noAutoSave) {
                    const wrapper = group.closest('.crm-visibility-wrapper');
                    const popupWrapper = wrapper?.querySelector('.crm-sharing-popup-wrapper');
                    if (popupWrapper?.dataset.popupId) {
                        CRM.saveSharing(popupWrapper.dataset.popupId);
                    }
                }
            });
        });
    }
    
    triggerFileUpload(formId) {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = '.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.gif';
        input.onchange = (e) => {
            if (e.target.files.length > 0) {
                this.uploadFiles(e.target.files);
            }
        };
        input.click();
    }
    
    handleMentions(textarea) {
        const text = textarea.value;
        const cursorPos = textarea.selectionStart;
        const textBeforeCursor = text.substring(0, cursorPos);
        const mentionMatch = textBeforeCursor.match(/@([\wа-яА-ЯёЁ]*)$/i);
        
        const dropdownId = textarea.id.replace('-content', '-mentions');
        const dropdown = document.getElementById(dropdownId);
        
        // Добавляем обработчик Tab если ещё не добавлен
        if (!textarea._mentionKeyHandler) {
            textarea._mentionKeyHandler = (e) => this.handleMentionKeydown(e, textarea, dropdown);
            textarea.addEventListener('keydown', textarea._mentionKeyHandler);
        }
        
        if (mentionMatch && dropdown) {
            const query = mentionMatch[1];
            this.positionMentionsDropdown(textarea, dropdown);
            this.debouncedSearchMentions(query, dropdown, textarea);
        } else if (dropdown) {
            dropdown.style.display = 'none';
        }
    }
    
    handleMentionKeydown(e, textarea, dropdown) {
        if (!dropdown || dropdown.style.display === 'none') return;
        
        // Tab или Enter - выбрать первый элемент
        if (e.key === 'Tab' || e.key === 'Enter') {
            const firstItem = dropdown.querySelector('.crm-mentions-item');
            if (firstItem) {
                e.preventDefault();
                this.insertMention(textarea, firstItem.dataset.name, firstItem.dataset.id, dropdown);
            }
        }
        // Escape - закрыть dropdown
        if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    }
    
    debouncedSearchMentions(query, dropdown, textarea) {
        // Debounce 400ms
        if (this._mentionTimeout) {
            clearTimeout(this._mentionTimeout);
        }
        this._mentionTimeout = setTimeout(() => {
            this.searchMentions(query, dropdown, textarea);
        }, 400);
    }
    
    positionMentionsDropdown(textarea, dropdown) {
        // Создаём временный элемент для измерения позиции курсора
        const text = textarea.value.substring(0, textarea.selectionStart);
        const styles = getComputedStyle(textarea);
        
        const mirror = document.createElement('div');
        mirror.style.cssText = `
            position: absolute;
            visibility: hidden;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: ${styles.fontFamily};
            font-size: ${styles.fontSize};
            line-height: ${styles.lineHeight};
            padding: ${styles.padding};
            width: ${textarea.offsetWidth}px;
        `;
        mirror.textContent = text;
        
        const marker = document.createElement('span');
        marker.textContent = '|';
        mirror.appendChild(marker);
        
        document.body.appendChild(mirror);
        
        const markerRect = marker.getBoundingClientRect();
        const mirrorRect = mirror.getBoundingClientRect();
        
        document.body.removeChild(mirror);
        
        const top = markerRect.top - mirrorRect.top - textarea.scrollTop;
        const left = markerRect.left - mirrorRect.left;
        
        dropdown.style.top = Math.min(top + 20, textarea.offsetHeight - 100) + 'px';
        dropdown.style.left = Math.min(left, textarea.offsetWidth - 200) + 'px';
    }
    
    async searchMentions(query, dropdown, textarea) {
        if (query.length < 1) {
            dropdown.style.display = 'none';
            return;
        }
        
        try {
            const response = await fetch(`/crm/api/v1/entities/autocomplete?q=${encodeURIComponent(query)}&limit=10`);
            const entities = await response.json();
            
            if (entities && entities.length > 0) {
                dropdown.innerHTML = entities.map(e => `
                    <div class="crm-mentions-item" data-id="${e.entity_id}" data-name="${e.name}" data-type="${e.type}">
                        <i class="ti ti-${this.getEntityIcon(e.type)} crm-mentions-item-icon"></i>
                        <span class="crm-mentions-item-name">${e.name}</span>
                        <span class="crm-mentions-item-type">${e.type}</span>
                    </div>
                `).join('');
                dropdown.style.display = 'block';
                
                dropdown.querySelectorAll('.crm-mentions-item').forEach(item => {
                    item.onclick = () => this.insertMention(textarea, item.dataset.name, item.dataset.id, dropdown);
                });
            } else {
                dropdown.style.display = 'none';
            }
        } catch (e) {
            dropdown.style.display = 'none';
        }
    }
    
    insertMention(textarea, name, entityId, dropdown) {
        const text = textarea.value;
        const cursorPos = textarea.selectionStart;
        const textBeforeCursor = text.substring(0, cursorPos);
        const textAfterCursor = text.substring(cursorPos);
        const mentionStart = textBeforeCursor.lastIndexOf('@');
        
        const newText = textBeforeCursor.substring(0, mentionStart) + `@${name} ` + textAfterCursor;
        textarea.value = newText;
        textarea.focus();
        const newPos = mentionStart + name.length + 2;
        textarea.setSelectionRange(newPos, newPos);
        
        dropdown.style.display = 'none';
        
        // Сохранить entity_id в hidden input для связывания при сохранении
        this.addMentionedEntity(textarea, entityId);
        
        // Обновить подсветку
        this.highlightMentions(textarea);
    }
    
    addMentionedEntity(textarea, entityId) {
        const formId = textarea.form?.id || textarea.getAttribute('form');
        if (!formId) return;
        
        let input = document.querySelector(`input[name="mentioned_entity_ids"][form="${formId}"]`);
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'mentioned_entity_ids';
            input.setAttribute('form', formId);
            input.value = '[]';
            textarea.closest('.crm-note-input')?.appendChild(input);
        }
        
        const ids = JSON.parse(input.value || '[]');
        if (!ids.includes(entityId)) {
            ids.push(entityId);
            input.value = JSON.stringify(ids);
        }
    }
    
    highlightMentions(textarea) {
        const highlightsId = textarea.id.replace('-content', '-highlights');
        const highlights = document.getElementById(highlightsId);
        if (!highlights) return;
        
        // Заменяем @mentions на span с подсветкой
        const text = textarea.value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/@[\wа-яА-ЯёЁ]+(?:\s[\wа-яА-ЯёЁ]+)?/g, '<span class="mention">$&</span>');
        
        highlights.innerHTML = text + '\n';
    }
    
    syncHighlightsScroll(textarea) {
        const highlightsId = textarea.id.replace('-content', '-highlights');
        const highlights = document.getElementById(highlightsId);
        if (highlights) {
            highlights.scrollTop = textarea.scrollTop;
        }
    }
    
    getEntityIcon(type) {
        const icons = {
            'person': 'user',
            'organization': 'building',
            'project': 'folder',
            'task': 'checkbox',
            'meeting': 'calendar-event',
            'call': 'phone',
            'email': 'mail'
        };
        return icons[type] || 'tag';
    }
    
    async analyzeNote(noteId) {
        try {
            const result = await this.apiRequest(`/notes/${noteId}/analyze`, {
                method: 'POST'
            });
            
            // Показываем модалку с результатами AI анализа
            this.showAISuggestions(result);
            return result;
        } catch (error) {
            console.error('Error analyzing note:', error);
        }
    }
    
    showAISuggestions(analysis) {
        // Триггерим HTMX запрос для показа модалки с результатами
        htmx.ajax('GET', `/crm/partials/ai-suggestions?data=${encodeURIComponent(JSON.stringify(analysis))}`, {
            target: '#modal-container',
            swap: 'innerHTML'
        });
    }
    
    // === Knowledge Graph ===
    
    async initGraph() {
        const container = document.querySelector('.crm-graph-canvas');
        if (!container) return;
        
        // Проверяем наличие vis.js
        if (typeof vis === 'undefined') {
            console.warn('vis.js not loaded, loading...');
            await this.loadVisJs();
        }
        
        try {
            const graphData = await this.apiRequest('/graph');
            this.renderGraph(container, graphData);
        } catch (error) {
            console.error('Error loading graph:', error);
        }
    }
    
    async loadVisJs() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/crm/js/vis-network.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    renderGraph(container, data) {
        // Сохраняем данные для редактирования
        this.graphNodes = new vis.DataSet(data.nodes.map(node => ({
            id: node.id,
            label: node.name,
            color: node.color || this.getEntityColor(node.type),
            shape: 'dot',
            size: node.size || 20,
            title: this.createNodeTooltip(node),
            font: { color: '#2D3A4F', size: 12 }
        })));
        
        this.graphEdges = new vis.DataSet(data.edges.map(rel => ({
            id: rel.relationship_id,
            from: rel.source || rel.source_entity_id,
            to: rel.target || rel.target_entity_id,
            label: rel.type || rel.relationship_type,
            relationshipId: rel.relationship_id,
            arrows: 'to',
            color: { color: '#8A9AAD', opacity: 0.6 },
            font: { size: 10, color: '#8A9AAD' }
        })));
        
        const self = this;
        
        const options = {
            nodes: {
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 1,
                smooth: {
                    type: 'continuous'
                }
            },
            physics: {
                stabilization: { iterations: 100 },
                barnesHut: {
                    gravitationalConstant: -3000,
                    springLength: 150
                }
            },
            interaction: {
                hover: true,
                tooltipDelay: 200
            },
            manipulation: {
                enabled: false,
                addEdge: function(edgeData, callback) {
                    if (edgeData.from === edgeData.to) {
                        self.showNotification('Нельзя создать связь с самим собой', 'warning');
                        callback(null);
                        return;
                    }
                    self.showRelationshipTypeModal(edgeData, callback);
                }
            }
        };
        
        this.graph = new vis.Network(container, { nodes: this.graphNodes, edges: this.graphEdges }, options);
        
        // Клик на ноду - открываем детали
        this.graph.on('click', (params) => {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                this.openEntityDetail(nodeId);
            }
        });
        
        // Правый клик - контекстное меню
        this.graph.on('oncontext', (params) => {
            params.event.preventDefault();
            
            // Сначала проверяем клик на ноде - если да, игнорируем
            const nodeId = this.graph.getNodeAt(params.pointer.DOM);
            if (nodeId) {
                return; // Клик на ноде - не показываем меню связи
            }
            
            // Проверяем клик на связи
            const edgeId = this.graph.getEdgeAt(params.pointer.DOM);
            if (edgeId) {
                this.showEdgeContextMenu(params.event, edgeId);
            }
        });
    }
    
    toggleGraphEditMode() {
        if (!this.graph) return;
        
        this.graphEditMode = !this.graphEditMode;
        this.graph.setOptions({ manipulation: { enabled: this.graphEditMode } });
        
        const btn = document.querySelector('.graph-edit-btn');
        if (btn) {
            btn.classList.toggle('active', this.graphEditMode);
            btn.title = this.graphEditMode ? 'Выйти из режима редактирования' : 'Режим редактирования';
        }
        
        this.showNotification(
            this.graphEditMode ? 'Режим редактирования: протяните связь между сущностями' : 'Режим просмотра',
            'info'
        );
    }
    
    async showRelationshipTypeModal(edgeData, callback) {
        // Получаем типы связей
        let types = ['works_for', 'knows', 'related_to', 'participates_in', 'owns', 'assigned_to'];
        try {
            const response = await fetch('/crm/api/v1/relationship-types');
            if (response.ok) {
                const data = await response.json();
                if (data.length > 0) types = data;
            }
        } catch (e) {}
        
        // Создаём модалку
        const modal = document.createElement('div');
        modal.className = 'crm-graph-modal-overlay';
        modal.innerHTML = `
            <div class="crm-graph-modal">
                <div class="crm-graph-modal-header">
                    <span>Новая связь</span>
                    <button class="crm-graph-modal-close" onclick="this.closest('.crm-graph-modal-overlay').remove()">×</button>
                </div>
                <div class="crm-graph-modal-body">
                    <label>Тип связи</label>
                    <select id="relationship-type-select" class="crm-input">
                        ${types.map(t => `<option value="${t}">${t.replace(/_/g, ' ')}</option>`).join('')}
                    </select>
                </div>
                <div class="crm-graph-modal-footer">
                    <button class="crm-btn crm-btn-ghost" onclick="this.closest('.crm-graph-modal-overlay').remove()">Отмена</button>
                    <button class="crm-btn crm-btn-primary" id="create-relationship-btn">Создать</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        const createBtn = modal.querySelector('#create-relationship-btn');
        createBtn.onclick = async () => {
            const type = modal.querySelector('#relationship-type-select').value;
            
            try {
                const response = await fetch('/crm/api/v1/relationships', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_entity_id: edgeData.from,
                        target_entity_id: edgeData.to,
                        relationship_type: type,
                        weight: 1.0,
                        attributes: {}
                    })
                });
                
                if (response.ok) {
                    const rel = await response.json();
                    edgeData.label = type;
                    edgeData.relationshipId = rel.relationship_id;
                    callback(edgeData);
                    this.showNotification('Связь создана', 'success');
                } else {
                    this.showNotification('Ошибка создания связи', 'error');
                    callback(null);
                }
            } catch (e) {
                this.showNotification('Ошибка: ' + e.message, 'error');
                callback(null);
            }
            
            modal.remove();
        };
    }
    
    showEdgeContextMenu(event, edgeId) {
        // Удаляем старое меню
        document.querySelectorAll('.crm-context-menu').forEach(m => m.remove());
        
        const edge = this.graphEdges.get(edgeId);
        if (!edge) return;
        
        const menu = document.createElement('div');
        menu.className = 'crm-context-menu';
        menu.innerHTML = `
            <div class="crm-context-menu-item" data-action="delete">
                <i class="ti ti-trash"></i>
                <span>Удалить связь</span>
            </div>
        `;
        
        menu.style.left = event.clientX + 'px';
        menu.style.top = event.clientY + 'px';
        document.body.appendChild(menu);
        
        menu.querySelector('[data-action="delete"]').onclick = () => {
            this.deleteEdge(edge);
            menu.remove();
        };
        
        // Закрытие по клику вне
        setTimeout(() => {
            document.addEventListener('click', function handler() {
                menu.remove();
                document.removeEventListener('click', handler);
            });
        }, 10);
    }
    
    async deleteEdge(edge) {
        if (!edge.relationshipId) {
            this.showNotification('Невозможно удалить связь без ID', 'warning');
            return;
        }
        
        if (!confirm('Удалить эту связь?')) return;
        
        try {
            const response = await fetch(`/crm/api/v1/relationships/${edge.relationshipId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                this.graphEdges.remove(edge.id);
                this.showNotification('Связь удалена', 'success');
            } else {
                this.showNotification('Ошибка удаления', 'error');
            }
        } catch (e) {
            this.showNotification('Ошибка: ' + e.message, 'error');
        }
    }
    
    getEntityColor(type) {
        const colors = {
            person: '#5B8EC2',    // Синий
            company: '#6B5B95',   // Фиолетовый
            project: '#7BC96F'    // Зеленый
        };
        return colors[type] || '#5BA8A8'; // Бирюзовый по умолчанию
    }
    
    createNodeTooltip(node) {
        const color = node.color || this.getEntityColor(node.type);
        const typeLabels = {
            person: 'Person',
            organization: 'Organization', 
            company: 'Company',
            project: 'Project',
            meeting: 'Meeting',
            call: 'Call',
            email: 'Email',
            task: 'Task'
        };
        const typeLabel = typeLabels[node.type] || node.type;
        
        const div = document.createElement('div');
        div.style.cssText = `
            background: white;
            border-radius: 12px;
            padding: 12px 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            min-width: 180px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        `;
        div.innerHTML = `
            <div style="
                font-size: 14px;
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 8px;
                padding-bottom: 8px;
                border-bottom: 1px solid #e5e7eb;
            ">${node.name}</div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="
                        display: inline-block;
                        width: 8px;
                        height: 8px;
                        border-radius: 50%;
                        background: ${color};
                    "></span>
                    <span style="font-size: 12px; color: #6b7280;">${typeLabel}</span>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span style="color: #9ca3af;">Connections</span>
                    <span style="color: #374151; font-weight: 500;">${node.degree || 0}</span>
                </div>
                ${node.score ? `
                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                    <span style="color: #9ca3af;">Score</span>
                    <span style="color: #374151; font-weight: 500;">${node.score}</span>
                </div>
                ` : ''}
            </div>
        `;
        return div;
    }
    
    zoomGraph(direction) {
        if (!this.graph) return;
        const scale = this.graph.getScale();
        const newScale = direction === 'in' ? scale * 1.2 : scale / 1.2;
        this.graph.moveTo({ scale: newScale });
    }
    
    fitGraph() {
        if (!this.graph) return;
        this.graph.fit({ animation: true });
    }
    
    // === Entities ===
    
    openEntityDetail(entityId) {
        htmx.ajax('GET', `/crm/partials/entity/${entityId}`, {
            target: '#modal-container',
            swap: 'innerHTML'
        });
    }
    
    // === Modal ===
    
    closeModal() {
        console.log('🔴 CRM closeModal вызван, stack:', new Error().stack);
        const modal = document.querySelector('.modal-overlay');
        if (modal) {
            modal.remove();
        }
        // Разблокируем скролл body
        document.body.style.overflow = '';
        // Очищаем pending файлы при закрытии модалки
        this.pendingFiles = [];
    }
    
    // === Notifications ===
    
    showNotification(message, type = 'info') {
        // Используем глобальную систему уведомлений если есть
        if (window.app && window.app.notification) {
            window.app.notification.show(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
    
    // === AI Assistant ===
    
    askAI() {
        // Открываем чат с CRM агентом
        if (window.app && window.app.chat) {
            // CRM использует специальный flow для AI помощника
            window.app.chat.open({
                agent_id: 'crm_assistant',
                session_id: null,
                title: 'CRM AI Помощник'
            });
        } else {
            // Fallback: показываем чат виджет
            const chatWidget = document.getElementById('chat-widget');
            if (chatWidget) {
                chatWidget.classList.remove('hidden');
                chatWidget.classList.add('open');
            } else {
                this.showNotification('AI помощник временно недоступен', 'warning');
            }
        }
    }
    
    // === AI Suggestions ===
    
    toggleSuggestionEdit(button) {
        const item = button.closest('.crm-suggestion-item');
        const editForm = item.querySelector('.crm-suggestion-edit');
        const isExpanded = editForm.style.display !== 'none';
        
        editForm.style.display = isExpanded ? 'none' : 'block';
        button.classList.toggle('expanded', !isExpanded);
        item.classList.toggle('expanded', !isExpanded);
    }
    
    discardSuggestion(button) {
        const item = button.closest('.crm-suggestion-item');
        item.style.opacity = '0.5';
        item.style.pointerEvents = 'none';
        
        // Анимация удаления
        item.style.transition = 'all 0.3s ease';
        item.style.transform = 'translateX(20px)';
        
        setTimeout(() => {
            item.remove();
            this.updateSuggestionCounts();
        }, 300);
    }
    
    discardAllSuggestions() {
        const items = document.querySelectorAll('.crm-suggestion-item');
        items.forEach((item, index) => {
            setTimeout(() => {
                item.style.opacity = '0';
                item.style.transform = 'translateX(20px)';
                setTimeout(() => item.remove(), 200);
            }, index * 50);
        });
        
        setTimeout(() => {
            this.updateSuggestionCounts();
            this.showNotification('Все предложения отклонены', 'info');
        }, items.length * 50 + 200);
    }
    
    async approveAllSuggestions(noteId) {
        // Собираем все видимые (не удаленные) entities
        const entities = [];
        document.querySelectorAll('#suggestions-entities .crm-suggestion-item').forEach(item => {
            const form = item.querySelector('.crm-sug-form');
            const nameInput = form?.querySelector('input[name="name"]');
            const typeSelect = form?.querySelector('select[name="type"]');
            
            if (nameInput && typeSelect) {
                // Собираем атрибуты из формы
                const attributes = {};
                form.querySelectorAll('.crm-sug-attr-row').forEach(row => {
                    const keyInput = row.querySelector('.crm-sug-attr-key');
                    const valInput = row.querySelector('.crm-sug-attr-val');
                    if (keyInput && valInput && keyInput.value && valInput.value) {
                        attributes[keyInput.value] = valInput.value;
                    }
                });
                
                // Если форма не заполнена, берем из data-attribute
                if (Object.keys(attributes).length === 0) {
                    try {
                        Object.assign(attributes, JSON.parse(item.dataset.attributes || '{}'));
                    } catch (e) {}
                }
                
                // AI description
                const aiDescInput = form.querySelector('input[name="ai_description"]');
                const aiDescription = aiDescInput?.value || item.dataset.aiDescription || 'Сущность извлечена AI';
                
                entities.push({
                    name: nameInput.value,
                    type: typeSelect.value,
                    ai_description: aiDescription,
                    attributes: attributes
                });
            }
        });
        
        // Собираем все видимые relationships
        const relationships = [];
        document.querySelectorAll('#suggestions-relationships .crm-suggestion-item').forEach(item => {
            relationships.push({
                source: item.dataset.source,
                target: item.dataset.target,
                type: item.dataset.relType,
                weight: parseFloat(item.dataset.weight) || 1.0
            });
        });
        
        // Собираем все видимые tasks
        const tasks = [];
        document.querySelectorAll('#suggestions-tasks .crm-suggestion-item').forEach(item => {
            const titleInput = item.querySelector('input[name="title"]');
            const prioritySelect = item.querySelector('select[name="priority"]');
            if (titleInput) {
                tasks.push({
                    title: titleInput.value,
                    priority: prioritySelect ? prioritySelect.value : 'medium'
                });
            }
        });
        
        if (entities.length === 0 && tasks.length === 0 && relationships.length === 0) {
            this.showNotification('Нет предложений для подтверждения', 'warning');
            return;
        }
        
        // Показываем спиннер
        const contentEl = document.getElementById('note-suggestions-content');
        if (contentEl) {
            contentEl.innerHTML = '<div class="crm-analyzing-state"><i class="ti ti-loader crm-spinner"></i><span>Importing...</span></div>';
        }
        
        try {
            const response = await fetch(`/crm/partials/notes/${noteId}/approve-suggestions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'HX-Request': 'true'
                },
                body: JSON.stringify({ 
                    entities, 
                    relationships,
                    tasks,
                    create_event: true,
                    link_author: true
                })
            });
            
            if (response.ok) {
                const html = await response.text();
                if (contentEl) {
                    contentEl.innerHTML = html;
                }
                // Trigger update of linked entities
                document.body.dispatchEvent(new CustomEvent('entitiesUpdated'));
            } else {
                throw new Error('Failed to approve suggestions');
            }
        } catch (error) {
            console.error('Error approving suggestions:', error);
            this.showNotification('Ошибка при подтверждении предложений', 'error');
            if (contentEl) {
                contentEl.innerHTML = '<div class="crm-alert crm-alert-warning"><i class="ti ti-alert-triangle"></i><span>Ошибка при подтверждении</span></div>';
            }
        }
    }
    
    approveSuggestion(button, action) {
        const item = button.closest('.crm-suggestion-item');
        const entityType = item.dataset.entityType;
        
        // Собираем данные из формы
        const form = item.querySelector('.crm-sug-form');
        const data = { attributes: {} };
        
        if (form) {
            const nameInput = form.querySelector('input[name="name"]');
            const typeSelect = form.querySelector('select[name="type"]');
            const aiDescInput = form.querySelector('input[name="ai_description"]');
            const relevanceInput = form.querySelector('input[name="relevance"]');
            
            data.name = nameInput?.value || item.querySelector('.crm-suggestion-name')?.textContent;
            data.type = typeSelect?.value || entityType;
            data.ai_description = aiDescInput?.value || item.dataset.aiDescription || 'Сущность извлечена AI';
            data.relevance = relevanceInput ? parseFloat(relevanceInput.value) / 100 : parseFloat(item.dataset.relevance || 0.5);
            
            // Собираем атрибуты
            form.querySelectorAll('.crm-sug-attr-row').forEach(row => {
                const keyInput = row.querySelector('.crm-sug-attr-key');
                const valInput = row.querySelector('.crm-sug-attr-val');
                if (keyInput && valInput && keyInput.value && valInput.value) {
                    data.attributes[keyInput.value] = valInput.value;
                }
            });
        } else {
            data.name = item.querySelector('.crm-suggestion-name')?.textContent;
            data.type = entityType;
            data.ai_description = item.dataset.aiDescription || 'Сущность извлечена AI';
            data.relevance = parseFloat(item.dataset.relevance || 0.5);
            try {
                data.attributes = JSON.parse(item.dataset.attributes || '{}');
            } catch (e) {
                data.attributes = {};
            }
        }
        
        // Визуальная обратная связь
        button.disabled = true;
        button.innerHTML = '<i class="ti ti-loader crm-spinner"></i>';
        
        // Отправляем на сервер
        const isTask = item.dataset.suggestionId?.startsWith('task-');
        const endpoint = isTask 
            ? '/crm/api/v1/tasks' 
            : '/crm/api/v1/entities';
        
        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (response.ok) {
                item.classList.add('approved');
                item.style.borderColor = 'var(--crm-success)';
                button.innerHTML = '<i class="ti ti-check"></i> DONE';
                button.classList.remove('crm-suggestion-btn-create', 'crm-suggestion-btn-update');
                button.style.background = '#dcfce7';
                button.style.color = '#16a34a';
                
                this.showNotification(
                    isTask ? 'Задача создана' : `Сущность ${action === 'create' ? 'создана' : 'обновлена'}`,
                    'success'
                );
            } else {
                throw new Error('Failed to save');
            }
        })
        .catch(error => {
            console.error('Error approving suggestion:', error);
            button.disabled = false;
            button.textContent = action.toUpperCase();
            this.showNotification('Ошибка сохранения', 'error');
        });
    }
    
    saveSuggestionEdit(button) {
        const item = button.closest('.crm-suggestion-item');
        const form = item.querySelector('.crm-sug-form');
        if (!form) return;
        
        // Обновляем отображаемое имя
        const nameInput = form.querySelector('input[name="name"]');
        if (nameInput) {
            const nameDisplay = item.querySelector('.crm-suggestion-name');
            if (nameDisplay) {
                nameDisplay.textContent = nameInput.value;
            }
        }
        
        // Обновляем тип если есть
        const typeSelect = form.querySelector('select[name="type"]');
        if (typeSelect) {
            item.dataset.entityType = typeSelect.value;
            
            // Обновляем отображение типа
            const typeDisplay = item.querySelector('.crm-suggestion-type');
            if (typeDisplay) {
                const selectedOption = typeSelect.options[typeSelect.selectedIndex];
                typeDisplay.textContent = selectedOption?.textContent || typeSelect.value;
            }
        }
        
        // Собираем и сохраняем атрибуты
        const attributes = {};
        form.querySelectorAll('.crm-sug-attr-row').forEach(row => {
            const keyInput = row.querySelector('.crm-sug-attr-key');
            const valInput = row.querySelector('.crm-sug-attr-val');
            if (keyInput && valInput && keyInput.value && valInput.value) {
                attributes[keyInput.value] = valInput.value;
            }
        });
        item.dataset.attributes = JSON.stringify(attributes);
        
        // Сохраняем ai_description
        const aiDescInput = form.querySelector('input[name="ai_description"]');
        if (aiDescInput) {
            item.dataset.aiDescription = aiDescInput.value;
        }
        
        // Обновляем отображение атрибутов в основном блоке
        const attrsDisplay = item.querySelector('.crm-suggestion-attrs');
        if (attrsDisplay) {
            attrsDisplay.innerHTML = Object.entries(attributes)
                .filter(([k, v]) => v && k !== 'name')
                .map(([k, v]) => `<span class="crm-suggestion-attr">${k}: ${v}</span>`)
                .join('');
        }
        
        // Сворачиваем форму
        const toggleBtn = item.querySelector('.crm-suggestion-btn-icon');
        if (toggleBtn) {
            this.toggleSuggestionEdit(toggleBtn);
        }
        
        this.showNotification('Изменения применены', 'success');
    }
    
    updateSuggestionFields(selectEl) {
        // При смене типа сущности - обновляем UI
        const item = selectEl.closest('.crm-suggestion-item');
        if (item) {
            item.dataset.entityType = selectEl.value;
            
            // Обновляем отображение типа
            const typeDisplay = item.querySelector('.crm-suggestion-type');
            if (typeDisplay) {
                const selectedOption = selectEl.options[selectEl.selectedIndex];
                typeDisplay.textContent = selectedOption?.textContent || selectEl.value;
            }
            
            // Обновляем иконку
            const iconEl = item.querySelector('.crm-suggestion-icon');
            if (iconEl) {
                const icons = { 
                    person: 'ti-user', 
                    organization: 'ti-building', 
                    project: 'ti-folder',
                    task: 'ti-checklist'
                };
                const iconClass = icons[selectEl.value] || 'ti-bookmark';
                iconEl.innerHTML = `<i class="ti ${iconClass}"></i>`;
                iconEl.className = `crm-suggestion-icon crm-suggestion-icon-${selectEl.value || 'default'}`;
            }
        }
    }
    
    addSuggestionAttr(button) {
        const form = button.closest('.crm-sug-form');
        const attrsContainer = form.querySelector('.crm-sug-attrs');
        
        const row = document.createElement('div');
        row.className = 'crm-sug-attr-row';
        row.innerHTML = `
            <input type="text" class="crm-sug-input crm-sug-attr-key" placeholder="Ключ" onchange="this.name = 'attr_' + this.value">
            <input type="text" class="crm-sug-input crm-sug-attr-val" placeholder="Значение">
            <button type="button" class="crm-sug-attr-del" onclick="this.parentElement.remove()">×</button>
        `;
        
        attrsContainer.appendChild(row);
        row.querySelector('.crm-sug-attr-key').focus();
    }
    
    updateSuggestionCounts() {
        const entitiesCount = document.querySelectorAll('#suggestions-entities .crm-suggestion-item').length;
        const relationshipsCount = document.querySelectorAll('#suggestions-relationships .crm-suggestion-item').length;
        const tasksCount = document.querySelectorAll('#suggestions-tasks .crm-suggestion-item').length;
        
        const counters = document.querySelectorAll('.crm-suggestion-count');
        counters.forEach(counter => {
            const section = counter.closest('.crm-suggestion-section');
            if (section?.querySelector('#suggestions-entities')) {
                counter.textContent = entitiesCount;
            } else if (section?.querySelector('#suggestions-relationships')) {
                counter.textContent = relationshipsCount;
            } else if (section?.querySelector('#suggestions-tasks')) {
                counter.textContent = tasksCount;
            }
        });
    }
    
    _createGlobalAPI() {
        const self = this;
        return {
    analyzeNote: (noteId) => self.analyzeNote(noteId),
    zoomGraph: (dir) => self.zoomGraph(dir),
    fitGraph: () => self.fitGraph(),
    toggleGraphEditMode: () => self.toggleGraphEditMode(),
    closeModal: () => self.closeModal(),
    openEntity: (id) => self.openEntityDetail(id),
    toggleVoice: () => self.toggleVoiceInput(),
    switchInputTab: (formId, tab) => self.switchInputTab(formId, tab),
    triggerFileUpload: (formId) => self.triggerFileUpload(formId),
    handleMentions: (textarea) => self.handleMentions(textarea),
    highlightMentions: (textarea) => self.highlightMentions(textarea),
    syncHighlightsScroll: (textarea) => self.syncHighlightsScroll(textarea),
    handleVisibilityChange: (value) => {
        const container = document.getElementById('shared-with-container');
        if (container) {
            container.style.display = value === 'shared' ? 'block' : 'none';
        }
    },
    
    // Sharing Popup methods
    toggleSharingPopup: (popupId) => {
        const popup = document.getElementById(popupId);
        if (!popup) return;
        
        const isVisible = popup.style.display !== 'none';
        
        // Close all other popups
        document.querySelectorAll('.crm-sharing-popup').forEach(p => {
            if (p.id !== popupId) p.style.display = 'none';
        });
        
        popup.style.display = isVisible ? 'none' : 'block';
        
        if (!isVisible) {
            const input = document.getElementById(`${popupId}-input`);
            if (input) input.focus();
            
            // Close on click outside
            setTimeout(() => {
                const closeHandler = (e) => {
                    const wrapper = document.getElementById(`${popupId}-wrapper`);
                    const toggleBtn = document.querySelector('.crm-shared-btn');
                    if (wrapper && !wrapper.contains(e.target) && !toggleBtn?.contains(e.target)) {
                        popup.style.display = 'none';
                        document.removeEventListener('click', closeHandler);
                    }
                };
                document.addEventListener('click', closeHandler);
            }, 100);
        }
    },
    
    closeSharingPopup: (popupId) => {
        const popup = document.getElementById(popupId);
        if (popup) popup.style.display = 'none';
    },
    
    searchShareablePopup: (popupId, query) => {
        clearTimeout(CRM._sharingPopupTimeout);
        const dropdown = document.getElementById(`${popupId}-dropdown`);
        
        if (!query || query.length < 2) {
            if (dropdown) dropdown.style.display = 'none';
            return;
        }
        
        CRM._sharingPopupTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/crm/api/sharing/search?q=${encodeURIComponent(query)}`, {
                    credentials: 'include'
                });
                if (response.ok) {
                    const results = await response.json();
                    CRM.renderShareablePopupDropdown(popupId, results);
                }
            } catch (e) {
                console.error('Sharing search error:', e);
            }
        }, 300);
    },
    
    renderShareablePopupDropdown: (popupId, results) => {
        const dropdown = document.getElementById(`${popupId}-dropdown`);
        if (!dropdown) return;
        
        if (results.length === 0) {
            dropdown.style.display = 'none';
            return;
        }
        
        dropdown.innerHTML = results.map(item => {
            const icon = item.type === 'company' ? 'ti-building' : 'ti-user';
            const name = item.name || item.email;
            const sub = item.type === 'company' 
                ? `${item.members_count || 0} members` 
                : (item.company_name || '');
            return `
                <div class="crm-sharing-popup-dropdown-item" 
                     onclick="CRM.addShareableToPopup('${popupId}', ${JSON.stringify(item).replace(/"/g, '&quot;')})">
                    <i class="ti ${icon}"></i>
                    <div class="crm-sharing-popup-dropdown-item-info">
                        <div class="crm-sharing-popup-dropdown-item-name">${name}</div>
                        ${sub ? `<div class="crm-sharing-popup-dropdown-item-sub">${sub}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        dropdown.style.display = 'block';
    },
    
    addShareableToPopup: (popupId, item) => {
        const tagsContainer = document.getElementById(`${popupId}-tags`);
        const hiddenInput = document.getElementById(`${popupId}-hidden`);
        const dropdown = document.getElementById(`${popupId}-dropdown`);
        const input = document.getElementById(`${popupId}-input`);
        
        if (!tagsContainer || !hiddenInput) return;
        
        // Get current values
        let values = [];
        try {
            values = JSON.parse(hiddenInput.value || '[]');
        } catch (e) {}
        
        // Check if already exists
        if (values.some(v => v.id === item.id && v.type === item.type)) {
            if (dropdown) dropdown.style.display = 'none';
            if (input) input.value = '';
            return;
        }
        
        // Add to values
        const newItem = {
            type: item.type,
            id: item.id,
            name: item.name || item.email
        };
        values.push(newItem);
        hiddenInput.value = JSON.stringify(values);
        
        // Add tag
        const icon = item.type === 'company' ? 'ti-building' : 'ti-user';
        const tag = document.createElement('span');
        tag.className = 'crm-sharing-tag';
        tag.dataset.type = item.type;
        tag.dataset.id = item.id;
        tag.innerHTML = `
            <i class="ti ${icon}"></i>
            <span>${item.name || item.email}</span>
            <button type="button" onclick="CRM.removeShareableFromPopup('${popupId}', this.parentElement)">
                <i class="ti ti-x"></i>
            </button>
        `;
        tagsContainer.appendChild(tag);
        
        // Clear input and dropdown
        if (dropdown) dropdown.style.display = 'none';
        if (input) input.value = '';
        
        // Update badge and auto-save
        CRM.updateSharingBadge(popupId, values.length);
        CRM.saveSharing(popupId);
    },
    
    removeShareableFromPopup: (popupId, tagElement) => {
        const hiddenInput = document.getElementById(`${popupId}-hidden`);
        if (!hiddenInput || !tagElement) return;
        
        const type = tagElement.dataset.type;
        const id = tagElement.dataset.id;
        
        // Remove from values
        let values = [];
        try {
            values = JSON.parse(hiddenInput.value || '[]');
        } catch (e) {}
        
        values = values.filter(v => !(v.id === id && v.type === type));
        hiddenInput.value = JSON.stringify(values);
        
        // Remove tag
        tagElement.remove();
        
        // Update badge and auto-save
        CRM.updateSharingBadge(popupId, values.length);
        CRM.saveSharing(popupId);
    },
    
    updateSharingBadge: (popupId, count) => {
        const badge = document.getElementById(`${popupId}-badge`);
        if (!badge) return;
        
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    },
    
    // Set entity visibility and auto-save
    setEntityVisibility: (value) => {
        const input = document.querySelector('input[name="visibility"][form="entity-edit-form"]');
        if (input) {
            input.value = value;
        }
        // Update toggle UI
        const group = document.querySelector('.crm-toggle-group[data-form="entity-edit-form"]');
        if (group) {
            group.querySelectorAll('.crm-toggle-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.value === value);
            });
        }
        // Auto-save
        CRM.saveSharing('entity-sharing');
    },
    
    // Auto-save sharing settings
    saveSharing: async (popupId) => {
        const wrapper = document.getElementById(`${popupId}-wrapper`);
        if (!wrapper) return;
        
        const resourceType = wrapper.dataset.resourceType;
        const resourceId = wrapper.dataset.resourceId;
        
        // Skip if no resource (new note/entity)
        if (!resourceType || !resourceId) return;
        
        const hiddenInput = document.getElementById(`${popupId}-hidden`);
        
        // Find visibility input by form attribute or near wrapper
        const formId = hiddenInput?.form?.id;
        let visibilityInput = formId 
            ? document.querySelector(`input[name="visibility"][form="${formId}"]`)
            : null;
        
        if (!visibilityInput) {
            const visibilityWrapper = wrapper.closest('.crm-visibility-wrapper');
            visibilityInput = visibilityWrapper?.nextElementSibling?.name === 'visibility'
                ? visibilityWrapper.nextElementSibling
                : visibilityWrapper?.parentElement?.querySelector('input[name="visibility"]');
        }
        
        let sharedWith = [];
        try {
            sharedWith = JSON.parse(hiddenInput?.value || '[]');
        } catch (e) {}
        
        const visibility = visibilityInput?.value || 'private';
        
        const response = await fetch(`/crm/api/sharing/${resourceType}/${resourceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ visibility, shared_with: sharedWith })
        });
        
        if (!response.ok) {
            CRM.showNotification('Failed to save sharing settings', 'error');
            return;
        }
        
        const data = await response.json();
        if (!data.success) {
            CRM.showNotification('Failed to save sharing settings', 'error');
        }
    },
    
    toggleSharedWith: (select) => {
        const container = document.getElementById('shared-with-container');
        if (container) {
            container.style.display = select.value === 'shared' ? 'block' : 'none';
        }
    },
    askAI: () => self.askAI(),
    showNotification: (msg, type) => self.showNotification(msg, type),
    uploadFiles: (files) => self.uploadFiles(files),
    removePendingFile: (fileId) => self.removePendingFile(fileId),
    uploadPendingFiles: (noteId) => self.uploadPendingFiles(noteId),
    get pendingFiles() { return self.pendingFiles || []; },
    
    // Sidebar settings
    saveSidebarSettings: async () => {
        const items = [];
        const settingsContainer = document.getElementById('sidebar-settings');
        if (!settingsContainer) return;
        
        settingsContainer.querySelectorAll('.crm-sidebar-setting-item').forEach((item, index) => {
            const checkbox = item.querySelector('.sidebar-visibility-toggle');
            items.push({
                id: checkbox.dataset.itemId,
                visible: checkbox.checked,
                order: index
            });
        });
        
        try {
            const response = await fetch('/crm/api/v1/profile/sidebar', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items })
            });
            
            if (response.ok) {
                self.showNotification('Настройки меню сохранены', 'success');
                window.location.reload();
            } else {
                throw new Error('Ошибка сохранения');
            }
        } catch (e) {
            self.showNotification('Ошибка сохранения настроек', 'error');
        }
    },
    
    // Widget settings
    saveWidgetSettings: async () => {
        const enabledWidgets = [];
        document.querySelectorAll('.widget-visibility-toggle:checked').forEach(checkbox => {
            enabledWidgets.push(checkbox.dataset.widgetId);
        });
        
        try {
            const response = await fetch('/crm/api/v1/profile/widgets', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled_widgets: enabledWidgets,
                    layout: {}
                })
            });
            
            if (response.ok) {
                self.showNotification('Настройки виджетов сохранены', 'success');
            } else {
                throw new Error('Ошибка сохранения');
            }
        } catch (e) {
            self.showNotification('Ошибка сохранения настроек', 'error');
        }
    },
    
    // Visibility toggle for shared_with
    toggleSharedWith: (select) => {
        const container = document.getElementById('shared-with-container');
        if (container) {
            container.style.display = select.value === 'shared' ? 'block' : 'none';
        }
    },
    
    // Sharing search state
    _sharingSearchTimeout: null,
    _sharingResults: [],
    
    // Search shareable users/companies with debounce
    searchShareable: (query) => {
        clearTimeout(CRM._sharingSearchTimeout);
        const dropdown = document.getElementById('sharing-dropdown');
        
        if (!query || query.length < 2) {
            if (dropdown) dropdown.style.display = 'none';
            return;
        }
        
        CRM._sharingSearchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/crm/api/sharing/search?q=${encodeURIComponent(query)}`, {
                    credentials: 'include'
                });
                if (response.ok) {
                    const results = await response.json();
                    CRM._sharingResults = results;
                    CRM.renderShareableDropdown(results);
                }
            } catch (e) {
                console.error('Sharing search error:', e);
            }
        }, 300);
    },
    
    // Show dropdown
    showShareableDropdown: () => {
        const dropdown = document.getElementById('sharing-dropdown');
        if (dropdown && CRM._sharingResults.length > 0) {
            dropdown.style.display = 'block';
        }
    },
    
    // Hide dropdown
    hideShareableDropdown: () => {
        setTimeout(() => {
            const dropdown = document.getElementById('sharing-dropdown');
            if (dropdown) dropdown.style.display = 'none';
        }, 200);
    },
    
    // Render dropdown with results
    renderShareableDropdown: (results) => {
        const dropdown = document.getElementById('sharing-dropdown');
        if (!dropdown) return;
        
        if (results.length === 0) {
            dropdown.innerHTML = '<div class="crm-sharing-empty">No results found</div>';
            dropdown.style.display = 'block';
            return;
        }
        
        const html = results.map(item => {
            if (item.type === 'user') {
                return `
                    <div class="crm-sharing-item" onclick="CRM.addShareableTag(${JSON.stringify(item).replace(/"/g, '&quot;')})">
                        <i class="ti ti-user crm-sharing-icon"></i>
                        <div class="crm-sharing-info">
                            <span class="crm-sharing-primary">${item.email}</span>
                            <span class="crm-sharing-secondary">${item.name}${item.company_name ? ' · ' + item.company_name : ''}</span>
                        </div>
                    </div>
                `;
            } else {
                return `
                    <div class="crm-sharing-item" onclick="CRM.addShareableTag(${JSON.stringify(item).replace(/"/g, '&quot;')})">
                        <i class="ti ti-building crm-sharing-icon crm-sharing-icon-company"></i>
                        <div class="crm-sharing-info">
                            <span class="crm-sharing-primary">${item.name}</span>
                            <span class="crm-sharing-secondary">${item.members_count || 0} members</span>
                        </div>
                    </div>
                `;
            }
        }).join('');
        
        dropdown.innerHTML = html;
        dropdown.style.display = 'block';
    },
    
    // Add tag to shared list
    addShareableTag: (item) => {
        const container = document.getElementById('shared-with-tags');
        const input = document.getElementById('shared-with-input');
        const hidden = document.getElementById('shared-with-hidden');
        const dropdown = document.getElementById('sharing-dropdown');
        
        let items = JSON.parse(hidden.value || '[]');
        
        // Check if already exists
        const exists = items.some(i => {
            if (typeof i === 'object') return i.type === item.type && i.id === item.id;
            return i === item.id;
        });
        if (exists) {
            if (dropdown) dropdown.style.display = 'none';
            if (input) input.value = '';
            return;
        }
        
        // Add to list
        items.push({
            type: item.type,
            id: item.id,
            name: item.name || item.email,
            email: item.email || ''
        });
        hidden.value = JSON.stringify(items);
        
        // Create tag element
        const tag = document.createElement('span');
        tag.className = `crm-tag crm-${item.type}-tag`;
        tag.dataset.type = item.type;
        tag.dataset.id = item.id;
        
        const icon = item.type === 'company' ? 'building' : 'user';
        const label = item.type === 'user' ? item.email : item.name;
        tag.innerHTML = `<i class="ti ti-${icon}"></i> ${label} <span class="crm-tag-remove" onclick="CRM.removeShareableTag(this)">&times;</span>`;
        
        container.insertBefore(tag, input);
        
        // Clear input and hide dropdown
        if (input) input.value = '';
        if (dropdown) dropdown.style.display = 'none';
        CRM._sharingResults = [];
    },
    
    // Remove tag from shared list
    removeShareableTag: (el) => {
        const tag = el.parentElement;
        const hidden = document.getElementById('shared-with-hidden');
        
        const type = tag.dataset.type;
        const id = tag.dataset.id;
        
        let items = JSON.parse(hidden.value || '[]');
        items = items.filter(i => {
            if (typeof i === 'object') return !(i.type === type && i.id === id);
            return i !== id;
        });
        hidden.value = JSON.stringify(items);
        
        tag.remove();
    },
    
    // Legacy support
    handleSharedWithInput: (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
        }
    },
    removeSharedUser: (el, userId) => CRM.removeShareableTag(el),
    
    // Link Telegram account
    linkTelegram: async () => {
        const input = document.getElementById('telegram-id-input');
        const telegramId = input?.value?.trim();
        
        if (!telegramId) {
            CRM.showNotification('Введите Telegram ID', 'error');
            return;
        }
        
        const formData = new FormData();
        formData.append('telegram_id', telegramId);
        
        try {
            const response = await fetch('/crm/api/profile/telegram', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const html = await response.text();
                document.getElementById('crm-content').innerHTML = html;
                CRM.showNotification('Telegram успешно привязан', 'success');
            } else {
                CRM.showNotification('Ошибка привязки Telegram', 'error');
            }
        } catch (e) {
            console.error('Telegram link error:', e);
            CRM.showNotification('Ошибка привязки Telegram', 'error');
        }
    },
    
    // Toggle tasks panel visibility
    toggleTasksPanel: () => {
        const app = document.querySelector('.crm-app');
        const isHidden = app.classList.toggle('tasks-panel-hidden');
        
        // Save state to cookie (expires in 365 days)
        const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
        document.cookie = `crm_tasks_hidden=${isHidden}; path=/; expires=${expires}; SameSite=Lax`;
    },
    
    // AI Suggestions
    toggleSuggestionEdit: (btn) => self.toggleSuggestionEdit(btn),
    discardSuggestion: (btn) => self.discardSuggestion(btn),
    discardAllSuggestions: () => self.discardAllSuggestions(),
    approveSuggestion: (btn, action) => self.approveSuggestion(btn, action),
    saveSuggestionEdit: (btn) => self.saveSuggestionEdit(btn),
    updateSuggestionFields: (select) => self.updateSuggestionFields(select),
    addSuggestionAttr: (btn) => self.addSuggestionAttr(btn),
    approveAllSuggestions: (noteId) => self.approveAllSuggestions(noteId),
    
    // AI Tooltip
    showAiTooltip(button) {
        // Remove any existing tooltips
        document.querySelectorAll('.crm-ai-tooltip').forEach(t => t.remove());
        
        const description = button.dataset.aiDescription;
        if (!description) return;
        
        // Create tooltip
        const tooltip = document.createElement('div');
        tooltip.className = 'crm-ai-tooltip';
        tooltip.innerHTML = `
            <div class="crm-ai-tooltip-header">
                <i class="ti ti-robot"></i>
                AI Context
            </div>
            <div class="crm-ai-tooltip-content">${description}</div>
        `;
        
        // Position below button
        document.body.appendChild(tooltip);
        const rect = button.getBoundingClientRect();
        tooltip.style.top = `${rect.bottom + 8 + window.scrollY}px`;
        tooltip.style.left = `${Math.max(10, rect.left - 20 + window.scrollX)}px`;
        
        // Close on click outside
        const closeHandler = (e) => {
            if (!tooltip.contains(e.target) && e.target !== button) {
                tooltip.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 10);
    },
    
    // File operations
    async downloadFile(noteId, fileId) {
        try {
            const response = await fetch(`/crm/api/notes/${noteId}/attachments/${fileId}/download`);
            if (response.ok) {
                const data = await response.json();
                if (data.download_url) {
                    window.open(data.download_url, '_blank');
                }
            } else {
                CRM.showNotification('Ошибка скачивания файла', 'error');
            }
        } catch (e) {
            console.error('Download error:', e);
            CRM.showNotification('Ошибка скачивания', 'error');
        }
    },
    
    async downloadAttachment(noteId, fileId) {
        try {
            const response = await fetch(`/crm/api/notes/${noteId}/attachments/${fileId}/download`);
            if (response.ok) {
                const data = await response.json();
                if (data.download_url) {
                    window.open(data.download_url, '_blank');
                }
            }
        } catch (e) {
            console.error('Download error:', e);
        }
    },
    
    async deleteAttachment(noteId, fileId) {
        if (!confirm('Удалить файл?')) return;
        
        try {
            const response = await fetch(`/crm/api/notes/${noteId}/attachments/${fileId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                // Refresh attachments list
                const list = document.getElementById('attachments-list');
                if (list) {
                    const res = await fetch(`/crm/api/notes/${noteId}/attachments`);
                    list.innerHTML = await res.text();
                }
                self.showNotification('Файл удален', 'success');
            }
        } catch (e) {
            console.error('Delete error:', e);
            self.showNotification('Ошибка удаления', 'error');
        }
    },
    
    async showFileContent(noteId, fileId, button) {
        // Remove existing tooltip
        document.querySelectorAll('.crm-file-content-tooltip').forEach(t => t.remove());
        
        // Create tooltip
        const tooltip = document.createElement('div');
        tooltip.className = 'crm-file-content-tooltip';
        tooltip.innerHTML = '<div class="loading"><i class="ti ti-loader crm-spinner"></i> Загрузка...</div>';
        
        // Position near button (above it)
        const rect = button.getBoundingClientRect();
        tooltip.style.position = 'fixed';
        tooltip.style.left = `${rect.right + 10}px`;
        tooltip.style.top = `${Math.max(10, rect.top - 100)}px`;
        
        document.body.appendChild(tooltip);
        
        // Close on click outside
        const closeHandler = (e) => {
            if (!tooltip.contains(e.target) && e.target !== button) {
                tooltip.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 100);
        
        try {
            const response = await fetch(`/crm/api/notes/${noteId}/attachments/${fileId}/content`);
            if (response.ok) {
                const data = await response.json();
                if (data.content) {
                    const preview = data.content.length > 1000 
                        ? data.content.substring(0, 1000) + '...' 
                        : data.content;
                    tooltip.innerHTML = `<div class="content">${preview}</div>`;
                } else {
                    tooltip.innerHTML = '<div class="error">Контент еще не проиндексирован</div>';
                }
            } else {
                tooltip.innerHTML = '<div class="error">Контент недоступен</div>';
            }
        } catch (e) {
            console.error('Content error:', e);
            tooltip.innerHTML = '<div class="error">Ошибка загрузки</div>';
        }
    }
};
    }
}

