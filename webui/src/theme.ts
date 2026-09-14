export function readStoredDark(): boolean {
  try {
    return localStorage.getItem('theme') !== 'light'
  } catch {
    return true
  }
}

export function applyTheme(isDark: boolean): void {
  if (isDark) {
    document.documentElement.removeAttribute('data-theme')
  } else {
    document.documentElement.setAttribute('data-theme', 'light')
  }
}

export function bootTheme(): void {
  applyTheme(readStoredDark())
}
