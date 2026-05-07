import clsx from 'clsx';

// Border-only card. Sharp 4px corners. No drop shadow.
// The operator-tool aesthetic lives in this one component — everything else
// composes from here.
export default function Panel({ className = '', children, title, subtitle, actions, padded = true }) {
  return (
    <section
      className={clsx(
        'bg-surface border border-border rounded',
        className,
      )}
    >
      {(title || subtitle || actions) && (
        <header className="flex items-start justify-between px-5 py-3 border-b border-border">
          <div className="min-w-0">
            {title && (
              <div className="text-[13px] font-semibold text-text-primary tracking-tight">
                {title}
              </div>
            )}
            {subtitle && (
              <div className="text-[12px] text-text-secondary mt-0.5">{subtitle}</div>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'p-5' : ''}>{children}</div>
    </section>
  );
}
