/**
 * Traces Module - просмотр OpenTelemetry трейсов
 */

/**
 * Утилиты для работы с traces
 */
class TraceUtils {
    static escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }
    static formatJson(obj) {
        try {
            const serializable = this.serializeForJson(obj);
            return JSON.stringify(serializable, null, 2);
        } catch (e) {
            console.error('Ошибка форматирования JSON:', e);
            return String(obj);
        }
    }

    static formatJsonWithSyntaxHighlighting(jsonString) {
        // Простое форматирование JSON с подсветкой синтаксиса
        return jsonString
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
                let cls = 'json-number';
                if (/^"/.test(match)) {
                    if (/:$/.test(match)) {
                        cls = 'json-key';
                    } else {
                        cls = 'json-string';
                    }
                } else if (/true|false/.test(match)) {
                    cls = 'json-boolean';
                } else if (/null/.test(match)) {
                    cls = 'json-null';
                }
                return `<span class="${cls}">${match}</span>`;
            });
    }
    static serializeForJson(obj) {
        if (obj === null || obj === undefined) {
            return obj;
        }
        if (obj instanceof Date) {
            return obj.toISOString();
        }
        if (typeof obj === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(obj)) {
            return obj;
        }
        if (Array.isArray(obj)) {
            return obj.map(item => this.serializeForJson(item));
        }
        if (typeof obj === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(obj)) {
                result[key] = this.serializeForJson(value);
            }
            return result;
        }
        return obj;
    }
    static formatDuration(durationMs) {
        if (!durationMs) return '—';
        return `${(durationMs / 1000).toFixed(2)}s`;
    }
    static formatCost(cost) {
        if (!cost) return '—';
        return `$${cost.toFixed(4)}`;
    }
    static getSpanIcon(spanType) {
        const icons = {
            'agent': '<i class="bi bi-robot text-purple"></i>',
            'llm': '<i class="bi bi-chat-square-text text-blue"></i>',
            'tool': '<i class="bi bi-tools text-green"></i>',
            'chain': '<i class="bi bi-diagram-2 text-orange"></i>',
            'retriever': '<i class="bi bi-search text-info"></i>',
        };
        return icons[spanType] || '<i class="bi bi-circle text-secondary"></i>';
    }
    static getSpanBadgeClass(spanType) {
        return `trace-badge-type trace-badge-${spanType}`;
    }
}

/**
 * Класс для построения execution tree
 */
class TraceTree {
    constructor(container, onSpanSelect) {
        this.container = container;
        this.onSpanSelect = onSpanSelect;
        this.selectedSpanId = null;
    }

    /**
     * Построение дерева из spans
     */
    build(spans) {
        const spanMap = new Map();
        const rootSpans = [];

        for (const span of spans) {
            spanMap.set(span.span_id, {
                ...span,
                children: []
            });
        }

        for (const span of spans) {
            const spanNode = spanMap.get(span.span_id);
            if (span.parent_span_id && spanMap.has(span.parent_span_id)) {
                const parent = spanMap.get(span.parent_span_id);
                parent.children.push(spanNode);
            } else {
                rootSpans.push(spanNode);
            }
        }

        this.container.innerHTML = '';
        const treeRoot = document.createElement('div');
        treeRoot.className = 'execution-tree-root';

        for (const rootSpan of rootSpans) {
            treeRoot.appendChild(this.renderNode(rootSpan, 0, [], true));
        }

        this.container.appendChild(treeRoot);
    }

    /**
     * Рендеринг узла дерева с линиями связи
     */
    renderNode(spanNode, level, ancestorLines, isLast) {
        const wrapper = document.createElement('div');
        wrapper.className = 'execution-tree-item';
        wrapper.dataset.spanId = spanNode.span_id;

        const hasChildren = spanNode.children.length > 0;

        // Создаем строку для узла (линии + контент)
        const nodeRow = document.createElement('div');
        nodeRow.className = 'execution-tree-row';
        nodeRow.style.display = 'flex';
        nodeRow.style.alignItems = 'center';

        // Контейнер для линий
        const lineContainer = document.createElement('div');
        lineContainer.className = 'execution-tree-lines';

        // Рисуем линии предков
        for (const shouldDraw of ancestorLines) {
            const line = document.createElement('div');
            line.className = 'execution-tree-line-vertical';
            if (!shouldDraw) {
                line.style.visibility = 'hidden';
            }
            lineContainer.appendChild(line);
        }

        // Горизонтальная линия соединения (если не root)
        if (level > 0) {
            const horizontalLine = document.createElement('div');
            horizontalLine.className = 'execution-tree-line-horizontal';
            lineContainer.appendChild(horizontalLine);
        }

        // Badge с иконкой типа
        const badge = document.createElement('div');
        badge.className = `execution-tree-badge execution-tree-badge-${spanNode.span_type}`;
        badge.innerHTML = TraceUtils.getSpanIcon(spanNode.span_type);
        lineContainer.appendChild(badge);

        // Вертикальная линия вниз (если есть дети)
        if (hasChildren) {
            const verticalLineDown = document.createElement('div');
            verticalLineDown.className = 'execution-tree-line-down';
            lineContainer.appendChild(verticalLineDown);
        }

        nodeRow.appendChild(lineContainer);

        // Контент: название и длительность
        const content = document.createElement('button');
        content.className = 'execution-tree-content';
        content.type = 'button';

        const nameAndInfo = document.createElement('div');
        nameAndInfo.className = 'execution-tree-name-block';

        const name = document.createElement('span');
        name.className = 'execution-tree-name';
        name.textContent = spanNode.name;

        const duration = document.createElement('span');
        duration.className = `execution-tree-duration ${this.getDurationClass(spanNode.duration_ms)}`;
        duration.textContent = TraceUtils.formatDuration(spanNode.duration_ms);

        nameAndInfo.appendChild(name);
        nameAndInfo.appendChild(duration);

        content.appendChild(nameAndInfo);

        // Кнопка раскрытия (если есть дети)
        if (hasChildren) {
            const expandBtn = document.createElement('button');
            expandBtn.className = 'execution-tree-expand-btn expanded';
            expandBtn.type = 'button';
            expandBtn.innerHTML = `
                <span class="execution-tree-expand-icon">
                    <i class="bi bi-chevron-down"></i>
                </span>
            `;

            expandBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleNode(wrapper);
            });

            content.appendChild(expandBtn);
        }

        content.addEventListener('click', (e) => {
            if (!e.target.closest('.execution-tree-expand-btn')) {
                this.selectSpan(spanNode.span_id);
            }
        });

        nodeRow.appendChild(content);
        wrapper.appendChild(nodeRow);

        // Контейнер для детей
        if (hasChildren) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'execution-tree-children';

            const newAncestorLines = [...ancestorLines];
            if (level > 0) {
                newAncestorLines.push(!isLast);
            }

            for (let i = 0; i < spanNode.children.length; i++) {
                const child = spanNode.children[i];
                const isLastChild = i === spanNode.children.length - 1;
                childrenContainer.appendChild(
                    this.renderNode(child, level + 1, newAncestorLines, isLastChild)
                );
            }

            wrapper.appendChild(childrenContainer);
        }

        return wrapper;
    }

    /**
     * Получение иконки для типа span
     */
    getSpanIcon(spanType) {
        const icons = {
            'agent': '<i class="bi bi-robot"></i>',
            'llm': '<i class="bi bi-stars"></i>',
            'tool': '<i class="bi bi-tools"></i>',
            'chain': '<i class="bi bi-link-45deg"></i>',
            'retriever': '<i class="bi bi-search"></i>',
            'embedding': '<i class="bi bi-grid-3x3"></i>',
            'parser': '<i class="bi bi-code-square"></i>',
            'prompt': '<i class="bi bi-chat-left-text"></i>',
            'other': '<i class="bi bi-circle"></i>'
        };
        return icons[spanType] || icons.other;
    }

    /**
     * Получение CSS класса для длительности (для цветовой индикации)
     */
    getDurationClass(durationMs) {
        if (!durationMs) return 'duration-fast';
        if (durationMs > 3000) return 'duration-slow';
        if (durationMs > 1000) return 'duration-medium';
        return 'duration-fast';
    }

    /**
     * Выбор span
     */
    selectSpan(spanId, triggerCallback = true) {
        if (this.selectedSpanId === spanId && !triggerCallback) {
            return;
        }

        const items = document.querySelectorAll('.execution-tree-item');
        for (const item of items) {
            item.classList.remove('active');
        }

        const item = document.querySelector(`[data-span-id="${spanId}"]`);
        if (item) {
            item.classList.add('active');
            item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }

        const wasSelected = this.selectedSpanId === spanId;
        this.selectedSpanId = spanId;
        if (this.onSpanSelect && triggerCallback && !wasSelected) {
            this.onSpanSelect(spanId);
        }
    }

    /**
     * Переключение узла дерева
     */
    toggleNode(wrapper) {
        const childrenContainer = wrapper.querySelector('.execution-tree-children');
        const expandBtn = wrapper.querySelector('.execution-tree-expand-btn');

        if (!childrenContainer || !expandBtn) return;

        const icon = expandBtn.querySelector('.execution-tree-expand-icon i');
        const isExpanded = !childrenContainer.classList.contains('collapsed');

        if (isExpanded) {
            childrenContainer.classList.add('collapsed');
            icon.classList.remove('bi-chevron-down');
            icon.classList.add('bi-chevron-right');
            expandBtn.classList.remove('expanded');
        } else {
            childrenContainer.classList.remove('collapsed');
            icon.classList.remove('bi-chevron-right');
            icon.classList.add('bi-chevron-down');
            expandBtn.classList.add('expanded');
        }
    }
}

/**
 * Класс для построения Timeline графа
 */
class TraceTimeline {
    constructor(container, onSpanSelect) {
        this.container = container;
        this.onSpanSelect = onSpanSelect;
        this.selectedSpanId = null;
        this.svg = null;
        this.spans = [];
    }

    async build(spans) {
        if (!spans || spans.length === 0) {
            this.container.innerHTML = '<div class="p-3 text-muted">Нет данных для отображения</div>';
            return;
        }

        this.spans = spans;

        // Ожидаем D3
        await this.waitForD3();
        if (typeof d3 === 'undefined') {
            console.error('❌ D3.js не загружен');
            this.container.innerHTML = '<div class="text-danger p-2">D3.js не загружен. Перезагрузите страницу.</div>';
            return;
        }

        const sortedSpans = [...spans].sort((a, b) =>
            new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
        );
        const lanes = this.calculateLanes(sortedSpans);
        const height = Math.max(150, lanes.length * 40 + 60);

        this.container.innerHTML = '';
        const containerRect = this.container.getBoundingClientRect();
        const width = containerRect.width || 1000;

        this.svg = d3.select(this.container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .style('font-family', 'system-ui, -apple-system, sans-serif');

        const timeExtent = this.calculateTimeExtent(sortedSpans);
        const timeScale = d3.scaleLinear()
            .domain([0, timeExtent.duration])
            .range([100, width - 100]);

        this.renderTimeline(lanes, timeExtent, timeScale, height);
    }

    calculateLanes(spans) {
        const lanes = [];
        spans.forEach(span => {
            const startTime = new Date(span.start_time).getTime();
            const endTime = span.end_time ? new Date(span.end_time).getTime() : new Date().getTime();
            let laneIndex = lanes.findIndex(lane => {
                const lastSpan = lane[lane.length - 1];
                const lastEndTime = lastSpan.end_time ? new Date(lastSpan.end_time).getTime() : new Date().getTime();
                return lastEndTime <= startTime;
            });
            if (laneIndex === -1) {
                laneIndex = lanes.length;
                lanes.push([]);
            }
            lanes[laneIndex].push(span);
        });
        return lanes;
    }

    calculateTimeExtent(spans) {
        const times = spans.map(s => ({
            start: new Date(s.start_time).getTime(),
            end: s.end_time ? new Date(s.end_time).getTime() : new Date().getTime()
        }));
        const minTime = Math.min(...times.map(t => t.start));
        const maxTime = Math.max(...times.map(t => t.end));
        return { minTime, maxTime, duration: maxTime - minTime };
    }

    renderTimeline(lanes, timeExtent, timeScale, height) {
        const g = this.svg.append('g')
            .attr('transform', 'translate(0, 30)');

        this.renderTimeAxis(g, timeScale, timeExtent);

        lanes.forEach((lane, laneIndex) => {
            const laneY = laneIndex * 40;
            g.append('line')
                .attr('x1', timeScale(0))
                .attr('x2', timeScale(timeExtent.duration))
                .attr('y1', laneY + 20)
                .attr('y2', laneY + 20)
                .attr('stroke', 'var(--border-primary)')
                .attr('stroke-width', 1)
                .attr('opacity', 0.3);

            lane.forEach(span => {
                this.renderSpanBar(g, span, laneY, timeExtent, timeScale);
            });
        });
    }

    renderSpanBar(g, span, y, timeExtent, timeScale) {
        const startTime = new Date(span.start_time).getTime();
        const endTime = span.end_time ? new Date(span.end_time).getTime() : new Date().getTime();
        const x = timeScale(startTime - timeExtent.minTime);
        const width = Math.max(timeScale(endTime - startTime) - timeScale(0), 3);

        const barGroup = g.append('g')
            .attr('class', 'timeline-span-group')
            .style('cursor', 'pointer')
            .on('click', (event) => {
                event.stopPropagation();
                this.selectSpan(span.span_id);
            })
            .on('mouseenter', (event) => {
                this.showTooltip(event, span);
            })
            .on('mouseleave', () => {
                this.hideTooltip();
            });

        barGroup.append('rect')
            .attr('class', 'timeline-bar')
            .attr('data-span-id', span.span_id)
            .attr('x', x)
            .attr('y', y + 10)
            .attr('width', width)
            .attr('height', 20)
            .attr('rx', 3)
            .attr('fill', this.getSpanColor(span.span_type))
            .attr('opacity', 0.9);

        if (width > 50) {
            barGroup.append('text')
                .attr('x', x + 5)
                .attr('y', y + 24)
                .attr('fill', 'white')
                .style('font-size', '11px')
                .style('font-weight', '600')
                .text(this.truncateName(span.name, Math.floor(width / 7)));
        }
    }

    renderTimeAxis(g, timeScale, timeExtent) {
        const axisTicks = 10;
        const step = timeExtent.duration / axisTicks;
        const axisG = g.append('g')
            .attr('transform', 'translate(0, -10)');
        for (let i = 0; i <= axisTicks; i++) {
            const time = i * step;
            const x = timeScale(time);
            g.append('line')
                .attr('x1', x)
                .attr('x2', x)
                .attr('y1', 0)
                .attr('y2', 300)
                .attr('stroke', 'var(--border-primary)')
                .attr('stroke-width', 0.5)
                .attr('opacity', 0.2);
            axisG.append('text')
                .attr('x', x)
                .attr('y', 0)
                .attr('text-anchor', 'middle')
                .attr('fill', 'var(--text-secondary)')
                .style('font-size', '10px')
                .text(this.formatAxisTime(time));
        }
    }

    formatAxisTime(ms) {
        if (ms < 1000) {
            return `${Math.round(ms)}ms`;
        } else if (ms < 60000) {
            return `${(ms / 1000).toFixed(1)}s`;
        } else {
            return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
        }
    }

    showTooltip(event, span) {
        const tooltip = d3.select('body')
            .append('div')
            .attr('class', 'trace-tooltip')
            .style('position', 'absolute')
            .style('background', 'var(--bg-card)')
            .style('border', '1px solid var(--border-primary)')
            .style('border-radius', '6px')
            .style('padding', '8px 12px')
            .style('font-size', '12px')
            .style('box-shadow', '0 2px 8px rgba(0,0,0,0.15)')
            .style('z-index', '10000')
            .style('pointer-events', 'none');

        tooltip.html(`
            <div style="font-weight: 600; margin-bottom: 4px;">${TraceUtils.escapeHtml(span.name)}</div>
            <div style="color: var(--text-secondary); font-size: 11px;">
                <div>Type: <span class="trace-badge-type trace-badge-${span.span_type}">${span.span_type}</span></div>
                <div>Duration: ${TraceUtils.formatDuration(span.duration_ms)}</div>
                ${span.cost ? `<div>Cost: $${span.cost.toFixed(4)}</div>` : ''}
            </div>
        `);

        tooltip
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
    }

    hideTooltip() {
        d3.selectAll('.trace-tooltip').remove();
    }

    selectSpan(spanId) {
        if (!this.svg) {
            return;
        }
        if (this.selectedSpanId === spanId) {
            return;
        }
        this.svg.selectAll('.timeline-bar')
            .classed('selected', false)
            .attr('stroke', 'none');
        this.svg.selectAll(`.timeline-bar[data-span-id="${spanId}"]`)
            .classed('selected', true)
            .attr('stroke', '#000')
            .attr('stroke-width', 2);
        this.selectedSpanId = spanId;
    }

    getSpanColor(spanType) {
        const colors = {
            'agent': '#a855f7',
            'llm': '#3b82f6',
            'tool': '#10b981',
            'chain': '#f59e0b',
            'retriever': '#06b6d4',
            'default': '#6b7280'
        };
        return colors[spanType] || colors.default;
    }

    truncateName(name, maxLength) {
        if (name.length <= maxLength) {
            return name;
        }
        return name.substring(0, maxLength - 3) + '...';
    }

    waitForD3() {
        return new Promise((resolve) => {
            if (typeof d3 !== 'undefined') {
                resolve();
                return;
            }
            let attempts = 0;
            const maxAttempts = 50;
            const checkD3 = setInterval(() => {
                attempts++;
                if (typeof d3 !== 'undefined') {
                    clearInterval(checkD3);
                    resolve();
                } else if (attempts >= maxAttempts) {
                    clearInterval(checkD3);
                    console.error('❌ D3.js не загрузился за', maxAttempts * 100, 'ms');
                    resolve();
                }
            }, 100);
        });
    }
}

/**
 * Класс для отображения деталей span
 */
class SpanDetails {
    constructor(container) {
        this.container = container;
    }

    render(span) {
        console.log('📄 Rendering span details:', span?.name);
        if (!span) {
            this.renderEmpty();
            return;
        }

        const html = `
            <div class="span-details-wrapper">
                <div class="span-details-header">
                    <h6 class="mb-0">${TraceUtils.escapeHtml(span.name)}</h6>
                    <div class="span-details-badges">
                        <span class="${TraceUtils.getSpanBadgeClass(span.span_type)}">${span.span_type}</span>
                        <span class="badge ${span.status === 'error' ? 'bg-danger' : 'bg-success'}">${span.status}</span>
                    </div>
                </div>
                <div class="span-details-info">
                    <div class="span-detail-row">
                        <span class="span-detail-label">Latency:</span>
                        <span class="span-detail-value font-mono">${TraceUtils.formatDuration(span.duration_ms)}</span>
                    </div>
                    ${span.cost ? `
                        <div class="span-detail-row">
                            <span class="span-detail-label">Cost:</span>
                            <span class="span-detail-value font-mono">${TraceUtils.formatCost(span.cost)}</span>
                        </div>
                    ` : ''}
                    <div class="span-detail-row">
                        <span class="span-detail-label">Span ID:</span>
                        <code class="span-detail-value">${TraceUtils.escapeHtml(span.span_id)}</code>
                    </div>
                    ${span.parent_span_id ? `
                        <div class="span-detail-row">
                            <span class="span-detail-label">Parent ID:</span>
                            <code class="span-detail-value">${TraceUtils.escapeHtml(span.parent_span_id)}</code>
                        </div>
                    ` : ''}
                </div>
                <div class="span-details-tabs">
                    <button class="span-details-tab active" data-tab="preview">Preview</button>
                    <button class="span-details-tab" data-tab="raw">Raw</button>
                </div>
                <div class="span-details-content">
                    <div class="span-tab-content active" data-tab-content="preview">
                        ${this.renderPreviewTab(span)}
                    </div>
                    <div class="span-tab-content" data-tab-content="raw">
                        ${this.renderRawTab(span)}
                    </div>
                </div>
            </div>
        `;

        this.container.innerHTML = html;
        this.attachEventListeners();
    }

    renderPreviewTab(span) {
        const sections = [];

        // Извлекаем ключевую информацию из метаданных и сообщений
        const langchainTags = this.extractLangchainTags(span.metadata);
        const keyInfo = this.extractKeyInfo(span);

        // Показываем ключевую информацию в начале
        if (keyInfo.hasContent) {
            sections.push(this.renderKeyInfoSection(keyInfo));
        }

        // Показываем теги
        if (langchainTags.length > 0) {
            sections.push(this.renderTagsSection(langchainTags));
        }

        // Парсим и форматируем input_data
        const parsedInput = this.parseData(span.input_data);
        if (parsedInput) {
            if (parsedInput.messages && Array.isArray(parsedInput.messages)) {
                sections.push(this.renderMessagesSection('Input Messages', parsedInput.messages));
                const otherInputData = { ...parsedInput };
                delete otherInputData.messages;
                if (Object.keys(otherInputData).length > 0) {
                    sections.push(this.renderTreeSection('Input (Other)', otherInputData, true));
                }
            } else {
                sections.push(this.renderTreeSection('Input', parsedInput, true));
            }
        }

        // Парсим и форматируем output_data
        const parsedOutput = this.parseData(span.output_data);
        if (parsedOutput) {
            if (parsedOutput.messages && Array.isArray(parsedOutput.messages)) {
                sections.push(this.renderMessagesSection('Output Messages', parsedOutput.messages));
                const otherOutputData = { ...parsedOutput };
                delete otherOutputData.messages;
                if (Object.keys(otherOutputData).length > 0) {
                    sections.push(this.renderTreeSection('Output (Other)', otherOutputData, true));
                }
            } else {
                sections.push(this.renderTreeSection('Output', parsedOutput, true));
            }
        }

        if (span.usage) {
            sections.push(this.renderTreeSection('Usage', this.parseData(span.usage), true));
        }
        if (span.metadata && Object.keys(span.metadata).length > 0) {
            // Форматируем метаданные с улучшенным отображением LangChain данных
            sections.push(this.renderMetadataSection('Metadata', span.metadata));
        }
        if (span.error) {
            sections.push(`
                <div class="tree-section">
                    <div class="tree-section-title text-danger">Error</div>
                    <div class="alert alert-danger mb-0">
                        ${TraceUtils.escapeHtml(span.error)}
                    </div>
                </div>
            `);
        }
        return sections.join('');
    }

    parseData(data) {
        if (!data) return null;

        // Если это уже объект, возвращаем как есть
        if (typeof data === 'object' && data !== null) {
            return data;
        }

        // Если это строка, пытаемся распарсить
        if (typeof data === 'string') {
            // Пропускаем пустые строки
            if (data.trim() === '') return null;

            try {
                // Сначала пытаемся JSON
                const parsed = JSON.parse(data);
                return parsed;
            } catch (e1) {
                try {
                    // Если не JSON, может быть Python dict строка
                    // Более безопасная конвертация
                    let jsonLike = data.trim();

                    // Заменяем Python специфичные значения
                    jsonLike = jsonLike
                        .replace(/None/g, 'null')
                        .replace(/True/g, 'true')
                        .replace(/False/g, 'false');

                    // Заменяем одинарные кавычки на двойные (только для ключей и значений)
                    // Более умная замена, которая учитывает контекст
                    jsonLike = jsonLike.replace(/'([^']*)'/g, (match, content) => {
                        // Если это выглядит как ключ (следует двоеточие или запятая)
                        if (/:\s*$|,\s*$/.test(jsonLike.slice(jsonLike.indexOf(match) + match.length))) {
                            return `"${content}"`;
                        }
                        // Иначе - это значение, тоже заменяем
                        return `"${content.replace(/"/g, '\\"')}"`;
                    });

                    const parsed = JSON.parse(jsonLike);
                    return parsed;
                } catch (e2) {
                    // Если не получилось - возвращаем как есть
                    console.warn('Не удалось распарсить данные:', e2);
                    return data;
                }
            }
        }

        return data;
    }

    extractKeyInfo(span) {
        const info = {
            hasContent: false,
            inputMessage: null,
            outputMessage: null,
            summary: null
        };

        // Парсим input_data
        const inputData = this.parseData(span.input_data);
        if (inputData) {
            // Ищем messages в input_data
            if (inputData.messages && Array.isArray(inputData.messages)) {
                const humanMessage = inputData.messages.find(msg => {
                    const msgType = msg.type || msg._originalType || '';
                    return msgType === 'human' || msgType === 'user' ||
                           (msg.content && typeof msg.content === 'string');
                });
                if (humanMessage && humanMessage.content) {
                    info.inputMessage = this.extractQuestionFromContent(humanMessage.content);
                    info.hasContent = true;
                }
            }

            // Если не нашли в messages, ищем в других полях
            if (!info.inputMessage) {
                if (inputData.original_question) {
                    info.inputMessage = inputData.original_question;
                    info.hasContent = true;
                } else if (inputData.question) {
                    info.inputMessage = inputData.question;
                    info.hasContent = true;
                }
            }
        }

        // Также проверяем метаданные для входящего сообщения
        if (!info.inputMessage && span.metadata && span.metadata['langchain.inputs']) {
            const inputs = this.parseData(span.metadata['langchain.inputs']);
            if (inputs) {
                if (inputs.original_question) {
                    info.inputMessage = inputs.original_question;
                    info.hasContent = true;
                } else if (inputs.messages && Array.isArray(inputs.messages)) {
                    const humanMsg = inputs.messages.find(msg => {
                        const msgType = msg.type || msg._originalType || '';
                        return msgType === 'human' || msgType === 'user';
                    });
                    if (humanMsg && humanMsg.content) {
                        info.inputMessage = this.extractQuestionFromContent(humanMsg.content);
                        info.hasContent = true;
                    }
                }
            }
        }

        // Парсим output_data
        const outputData = this.parseData(span.output_data);
        if (outputData) {
            if (outputData.messages && Array.isArray(outputData.messages)) {
                // Ищем последнее AI сообщение с контентом
                const aiMessages = outputData.messages.filter(msg => {
                    const msgType = msg.type || msg._originalType || '';
                    return (msgType === 'ai' || msgType === 'assistant') && msg.content;
                });
                if (aiMessages.length > 0) {
                    const lastAIMessage = aiMessages[aiMessages.length - 1];
                    info.outputMessage = lastAIMessage.content;
                    info.summary = this.extractSummaryFromContent(lastAIMessage.content);
                    info.hasContent = true;
                }
            }
        }

        // Также проверяем метаданные для выходного сообщения
        if (!info.outputMessage && span.metadata && span.metadata['langchain.outputs']) {
            const outputs = this.parseData(span.metadata['langchain.outputs']);
            if (outputs && outputs.messages && Array.isArray(outputs.messages)) {
                const aiMessages = outputs.messages.filter(msg => {
                    const msgType = msg.type || msg._originalType || '';
                    return (msgType === 'ai' || msgType === 'assistant') && msg.content;
                });
                if (aiMessages.length > 0) {
                    const lastAIMessage = aiMessages[aiMessages.length - 1];
                    info.outputMessage = lastAIMessage.content;
                    info.summary = this.extractSummaryFromContent(lastAIMessage.content);
                    info.hasContent = true;
                }
            }
        }

        return info;
    }

    extractQuestionFromContent(content) {
        if (!content || typeof content !== 'string') return null;

        // Пытаемся найти исходный вопрос пользователя
        const questionMatch = content.match(/Исходный вопрос пользователя:\s*["']?([^"\n]+)["']?/i);
        if (questionMatch) {
            return questionMatch[1];
        }

        // Если не нашли, берем первые 200 символов
        if (content.length > 200) {
            return content.substring(0, 200) + '...';
        }
        return content;
    }

    extractSummaryFromContent(content) {
        if (!content || typeof content !== 'string') return null;

        // Ищем резюме или результат
        const summaryMatches = [
            /Резюме[:\s]+(.+?)(?:\n\n|$)/i,
            /Итог[:\s]+(.+?)(?:\n\n|$)/i,
            /\*\*Результат\*\*[:\s]+(.+?)(?:\n\n|$)/i,
            /Результат работы агента[:\s]+(.+?)(?:\n\n|$)/i
        ];

        for (const pattern of summaryMatches) {
            const match = content.match(pattern);
            if (match && match[1]) {
                return match[1].trim();
            }
        }

        // Если не нашли паттерн, берем первые 300 символов
        if (content.length > 300) {
            return content.substring(0, 300) + '...';
        }
        return content;
    }

    renderKeyInfoSection(keyInfo) {
        if (!keyInfo.hasContent) return '';

        const sections = [];

        if (keyInfo.inputMessage) {
            sections.push(`
                <div class="key-info-item">
                    <div class="key-info-label">
                        <i class="bi bi-inbox me-2"></i>
                        Входящее сообщение
                    </div>
                    <div class="key-info-value">
                        ${TraceUtils.escapeHtml(keyInfo.inputMessage)}
                    </div>
                </div>
            `);
        }

        if (keyInfo.outputMessage) {
            sections.push(`
                <div class="key-info-item">
                    <div class="key-info-label">
                        <i class="bi bi-reply me-2"></i>
                        Ответ агента
                    </div>
                    <div class="key-info-value markdown-content">
                        ${this.renderMarkdownContent(keyInfo.outputMessage)}
                    </div>
                </div>
            `);
        }

        if (keyInfo.summary && keyInfo.summary !== keyInfo.outputMessage) {
            sections.push(`
                <div class="key-info-item">
                    <div class="key-info-label">
                        <i class="bi bi-file-text me-2"></i>
                        Резюме
                    </div>
                    <div class="key-info-value">
                        ${TraceUtils.escapeHtml(keyInfo.summary)}
                    </div>
                </div>
            `);
        }

        if (sections.length === 0) return '';

        return `
            <div class="tree-section key-info-section">
                <div class="tree-section-title">
                    <i class="bi bi-info-circle me-2"></i>
                    Ключевая информация
                </div>
                <div class="key-info-container">
                    ${sections.join('')}
                </div>
            </div>
        `;
    }

    extractLangchainTags(metadata) {
        if (!metadata) return [];

        const tags = [];

        // LangGraph информация
        if (metadata['langchain.metadata']) {
            let metaData;
            try {
                metaData = typeof metadata['langchain.metadata'] === 'string'
                    ? JSON.parse(metadata['langchain.metadata'])
                    : metadata['langchain.metadata'];
            } catch (e) {
                metaData = null;
            }

            if (metaData) {
                if (metaData.langgraph_node) {
                    tags.push({
                        label: 'Node',
                        value: metaData.langgraph_node,
                        icon: 'bi-diagram-2',
                        color: 'info'
                    });
                }
                if (metaData.langgraph_step !== undefined) {
                    tags.push({
                        label: 'Step',
                        value: `#${metaData.langgraph_step}`,
                        icon: 'bi-list-ol',
                        color: 'secondary'
                    });
                }
                if (metaData.langgraph_triggers && Array.isArray(metaData.langgraph_triggers)) {
                    const triggers = metaData.langgraph_triggers.map(t => t.replace('branch:to:', '')).join(', ');
                    if (triggers) {
                        tags.push({
                            label: 'Trigger',
                            value: triggers,
                            icon: 'bi-arrow-right-circle',
                            color: 'primary'
                        });
                    }
                }
                if (metaData.thread_id) {
                    const threadParts = metaData.thread_id.split(':');
                    if (threadParts.length > 1) {
                        tags.push({
                            label: 'Flow',
                            value: threadParts[2] || 'unknown',
                            icon: 'bi-diagram-3',
                            color: 'primary'
                        });
                    }
                }
                if (metaData.langgraph_checkpoint_ns) {
                    const checkpointParts = metaData.langgraph_checkpoint_ns.split(':');
                    if (checkpointParts.length > 0) {
                        tags.push({
                            label: 'Checkpoint',
                            value: checkpointParts[0],
                            icon: 'bi-bookmark',
                            color: 'secondary',
                            title: metaData.langgraph_checkpoint_ns
                        });
                    }
                }
            }
        }

        // Selected Agent
        if (metadata['langchain.inputs']) {
            let inputs;
            try {
                inputs = typeof metadata['langchain.inputs'] === 'string'
                    ? JSON.parse(metadata['langchain.inputs'])
                    : metadata['langchain.inputs'];
            } catch (e) {
                inputs = null;
            }

            if (inputs && inputs.selected_agent) {
                tags.push({
                    label: 'Agent',
                    value: inputs.selected_agent,
                    icon: 'bi-robot',
                    color: 'purple'
                });
            }
            if (inputs && inputs.original_question) {
                const question = inputs.original_question;
                if (question.length > 50) {
                    tags.push({
                        label: 'Question',
                        value: question.substring(0, 50) + '...',
                        icon: 'bi-question-circle',
                        color: 'warning',
                        title: question
                    });
                } else {
                    tags.push({
                        label: 'Question',
                        value: question,
                        icon: 'bi-question-circle',
                        color: 'warning'
                    });
                }
            }
        }

        // Model и токены из outputs
        if (metadata['langchain.outputs']) {
            let outputs;
            try {
                outputs = typeof metadata['langchain.outputs'] === 'string'
                    ? JSON.parse(metadata['langchain.outputs'])
                    : metadata['langchain.outputs'];
            } catch (e) {
                outputs = null;
            }

            if (outputs && outputs.messages) {
                // Ищем последнее AI сообщение с метаданными
                const aiMessages = outputs.messages.filter(msg =>
                    (msg.type === 'ai' || msg.type === 'assistant' || msg._originalType === 'ai') &&
                    msg.response_metadata
                );

                if (aiMessages.length > 0) {
                    const lastAIMessage = aiMessages[aiMessages.length - 1];
                    const responseMeta = lastAIMessage.response_metadata;

                    if (responseMeta.model_name) {
                        tags.push({
                            label: 'Model',
                            value: responseMeta.model_name,
                            icon: 'bi-cpu',
                            color: 'success'
                        });
                    }

                    // Token usage
                    if (responseMeta.token_usage) {
                        const usage = responseMeta.token_usage;
                        const total = usage.total_tokens || (usage.prompt_tokens || 0) + (usage.completion_tokens || 0);
                        if (total > 0) {
                            tags.push({
                                label: 'Tokens',
                                value: `${total.toLocaleString()} (${usage.prompt_tokens || 0}/${usage.completion_tokens || 0})`,
                                icon: 'bi-123',
                                color: 'info',
                                title: `Prompt: ${usage.prompt_tokens || 0}, Completion: ${usage.completion_tokens || 0}, Total: ${total}`
                            });
                        }
                    }

                    // Finish reason
                    if (responseMeta.finish_reason) {
                        tags.push({
                            label: 'Finish',
                            value: responseMeta.finish_reason,
                            icon: responseMeta.finish_reason === 'stop' ? 'bi-check-circle' : 'bi-exclamation-circle',
                            color: responseMeta.finish_reason === 'stop' ? 'success' : 'warning'
                        });
                    }
                }

                // Tool calls
                const toolCalls = outputs.messages.filter(msg =>
                    msg.tool_calls && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0
                );
                if (toolCalls.length > 0) {
                    const allToolCalls = toolCalls.flatMap(msg => msg.tool_calls);
                    const uniqueTools = [...new Set(allToolCalls.map(tc => tc.name))];
                    if (uniqueTools.length > 0) {
                        tags.push({
                            label: 'Tools',
                            value: `${uniqueTools.length} tool${uniqueTools.length > 1 ? 's' : ''}`,
                            icon: 'bi-tools',
                            color: 'green',
                            title: uniqueTools.join(', ')
                        });
                    }
                }
            }
        }

        // Run ID
        if (metadata['langchain.run_id']) {
            tags.push({
                label: 'Run ID',
                value: metadata['langchain.run_id'].substring(0, 8) + '...',
                icon: 'bi-hash',
                color: 'secondary',
                title: metadata['langchain.run_id']
            });
        }

        // Type
        if (metadata['langchain.type']) {
            tags.push({
                label: 'Type',
                value: metadata['langchain.type'],
                icon: 'bi-tag',
                color: 'info'
            });
        }

        return tags;
    }

    renderTagsSection(tags) {
        if (!tags || tags.length === 0) return '';

        const tagsHtml = tags.map(tag => {
            let badgeClass;
            if (tag.color === 'purple') {
                badgeClass = 'bg-purple';
            } else if (tag.color === 'green') {
                badgeClass = 'bg-green';
            } else {
                badgeClass = `bg-${tag.color}`;
            }
            const titleAttr = tag.title ? `title="${TraceUtils.escapeHtml(tag.title)}"` : '';
            return `
                <div class="metadata-tag" ${titleAttr}>
                    <i class="bi ${tag.icon} me-1"></i>
                    <span class="metadata-tag-label">${TraceUtils.escapeHtml(tag.label)}:</span>
                    <span class="badge ${badgeClass} metadata-tag-value">${TraceUtils.escapeHtml(tag.value)}</span>
                </div>
            `;
        }).join('');

        return `
            <div class="tree-section metadata-tags-section">
                <div class="tree-section-title">
                    <i class="bi bi-tags me-2"></i>
                    Key Information
                </div>
                <div class="metadata-tags-container">
                    ${tagsHtml}
                </div>
            </div>
        `;
    }

    renderMetadataSection(title, metadata) {
        // Парсим LangChain данные для лучшего отображения
        const langchainSections = {};
        const otherMetadata = {};

        for (const [key, value] of Object.entries(metadata)) {
            if (key.startsWith('langchain.')) {
                langchainSections[key] = value;
            } else {
                otherMetadata[key] = value;
            }
        }

        // Парсим все LangChain секции
        for (const key in langchainSections) {
            langchainSections[key] = this.parseData(langchainSections[key]);
        }

        let sectionsHtml = '';

        // LangChain секции (в определенном порядке)
        const orderedKeys = [
            'langchain.inputs',
            'langchain.metadata',
            'langchain.outputs',
            'langchain.run_id',
            'langchain.tags',
            'langchain.type'
        ];

        // Сначала добавляем упорядоченные ключи
        for (const key of orderedKeys) {
            if (langchainSections[key]) {
                const displayKey = this.formatMetadataKey(key);
                sectionsHtml += this.renderTreeSection(displayKey, langchainSections[key], true);
            }
        }

        // Затем добавляем остальные LangChain ключи
        for (const [key, value] of Object.entries(langchainSections)) {
            if (!orderedKeys.includes(key)) {
                const displayKey = this.formatMetadataKey(key);
                sectionsHtml += this.renderTreeSection(displayKey, value, true);
            }
        }

        // Другие метаданные
        if (Object.keys(otherMetadata).length > 0) {
            sectionsHtml += this.renderTreeSection('Other Metadata', otherMetadata, true);
        }

        return sectionsHtml;
    }

    renderRawTab(span) {
        // Форматируем JSON с красивым выводом
        const formattedJson = TraceUtils.formatJson(span);
        return `
            <div class="raw-json-container">
                <div class="raw-json-header">
                    <button class="btn btn-sm btn-ghost copy-json-btn" type="button">
                        <i class="bi bi-clipboard"></i>
                        Copy JSON
                    </button>
                </div>
                <pre class="raw-json-content"><code class="json-content">${TraceUtils.escapeHtml(formattedJson)}</code></pre>
            </div>
        `;
    }

    renderEmpty() {
        this.container.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-cursor fs-1 mb-3"></i>
                <div>Выберите span для просмотра деталей</div>
            </div>
        `;
    }

    renderMessagesSection(title, messages) {
        if (!Array.isArray(messages)) {
            return '';
        }
        const messagesHtml = messages.map((msg) => {
            const messageType = msg.type || msg._originalType || 'unknown';
            const content = msg.content || '';
            let icon = '💬';
            let badge = messageType;
            if (messageType === 'human' || messageType === 'user') {
                icon = '👤';
                badge = 'user';
            } else if (messageType === 'ai' || messageType === 'assistant') {
                icon = '🤖';
                badge = 'ai';
            } else if (messageType === 'tool') {
                icon = '🔧';
                badge = 'tool';
            } else if (messageType === 'system') {
                icon = '⚙️';
                badge = 'system';
            }
            return `
                <div class="message-item">
                    <div class="message-header">
                        <span class="message-icon">${icon}</span>
                        <span class="message-type-badge">${badge}</span>
                        ${msg.name ? `<span class="message-name">${TraceUtils.escapeHtml(msg.name)}</span>` : ''}
                    </div>
                    <div class="message-content">
                        ${content ? this.renderMarkdownContent(content) : '<span class="text-muted">Empty message</span>'}
                    </div>
                    ${msg.tool_calls && msg.tool_calls.length > 0 ? `
                        <div class="message-tool-calls">
                            <div class="tool-calls-title">🔧 Tool Calls:</div>
                            ${msg.tool_calls.map(tc => `
                                <div class="tool-call-item">
                                    <code>${TraceUtils.escapeHtml(tc.name)}</code>
                                    <pre class="tool-call-args">${TraceUtils.formatJson(tc.args || {})}</pre>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                    ${msg.response_metadata ? `
                        <details class="message-metadata">
                            <summary>Response Metadata</summary>
                            <pre class="metadata-content">${TraceUtils.formatJson(msg.response_metadata)}</pre>
                        </details>
                    ` : ''}
                </div>
            `;
        }).join('');
        return `
            <div class="tree-section messages-section">
                <div class="tree-section-title">${title}</div>
                <div class="messages-container">
                    ${messagesHtml}
                </div>
            </div>
        `;
    }

    renderMarkdownContent(content) {
        if (!content) return '';
        let html = TraceUtils.escapeHtml(content);
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');
        html = html.replace(/\n/g, '<br>');
        return `<div class="markdown-content">${html}</div>`;
    }

    renderTreeSection(title, data, isFormatted = false) {
        if (!data) return '';

        // Всегда пытаемся отформатировать как JSON для объектов
        if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
            try {
                const formattedJson = TraceUtils.formatJson(data);
                return `
                    <div class="tree-section">
                        <div class="tree-section-title">${title}</div>
                        <div class="tree-content">
                            <pre class="metadata-json-content"><code class="json-content">${TraceUtils.escapeHtml(formattedJson)}</code></pre>
                        </div>
                    </div>
                `;
            } catch (e) {
                // Fallback на обычное дерево
            }
        }

        // Для массивов и других типов используем дерево
        return `
            <div class="tree-section">
                <div class="tree-section-title">${title}</div>
                <div class="tree-content">
                    ${this.renderTreeData(data, 0)}
                </div>
            </div>
        `;
    }

    renderTreeData(data, level = 0) {
        if (data === null || data === undefined) {
            return `<div class="tree-value tree-null">null</div>`;
        }
        if (typeof data === 'string') {
            return `<div class="tree-value tree-string">"${TraceUtils.escapeHtml(data)}"</div>`;
        }
        if (typeof data === 'number' || typeof data === 'boolean') {
            return `<div class="tree-value tree-primitive">${data}</div>`;
        }
        if (Array.isArray(data)) {
            if (data.length === 0) {
                return `<div class="tree-value tree-array">[]</div>`;
            }
            const itemsHtml = data.map((item, index) => `
                <div class="tree-node" data-level="${level}">
                    <div class="tree-node-header">
                        <button class="tree-toggle" type="button">
                            <i class="bi bi-chevron-right"></i>
                        </button>
                        <span class="tree-key">${index}</span>
                        <span class="tree-count">${this.getItemCount(item)}</span>
                    </div>
                    <div class="tree-node-content collapsed">
                        ${this.renderTreeData(item, level + 1)}
                    </div>
                </div>
            `).join('');
            return itemsHtml;
        }
        if (typeof data === 'object') {
            const entries = Object.entries(data);
            if (entries.length === 0) {
                return `<div class="tree-value tree-object">{}</div>`;
            }
            const itemsHtml = entries.map(([key, value]) => `
                <div class="tree-node" data-level="${level}">
                    <div class="tree-node-header">
                        ${this.isExpandable(value) ? `
                            <button class="tree-toggle" type="button">
                                <i class="bi bi-chevron-right"></i>
                            </button>
                        ` : '<span class="tree-toggle-spacer"></span>'}
                        <span class="tree-key">${TraceUtils.escapeHtml(key)}</span>
                        ${this.isExpandable(value) ? `
                            <span class="tree-count">${this.getItemCount(value)}</span>
                        ` : ''}
                    </div>
                    ${this.isExpandable(value) ? `
                        <div class="tree-node-content collapsed">
                            ${this.renderTreeData(value, level + 1)}
                        </div>
                    ` : `
                        <div class="tree-node-inline-value">
                            ${this.renderTreeData(value, level + 1)}
                        </div>
                    `}
                </div>
            `).join('');
            return itemsHtml;
        }
        return `<div class="tree-value">${TraceUtils.escapeHtml(String(data))}</div>`;
    }

    isExpandable(value) {
        if (value === null || value === undefined) return false;
        if (typeof value === 'object') {
            if (Array.isArray(value)) return value.length > 0;
            return Object.keys(value).length > 0;
        }
        return false;
    }

    getItemCount(value) {
        if (value === null || value === undefined) return '';
        if (Array.isArray(value)) {
            return value.length === 1 ? '1 item' : `${value.length} items`;
        }
        if (typeof value === 'object') {
            const count = Object.keys(value).length;
            return count === 1 ? '1 item' : `${count} items`;
        }
        return '';
    }

    attachEventListeners() {
        const toggles = this.container.querySelectorAll('.tree-toggle');
        for (const toggle of toggles) {
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const node = toggle.closest('.tree-node');
                const content = node.querySelector(':scope > .tree-node-content');
                const icon = toggle.querySelector('i');
                if (content) {
                    content.classList.toggle('collapsed');
                    icon.classList.toggle('bi-chevron-right');
                    icon.classList.toggle('bi-chevron-down');
                }
            });
        }

        const tabButtons = this.container.querySelectorAll('.span-details-tab');
        for (const button of tabButtons) {
            button.addEventListener('click', () => {
                const tabName = button.dataset.tab;
                this.switchTab(tabName);
            });
        }

        const copyBtn = this.container.querySelector('.copy-json-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                const jsonContent = this.container.querySelector('.raw-json-content code');
                if (jsonContent) {
                    navigator.clipboard.writeText(jsonContent.textContent).then(() => {
                        const originalHtml = copyBtn.innerHTML;
                        copyBtn.innerHTML = '<i class="bi bi-check"></i> Copied!';
                        setTimeout(() => {
                            copyBtn.innerHTML = originalHtml;
                        }, 2000);
                    });
                }
            });
        }
    }

    switchTab(tabName) {
        const tabButtons = this.container.querySelectorAll('.span-details-tab');
        for (const button of tabButtons) {
            if (button.dataset.tab === tabName) {
                button.classList.add('active');
            } else {
                button.classList.remove('active');
            }
        }
        const tabContents = this.container.querySelectorAll('.span-tab-content');
        for (const content of tabContents) {
            if (content.dataset.tabContent === tabName) {
                content.classList.add('active');
            } else {
                content.classList.remove('active');
            }
        }
    }

    formatMetadataKey(key) {
        // Форматируем ключи метаданных для читаемости
        return key
            .replace('langchain.', '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase())
            .replace(/Inputs/i, 'Inputs')
            .replace(/Outputs/i, 'Outputs')
            .replace(/Metadata/i, 'Metadata')
            .replace(/Run Id/i, 'Run ID')
            .replace(/Tags/i, 'Tags')
            .replace(/Type/i, 'Type');
    }
}

export default class TracesModule {
    constructor(app) {
        this.app = app;
        this.name = 'traces';
        this.version = '2.0.0';
        this.traceData = null;

        // Компоненты
        this.tree = null;
        this.timeline = null;
        this.details = null;
    }

    async init() {
        console.log('✅ Traces модуль инициализирован');
        this.setupGlobalAccess();
        this.setupEventListeners();
        return this;
    }

    setupGlobalAccess() {
        if (!globalThis.app) globalThis.app = {};
        globalThis.app.traces = this;
    }

    setupEventListeners() {
        document.addEventListener('htmx:afterSettle', (e) => {
            if (e.target.id === 'content' && this.isTracesPage()) {
                this.onPageLoad();
            }

            const modal = document.querySelector('.modal-overlay');
            if (modal && modal.querySelector('#trace-tree-container')) {
                this.initTraceDetailModal();
            }
        });
    }

    isTracesPage() {
        return window.location.pathname.startsWith('/frontend/traces');
    }

    onPageLoad() {
        console.log('🔄 Traces страница загружена');
    }

    initTraceDetailModal() {
        const modal = document.querySelector('.modal-overlay');
        if (!modal) return;

        const treeContainer = modal.querySelector('#trace-tree-container');
        const timelineContainer = modal.querySelector('#trace-timeline-container');
        const detailsContainer = modal.querySelector('#trace-detail-view');

        if (treeContainer && detailsContainer) {
            this.tree = new TraceTree(treeContainer, (spanId) => {
                this.onSpanSelect(spanId);
            });

            this.timeline = new TraceTimeline(timelineContainer, (spanId) => {
                this.onSpanSelect(spanId);
            });

            this.details = new SpanDetails(detailsContainer);
        }
    }

    initTraceDetail({ traceInfo, spans }) {
        console.log('🔍 Initializing trace detail:', { traceInfo, spansCount: spans?.length });

        this.traceData = { traceInfo, spans };

        const modal = document.querySelector('.modal-overlay');
        if (!modal) {
            console.error('❌ Modal not found');
            return;
        }

        const treeContainer = modal.querySelector('#trace-tree-container');
        const timelineContainer = modal.querySelector('#trace-timeline-container');
        const detailsContainer = modal.querySelector('#trace-detail-view');

        console.log('📦 Containers:', {
            treeContainer: !!treeContainer,
            timelineContainer: !!timelineContainer,
            detailsContainer: !!detailsContainer
        });

        if (treeContainer) {
            this.tree = new TraceTree(treeContainer, (spanId) => {
                this.onSpanSelect(spanId);
            });
            this.tree.build(spans);

            // Выбираем первый span после построения дерева
            if (spans.length > 0) {
                const firstSpan = spans.find(s => !s.parent_span_id) || spans[0];
                if (firstSpan) {
                    setTimeout(() => {
                        this.tree.selectSpan(firstSpan.span_id);
                        this.onSpanSelect(firstSpan.span_id);
                    }, 100);
                }
            }
        }

        if (timelineContainer && spans.length > 1) {
            console.log('🎨 Building timeline:', {
                container: !!timelineContainer,
                spansCount: spans.length,
                d3Available: typeof d3 !== 'undefined'
            });

            this.timeline = new TraceTimeline(timelineContainer, (spanId) => {
                this.onSpanSelect(spanId);
            });
            this.timeline.build(spans).catch(err => {
                console.error('❌ Error building timeline:', err);
            });
        }

        if (detailsContainer) {
            this.details = new SpanDetails(detailsContainer);
        }
    }

    onSpanSelect(spanId) {
        console.log('🎯 Span selected:', spanId);

        if (!this.traceData?.spans) {
            console.error('❌ No trace data');
            return;
        }

        const span = this.traceData.spans.find(s => s.span_id === spanId);
        if (!span) {
            console.error('❌ Span not found:', spanId);
            return;
        }

        console.log('✅ Rendering span:', span.name);

        // Синхронизируем выделение между tree и timeline (БЕЗ вызова callback)
        if (this.tree) {
            this.tree.selectSpan(spanId, false);
        }
        if (this.timeline) {
            this.timeline.selectSpan(spanId);
        }

        // Обновляем Details
        if (this.details) {
            this.details.render(span);
        }
    }

    destroy() {
        console.log('🧹 Traces модуль выгружен');
        this.tree = null;
        this.timeline = null;
        this.details = null;
        this.traceData = null;
    }
}
