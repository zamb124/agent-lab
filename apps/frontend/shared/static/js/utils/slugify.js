/**
 * Утилита для создания slug из текста
 */

const translitMap = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
};

export function slugify(text) {
    let slug = text
        .toString()
        .toLowerCase()
        .trim()
        .split('')
        .map(char => translitMap[char] || char)
        .join('')
        .replace(/\s+/g, '_')
        .replace(/[^\w\-]+/g, '')
        .replace(/\_\_+/g, '_')
        .replace(/^_+|_+$/g, '');
    
    if (!slug || slug.length < 2) {
        slug = 'item';
    }
    
    return slug;
}

export function generateUniqueId(baseName = 'item') {
    const slug = slugify(baseName);
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 6);
    return `${slug}_${timestamp}${random}`;
}

