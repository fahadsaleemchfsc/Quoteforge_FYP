import { Sun, Moon, Monitor } from 'lucide-react';
import clsx from 'clsx';
import { useTheme } from '@/context/ThemeContext';

// Three-icon segmented control for light / dark / system.
// Always visible in the top bar — not hidden in a dropdown.
const OPTIONS = [
  { value: 'light',  Icon: Sun,     label: 'Light theme'  },
  { value: 'dark',   Icon: Moon,    label: 'Dark theme'   },
  { value: 'system', Icon: Monitor, label: 'System theme' },
];

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="inline-flex border border-border rounded overflow-hidden bg-surface"
    >
      {OPTIONS.map(({ value, Icon, label }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={clsx(
              'w-8 h-7 inline-flex items-center justify-center border-r border-border last:border-r-0 transition-colors',
              active
                ? 'bg-accent-muted text-accent'
                : 'bg-surface text-text-muted hover:bg-subtle hover:text-text-primary',
            )}
          >
            <Icon size={14} strokeWidth={active ? 2.2 : 1.8} />
          </button>
        );
      })}
    </div>
  );
}
