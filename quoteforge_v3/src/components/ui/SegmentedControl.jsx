import clsx from 'clsx';

// Linked-buttons tab control. Replaces the previous filter-btn groups.
// options: [{ value, label, count? }]
export default function SegmentedControl({ options, active, onChange, size = 'md', className = '' }) {
  const sz = size === 'sm'
    ? 'text-[11.5px] h-7 px-2.5'
    : 'text-[12.5px] h-8 px-3';
  return (
    <div
      className={clsx('inline-flex border border-border rounded overflow-hidden bg-surface', className)}
      role="tablist"
    >
      {options.map((opt, i) => {
        const isActive = opt.value === active;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(opt.value)}
            className={clsx(
              'inline-flex items-center gap-1.5 font-medium border-r border-border last:border-r-0 transition-colors',
              sz,
              isActive
                ? 'bg-accent-muted text-accent'
                : 'bg-surface text-text-secondary hover:bg-subtle hover:text-text-primary',
            )}
          >
            <span className={isActive ? 'font-semibold' : ''}>{opt.label}</span>
            {opt.count != null && (
              <span
                className="font-mono text-[10.5px] tabular-nums"
                style={{ color: isActive ? 'var(--accent)' : 'var(--text-muted)' }}
              >
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
