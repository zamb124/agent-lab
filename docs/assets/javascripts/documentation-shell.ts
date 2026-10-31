interface DocsAssistantEmbed {
    setMetadataHooks(hooks: () => Promise<Record<string, string | number>>): void;
    setLocale(locale: string): void;
    setAssistantTitle(title: string): void;
}

declare global {
    interface Window {
        linnexFlowUI?: DocsAssistantEmbed;
        __docsAssistantLoading?: Promise<DocsAssistantEmbed> | null;
        document$?: { subscribe(fn: () => void): void };
    }
}

export {};

(() => {
  const labels = () => {
    const isRu = (document.documentElement.lang || "").toLowerCase().startsWith("ru");
    return isRu
      ? {
          copy: "Копировать ссылку",
          copied: "Скопировано",
          failed: "Не удалось",
          assistantFailed: "AI-помощник недоступен",
        }
      : {
          copy: "Copy page",
          copied: "Copied",
          failed: "Copy failed",
          assistantFailed: "AI assistant unavailable",
        };
  };

  const docsLanguage = (): string => {
    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("en") || window.location.pathname.includes("/documentation/en/")) {
      return "en";
    }
    return "ru";
  };

  const enhanceCopyPage = () => {
    const article = document.querySelector(".md-content__inner");
    const title = article && article.querySelector("h1");
    if (!article || !title || article.querySelector(".docs-copy-page")) return;
    const text = labels();

    const button = document.createElement("button");
    button.type = "button";
    button.className = "docs-copy-page";
    button.setAttribute("aria-label", text.copy);
    button.innerHTML = `<span>${text.copy}</span>`;
    title.insertAdjacentElement("afterend", button);

    button.addEventListener("click", async () => {
      const label = button.querySelector("span");
      if (!label) return;
      try {
        await navigator.clipboard.writeText(window.location.href);
        button.classList.add("is-copied");
        label.textContent = text.copied;
        window.setTimeout(() => {
          button.classList.remove("is-copied");
          label.textContent = text.copy;
        }, 1600);
      } catch (_) {
        label.textContent = text.failed;
      }
    });
  };

  const markExternalLinks = () => {
    document.querySelectorAll<HTMLAnchorElement>(".md-content a[href^='http']").forEach((link) => {
      if (link.hostname !== window.location.hostname) {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      }
    });
  };

  const normalizeGeneratedLabels = () => {
    const isRu = (document.documentElement.lang || "").toLowerCase().startsWith("ru");
    const replacements = new Map<string, string>([
      ["Crm", "NetWorkle"],
      [
        "Crm shell",
        isRu ? "NetWorkle: оболочка записной книжки" : "NetWorkle: notebook shell",
      ],
      [
        "Crm settings hub",
        isRu ? "NetWorkle: хаб настроек" : "NetWorkle: settings hub",
      ],
    ]);

    document.querySelectorAll(".md-nav__link .md-ellipsis, .md-nav__title").forEach((node) => {
      const current = (node.textContent || "").replace(/\s+/g, " ").trim();
      const replacement = replacements.get(current);
      if (!replacement) return;

      const ellipsis = node.matches(".md-ellipsis") ? node : node.querySelector(".md-ellipsis");
      if (ellipsis) {
        ellipsis.textContent = replacement;
        return;
      }

      for (const child of Array.from(node.childNodes)) {
        if (child.nodeType === Node.TEXT_NODE && (child.textContent || "").trim()) {
          child.textContent = ` ${replacement} `;
          return;
        }
      }
    });
  };

  const waitForDocsAssistant = () => new Promise<DocsAssistantEmbed>((resolve, reject) => {
    if (window.linnexFlowUI) {
      resolve(window.linnexFlowUI);
      return;
    }
    const timer = window.setTimeout(() => {
      window.removeEventListener("linnex-flow-ui-mounted", onMounted);
      reject(new Error("docs assistant mount timeout"));
    }, 8000);
    const onMounted = () => {
      window.clearTimeout(timer);
      window.removeEventListener("linnex-flow-ui-mounted", onMounted);
      if (!window.linnexFlowUI) {
        reject(new Error("docs assistant mount missing linnexFlowUI"));
        return;
      }
      resolve(window.linnexFlowUI);
    };
    window.addEventListener("linnex-flow-ui-mounted", onMounted);
  });

  const configureDocsAssistantMetadata = (embed: DocsAssistantEmbed | undefined) => {
    if (!embed || typeof embed.setMetadataHooks !== "function") {
      throw new Error("docs assistant: linnexFlowUI.setMetadataHooks is required");
    }
    embed.setMetadataHooks(async () => ({
      page_url: window.location.href,
      page_title: document.title,
      docs_language: docsLanguage(),
      docs_path: window.location.pathname,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
    }));
    embed.setLocale(docsLanguage());
    embed.setAssistantTitle("Ask AI");
  };

  const platformUiOrigin = (): string => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="docs-platform-ui-origin"]');
    const fromMeta = meta && typeof meta.content === "string" ? meta.content.trim() : "";
    if (fromMeta) {
      return fromMeta.replace(/\/+$/, "");
    }
    return window.location.origin;
  };

  const assertJavascriptModuleUrl = async (url: string) => {
    const response = await fetch(url, { method: "GET", cache: "no-store" });
    const contentType = (response.headers.get("content-type") || "").toLowerCase();
    if (!response.ok) {
      throw new Error(`docs assistant script HTTP ${response.status}`);
    }
    if (!contentType.includes("javascript") && !contentType.includes("ecmascript")) {
      throw new Error(
        `docs assistant script MIME ${contentType || "unknown"} (нужен /static/core на origin платформы, не zensical serve)`,
      );
    }
  };

  const ensureDocsAssistantLoaded = async (): Promise<DocsAssistantEmbed> => {
    if (window.linnexFlowUI) {
      configureDocsAssistantMetadata(window.linnexFlowUI);
      return window.linnexFlowUI;
    }
    if (window.__docsAssistantLoading) {
      const embed = await window.__docsAssistantLoading;
      configureDocsAssistantMetadata(embed);
      return embed;
    }

    const origin = platformUiOrigin();
    const scriptUrl = `${origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js`;

    window.__docsAssistantLoading = (async () => {
      await assertJavascriptModuleUrl(scriptUrl);
      const embed = await new Promise<DocsAssistantEmbed>((resolve, reject) => {
        const script = document.createElement("script");
        script.type = "module";
        script.src = scriptUrl;
        script.dataset.embedId = "docs_assistant";
        script.dataset.presentation = "drawer";
        script.dataset.position = "bottom-right";
        script.dataset.theme = "light";
        script.dataset.locale = docsLanguage();
        script.dataset.showLauncher = "false";
        script.dataset.initialOpen = "false";
        script.dataset.flowsBaseUrl = `${origin}/flows`;
        script.dataset.platformUiOrigin = origin;
        script.dataset.tokenUrl = `${origin}/frontend/api/public/docs-assistant/session`;
        script.dataset.tokenExpiresSeconds = "600";
        script.dataset.useCredentials = "false";
        script.dataset.toggleEventName = "linnex-docs-assistant-toggle";
        script.onload = async () => {
          try {
            resolve(await waitForDocsAssistant());
          } catch (error) {
            reject(error);
          }
        };
        script.onerror = () => reject(new Error("cannot load docs assistant script"));
        document.head.appendChild(script);
      });
      configureDocsAssistantMetadata(embed);
      return embed;
    })();

    try {
      return await window.__docsAssistantLoading;
    } catch (error) {
      window.__docsAssistantLoading = null;
      throw error;
    }
  };

  const bindDocsAssistant = () => {
    document.querySelectorAll("[data-docs-ask-ai]").forEach((node) => {
      if (!(node instanceof HTMLButtonElement) || node.dataset.docsAskAiBound === "true") {
        return;
      }
      node.dataset.docsAskAiBound = "true";
      node.addEventListener("click", async () => {
        const text = labels();
        try {
          node.disabled = true;
          await ensureDocsAssistantLoaded();
          configureDocsAssistantMetadata(window.linnexFlowUI);
          window.dispatchEvent(
            new CustomEvent("linnex-docs-assistant-toggle", {
              detail: { open: true },
            }),
          );
        } catch (_) {
          node.setAttribute("title", text.assistantFailed);
        } finally {
          node.disabled = false;
        }
      });
    });
  };

  const boot = () => {
    enhanceCopyPage();
    markExternalLinks();
    normalizeGeneratedLabels();
    bindDocsAssistant();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(boot);
  }
})();
