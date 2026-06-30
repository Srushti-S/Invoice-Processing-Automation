/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#faf9f7',
        ink: '#1f2421',
        muted: '#6b7280',
        line: '#e7e5e0',
        accent: '#2f6f5e',
        ok: '#2f7a55',
        reject: '#b3261e',
        review: '#8a6d1f',
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
