import { useEffect, useState } from 'react'
import { Moon, Sun, SunMoon } from 'lucide-react'

type Theme = 'system' | 'light' | 'dark'
const ORDER: Theme[] = ['system', 'light', 'dark']
const KEY = 'water-theme'

function stored(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

/** System / light / dark, remembered per browser. Dark tokens live in index.css. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(stored)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') delete root.dataset.theme
    else root.dataset.theme = theme
    try {
      if (theme === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, theme)
    } catch {
      // Storage unavailable (private mode): the choice lasts for this visit
    }
  }, [theme])

  const Icon = theme === 'light' ? Sun : theme === 'dark' ? Moon : SunMoon
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="grid h-9 w-9 place-items-center rounded-full text-white/80 transition hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
      aria-label={`Theme: ${theme}. Switch to ${next}.`}
      title={`Theme: ${theme}`}
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  )
}
