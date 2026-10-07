'use strict';
const themeKey = 'audiotheca-project-hub-theme';
const button = document.getElementById('theme-toggle');
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(themeKey, theme); } catch {}
  if (button) {
    button.textContent = theme === 'dark' ? 'Dark mode' : 'Light mode';
    button.setAttribute('aria-pressed', String(theme === 'light'));
  }
}
setTheme(document.documentElement.dataset.theme || 'dark');
button?.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
fetch('/api/status', { cache: 'no-store' }).then(response => {
  if (!response.ok) throw new Error('status unavailable');
  return response.json();
}).then(status => {
  const setText = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
  setText('git-branch', status.branch);
  setText('git-commit', status.commit);
  setText('changed-files', status.changed_files === null ? 'Unavailable' : String(status.changed_files));
  setText('checked-at', new Date(status.checked_at).toLocaleString());
}).catch(() => {
  for (const id of ['git-branch', 'git-commit', 'changed-files']) {
    const node = document.getElementById(id);
    if (node) node.textContent = 'Unavailable';
  }
});
