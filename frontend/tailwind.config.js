/** @type {import('tailwindcss').Config} */

// Every color is a role backed by a CSS variable in src/index.css, which
// carries the light and dark values.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        page: token('page'),
        surface: token('surface'),
        'surface-2': token('surface-2'),
        ink: token('ink'),
        'ink-2': token('ink-2'),
        muted: token('muted'),
        grid: token('grid'),
        axis: token('axis'),
        line: token('line'),
        accent: token('accent'),
        'accent-soft': token('accent-soft'),
        status: {
          good: token('good'),
          warning: token('warning'),
          serious: token('serious'),
          critical: token('critical'),
        },
      },
    },
  },
  plugins: [],
}
