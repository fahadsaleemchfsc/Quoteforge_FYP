import clsx from 'clsx';

// Semantic-colored inline label. 2px radius, tight padding, small-caps.
// variant maps to our token palette.
const STYLES = {
  accent:  { bg: 'var(--accent-muted)',  fg: 'var(--accent)' },
  success: { bg: 'var(--success-muted)', fg: 'var(--success)' },
  warning: { bg: 'var(--warning-muted)', fg: 'var(--warning)' },
  danger:  { bg: 'var(--danger-muted)',  fg: 'var(--danger)' },
  muted:   { bg: 'var(--bg-subtle)',     fg: 'var(--text-secondary)' },
};

export default function Pill({ variant = 'muted', className = '', caps = true, children, mono = false }) {
  const s = STYLES[variant] || STYLES.muted;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-1.5 py-0.5 font-medium',
        caps && 'uppercase tracking-wider',
        mono && 'font-mono',
        className,
      )}
      style={{
        backgroundColor: s.bg,
        color: s.fg,
        borderRadius: '2px',
        fontSize: caps ? '10.5px' : '11.5px',
        letterSpacing: caps ? '0.06em' : undefined,
      }}
    >
      {children}
    </span>
  );
}
