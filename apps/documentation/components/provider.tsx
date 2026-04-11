'use client';

import SearchDialog from '@/components/search';
import {
  DOC_LOCALES,
  DOC_UI_STRINGS,
  type DocLocale,
  docLocaleFromPathname,
  hrefForDocLocale,
  readStoredDocLocale,
  writeStoredDocLocale,
} from '@/lib/doc-locale';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

export function Provider({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/';
  const router = useRouter();

  const [storedLocale, setStoredLocale] = useState<DocLocale | null>(null);
  useEffect(() => {
    setStoredLocale(readStoredDocLocale());
  }, []);

  const fromPath = docLocaleFromPathname(pathname);
  const activeLocale: DocLocale = useMemo(() => {
    if (fromPath) {
      return fromPath;
    }
    if (storedLocale) {
      return storedLocale;
    }
    if (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('en')) {
      return 'en';
    }
    return 'ru';
  }, [fromPath, storedLocale]);

  useEffect(() => {
    if (fromPath) {
      writeStoredDocLocale(fromPath);
    }
  }, [fromPath]);

  useEffect(() => {
    document.documentElement.lang = activeLocale === 'en' ? 'en' : 'ru';
  }, [activeLocale]);

  const onLocaleChange = useCallback(
    (value: string) => {
      if (value !== 'ru' && value !== 'en') {
        throw new Error(`Неподдерживаемый язык документации: ${value}`);
      }
      const next = value as DocLocale;
      writeStoredDocLocale(next);
      const target = hrefForDocLocale(pathname, next);
      router.push(target);
    },
    [pathname, router],
  );

  return (
    <RootProvider
      search={{ SearchDialog }}
      theme={{
        storageKey: 'humanitec-documentation-theme',
        defaultTheme: 'system',
        enableSystem: true,
      }}
      i18n={{
        locale: activeLocale,
        locales: DOC_LOCALES,
        onLocaleChange,
        translations: DOC_UI_STRINGS[activeLocale],
      }}
    >
      {children}
    </RootProvider>
  );
}
