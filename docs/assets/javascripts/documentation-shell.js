(() => {
  const labels = () => {
    const isRu = (document.documentElement.lang || "").toLowerCase().startsWith("ru");
    return isRu
      ? { copy: "Копировать ссылку", copied: "Скопировано", failed: "Не удалось" }
      : { copy: "Copy page", copied: "Copied", failed: "Copy failed" };
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

  const boot = () => {
    enhanceCopyPage();
    markExternalLinks();
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
