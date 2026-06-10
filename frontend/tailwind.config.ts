import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

/**
 * Tailwind CSS configuration.
 *
 * Scans both frontend source files and Flask templates
 * to ensure all utility classes are included in the build.
 * The typography plugin provides the `prose` classes used to style
 * Markdown-rendered page content.
 */
export default {
  content: [
    './src/**/*.{js,ts,jsx,tsx}',
    '../src/app/templates/**/*.html',
  ],
  theme: {
    extend: {},
  },
  plugins: [typography],
} satisfies Config
