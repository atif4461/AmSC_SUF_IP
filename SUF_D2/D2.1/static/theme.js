(() => {
  const KEY = "amsc-theme";
  const toggleBtn = document.getElementById("theme-toggle-btn");

  const getTheme = () => {
    const saved = localStorage.getItem(KEY);
    return saved === "dark" || saved === "light" ? saved : "light";
  };

  const renderToggle = (theme) => {
    if (!toggleBtn) return;

    const isDark = theme === "dark";
    toggleBtn.textContent = isDark ? "☀️ Light" : "🌙 Dark";
    toggleBtn.setAttribute("aria-pressed", String(isDark));
    toggleBtn.setAttribute(
      "aria-label",
      isDark ? "Switch to light theme" : "Switch to dark theme"
    );
    toggleBtn.title = isDark ? "Switch to light theme" : "Switch to dark theme";
  };

  const applyTheme = (theme) => {
    document.documentElement.setAttribute("data-bs-theme", theme);
    localStorage.setItem(KEY, theme);
    renderToggle(theme);
  };

  applyTheme(getTheme());

  if (!toggleBtn) {
    return;
  }

  toggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-bs-theme") || "light";
    applyTheme(current === "dark" ? "light" : "dark");
  });
})();
