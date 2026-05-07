import clsx from 'clsx';

// Small 24×14 switch. Accent violet when on.
export default function Toggle({ checked, onChange, disabled = false, className = '', ariaLabel }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={clsx(
        'relative inline-flex items-center transition-colors duration-120 flex-shrink-0',
        disabled && 'opacity-50 cursor-not-allowed',
        !disabled && 'cursor-pointer',
        className,
      )}
      style={{
        width: 24, height: 14, borderRadius: 999,
        background: checked ? 'var(--accent)' : 'var(--bg-muted)',
        padding: 2,
      }}
    >
      <span
        className="inline-block transition-transform duration-120"
        style={{
          width: 10, height: 10, borderRadius: 999,
          background: 'var(--bg-surface)',
          transform: `translateX(${checked ? 10 : 0}px)`,
        }}
      />
    </button>
  );
}
