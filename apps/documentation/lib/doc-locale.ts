import type { TranslationsOption } from 'fumadocs-ui/contexts/i18n';

export type DocLocale = 'ru' | 'en';

export const DOC_LOCALE_STORAGE_KEY = 'humanitec-documentation-locale';

export const DOC_LOCALES: { name: string; locale: DocLocale }[] = [
  { name: 'Русский', locale: 'ru' },
  { name: 'English', locale: 'en' },
];

const GUIDE_LOCALE = /^guides\/(ru|en)(\/|$)/;

export function docLocaleFromPathname(pathname: string): DocLocale | null {
  const trimmed = pathname.replace(/^\/+|\/+$/g, '');
  const match = GUIDE_LOCALE.exec(trimmed);
  if (!match) {
    return null;
  }
  return match[1] as DocLocale;
}

/**
 * Сегменты пути без ведущего и завершающего слэша (как в usePathname с basePath).
 */
function pathSegments(pathname: string): string[] {
  const trimmed = pathname.replace(/^\/+|\/+$/g, '');
  return trimmed ? trimmed.split('/').filter(Boolean) : [];
}

/**
 * Целевой путь с учётом `trailingSlash: true` в Next.
 */
export function hrefForDocLocale(pathname: string, next: DocLocale): string {
  const segments = pathSegments(pathname);
  if (segments[0] === 'guides' && (segments[1] === 'ru' || segments[1] === 'en')) {
    segments[1] = next;
    return `/${segments.join('/')}/`;
  }
  return `/guides/${next}/`;
}

export function readStoredDocLocale(): DocLocale | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const raw = window.localStorage.getItem(DOC_LOCALE_STORAGE_KEY);
  if (raw === 'ru' || raw === 'en') {
    return raw;
  }
  return null;
}

export function writeStoredDocLocale(locale: DocLocale): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(DOC_LOCALE_STORAGE_KEY, locale);
}

export const DOC_UI_STRINGS: Record<DocLocale, TranslationsOption> = {
  ru: {
    search: 'Поиск',
    searchNoResult: 'Ничего не найдено',
    toc: 'На этой странице',
    tocNoHeadings: 'Нет заголовков',
    lastUpdate: 'Обновлено',
    chooseLanguage: 'Язык',
    nextPage: 'Следующая страница',
    previousPage: 'Предыдущая страница',
    chooseTheme: 'Тема',
    editOnGithub: 'Редактировать на GitHub',
  },
  en: {
    search: 'Search',
    searchNoResult: 'No results found',
    toc: 'On this page',
    tocNoHeadings: 'No Headings',
    lastUpdate: 'Last updated on',
    chooseLanguage: 'Language',
    nextPage: 'Next Page',
    previousPage: 'Previous Page',
    chooseTheme: 'Theme',
    editOnGithub: 'Edit on GitHub',
  },
};
