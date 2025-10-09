/**
 * Утилиты для рендеринга Markdown
 */

export function renderMarkdown(markdown) {
    let html = markdown;
    
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    const lines = html.split('\n');
    const result = [];
    let inOrderedList = false;
    let inUnorderedList = false;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (/^\d+\.\s+/.test(trimmedLine)) {
            if (!inOrderedList) {
                result.push('<ol>');
                inOrderedList = true;
            }
            if (inUnorderedList) {
                result.push('</ul>');
                inUnorderedList = false;
            }
            result.push('<li>' + trimmedLine.replace(/^\d+\.\s+/, '') + '</li>');
        }
        else if (/^[-*]\s+/.test(trimmedLine)) {
            if (!inUnorderedList) {
                result.push('<ul>');
                inUnorderedList = true;
            }
            result.push('<li>' + trimmedLine.replace(/^[-*]\s+/, '') + '</li>');
        }
        else {
            if (inOrderedList && trimmedLine === '') {
                result.push('</ol>');
                inOrderedList = false;
            }
            if (inUnorderedList && trimmedLine === '') {
                result.push('</ul>');
                inUnorderedList = false;
            }
            
            if (trimmedLine === '') {
                result.push('<br>');
            } else if (!trimmedLine.startsWith('<h')) {
                result.push(line);
            } else {
                result.push(line);
            }
        }
    }
    
    if (inOrderedList) result.push('</ol>');
    if (inUnorderedList) result.push('</ul>');
    
    return result.join('\n');
}

export function sanitizeHTML(html) {
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
}

