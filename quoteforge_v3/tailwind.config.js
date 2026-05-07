/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic tokens — resolved to CSS variables in theme.css.
        app:              'var(--bg-app)',
        surface:          'var(--bg-surface)',
        subtle:           'var(--bg-subtle)',
        muted:            'var(--bg-muted)',
        border:           'var(--border)',
        'border-strong':  'var(--border-strong)',
        accent:           'var(--accent)',
        'accent-hover':   'var(--accent-hover)',
        'accent-muted':   'var(--accent-muted)',
        'accent-fg':      'var(--accent-fg)',
        success:          'var(--success)',
        'success-muted':  'var(--success-muted)',
        warning:          'var(--warning)',
        'warning-muted':  'var(--warning-muted)',
        danger:           'var(--danger)',
        'danger-muted':   'var(--danger-muted)',
        'text-primary':   'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted':     'var(--text-muted)',
        'text-inverse':   'var(--text-inverse)',

        // Back-compat: brand-* now resolves to accent tokens so legacy
        // pages keep rendering during the transition.
        brand: {
          50:  'var(--accent-muted)',
          100: 'var(--accent-muted)',
          500: 'var(--accent)',
          600: 'var(--accent)',
          700: 'var(--accent-hover)',
          800: 'var(--accent-hover)',
        },
        // Sidebar tokens — pinned dark in both themes (branded surface).
        sidebar: {
          DEFAULT: '#0A0A0B',
          hover:   '#1C1C21',
          border:  '#27272A',
          text:    '#A1A1AA',
          active:  '#FAFAFA',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        DEFAULT: '4px',
        sm:  '2px',
        md:  '4px',
        lg:  '6px',
        xl:  '8px',
        '2xl': '8px',
      },
      boxShadow: {
        // Kept names for back-compat; nearly flat now — borders do the work.
        card:       '0 1px 2px rgba(0,0,0,0.04)',
        'card-hover':'0 1px 2px rgba(0,0,0,0.06)',
        dropdown:   'var(--shadow-pop)',
        pop:        'var(--shadow-pop)',
      },
      transitionDuration: { DEFAULT: '120ms' },
    },
  },
  plugins: [],
};
