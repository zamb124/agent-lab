export function installHumanitecTestSelectors(): void {
  if (typeof document === 'undefined') {
    return;
  }
  const apply = (): void => {
    const composer = document.querySelector("textarea");
    if (composer !== null && !composer.hasAttribute("data-humanitec-chat-composer")) {
      composer.setAttribute("data-humanitec-chat-composer", "1");
    }
    const buttons = document.querySelectorAll("button");
    for (const button of buttons) {
      const label = button.textContent ?? "";
      // Composer extension-picker кнопка (ExtensionMenu) — Puzzle-иконка + счётчик
      // (только цифры). Sidebar nav-пункт "Extensions" тоже использует Puzzle,
      // но его label — локализованное название, не число.
      const hasPuzzleIcon = button.querySelector("svg.lucide-puzzle") !== null;
      const isComposerExtensionPicker = hasPuzzleIcon && /^\d+$/.test(label.trim());
      if (isComposerExtensionPicker && !button.hasAttribute("data-humanitec-mcp-picker")) {
        button.setAttribute("data-humanitec-mcp-picker", "1");
      }
      if (label.trim() === "Send" && !button.hasAttribute("data-humanitec-chat-send")) {
        button.setAttribute("data-humanitec-chat-send", "1");
      }
    }
  };
  apply();
  window.setInterval(apply, 1000);
}
