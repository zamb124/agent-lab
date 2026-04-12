/**
 * Lighthouse CI: URL задаётся через PWA_LIGHTHOUSE_URL (полный URL страницы для съёма).
 * Пример: PWA_LIGHTHOUSE_URL=https://humanitec.ru/
 */
const url = process.env.PWA_LIGHTHOUSE_URL;
if (!url || String(url).trim() === "") {
  throw new Error(
    "Задайте PWA_LIGHTHOUSE_URL (например https://humanitec.ru/)"
  );
}

module.exports = {
  ci: {
    collect: {
      url: [url.trim()],
      numberOfRuns: 1,
    },
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.3 }],
        "categories:pwa": ["warn", { minScore: 0.75 }],
        "categories:accessibility": ["warn", { minScore: 0.8 }],
        "categories:best-practices": ["warn", { minScore: 0.75 }],
        "categories:seo": ["warn", { minScore: 0.8 }],
      },
    },
  },
};
