/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        sidebar: {
          DEFAULT: '#0f172a',
          hover: '#1e293b',
          border: '#1e293b',
          text: '#94a3b8',
          active: '#e2e8f0',
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"SF Mono"', '"Fira Code"', '"Cascadia Code"', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease',
        'fade-slide-up': 'fadeSlideUp 0.4s ease',
        'slide-in-right': 'slideInRight 0.3s ease',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        fadeSlideUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          from: { opacity: '0', transform: 'translateX(20px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
};
