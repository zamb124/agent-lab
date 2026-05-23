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

  const docsLanguage = () => {
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
      try {
        await navigator.clipboard.writeText(window.location.href);
        button.classList.add("is-copied");
        button.querySelector("span").textContent = text.copied;
        window.setTimeout(() => {
          button.classList.remove("is-copied");
          button.querySelector("span").textContent = text.copy;
        }, 1600);
      } catch (_) {
        button.querySelector("span").textContent = text.failed;
      }
    });
  };

  const markExternalLinks = () => {
    document.querySelectorAll(".md-content a[href^='http']").forEach((link) => {
      if (link.hostname !== window.location.hostname) {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      }
    });
  };

  const normalizeGeneratedLabels = () => {
    const isRu = (document.documentElement.lang || "").toLowerCase().startsWith("ru");
    const replacements = new Map([
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
        if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
          child.textContent = ` ${replacement} `;
          return;
        }
      }
    });
  };

  const nextFrame = () => new Promise((resolve) => window.requestAnimationFrame(resolve));

  const waitForDocsAssistant = async () => {
    const startedAt = Date.now();
    while (Date.now() - startedAt <= 8000) {
      if (window.humanitecEmbed && window.humanitecEmbed.element) {
        const assistant = window.humanitecEmbed.element;
        if (assistant.updateComplete && typeof assistant.updateComplete.then === "function") {
          await assistant.updateComplete;
        }
        const drawer = assistant.querySelector("platform-embed-chat-drawer");
        if (drawer && drawer.updateComplete && typeof drawer.updateComplete.then === "function") {
          await drawer.updateComplete;
        }
        return window.humanitecEmbed;
      }
      await nextFrame();
    }
    throw new Error("docs assistant mount timeout");
  };

  const configureDocsAssistantMetadata = (embed) => {
    if (!embed || typeof embed.setMetadataHooks !== "function") return;
    const extraMetadata = async () => ({
      page_url: window.location.href,
      page_title: document.title,
      docs_language: docsLanguage(),
      docs_path: window.location.pathname,
    });
    const contextVariables = async () => ({
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
    });
    embed.setMetadataHooks(extraMetadata, contextVariables);
    if (typeof embed.setLocale === "function") {
      embed.setLocale(docsLanguage());
    }
  };

  const ensureDocsAssistantLoaded = async () => {
    if (window.humanitecEmbed && window.humanitecEmbed.element) {
      configureDocsAssistantMetadata(window.humanitecEmbed);
      return window.humanitecEmbed;
    }
    if (window.__docsAssistantLoading) {
      const embed = await window.__docsAssistantLoading;
      configureDocsAssistantMetadata(embed);
      return embed;
    }

    window.__docsAssistantLoading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.type = "module";
      script.src = "/static/core/lib/embed-chat/humanitec-embed-autoload.js";
      script.dataset.embedId = "docs_assistant";
      script.dataset.flowId = "lara";
      script.dataset.branchId = "docs";
      script.dataset.assistantTitle = "Ask AI";
      script.dataset.theme = "light";
      script.dataset.locale = docsLanguage();
      script.dataset.showLauncher = "false";
      script.dataset.initialOpen = "false";
      script.dataset.flowsBaseUrl = "/flows";
      script.dataset.platformUiOrigin = window.location.origin;
      script.dataset.chatTokenUrl = "/frontend/api/public/docs-assistant/session";
      script.dataset.tokenExpiresSeconds = "600";
      script.dataset.eventNamespace = "docs-assistant";
      script.dataset.toggleEventName = "humanitec-docs-assistant-toggle";
      script.onload = async () => {
        try {
          const embed = await waitForDocsAssistant();
          configureDocsAssistantMetadata(embed);
          resolve(embed);
        } catch (error) {
          reject(error);
        }
      };
      script.onerror = () => reject(new Error("cannot load docs assistant script"));
      document.head.appendChild(script);
    });

    return window.__docsAssistantLoading;
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
          configureDocsAssistantMetadata(window.humanitecEmbed);
          window.dispatchEvent(
            new CustomEvent("humanitec-docs-assistant-toggle", {
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
