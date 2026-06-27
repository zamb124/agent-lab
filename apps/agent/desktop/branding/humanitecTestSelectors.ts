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
      const label = button.textContent;
      if (label === null) {
        continue;
      }
      if (label.includes("MCP") && !button.hasAttribute("data-humanitec-mcp-picker")) {
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
