import clsx from 'clsx';

const STATUS_CONFIG = {
  active:       { bg: 'bg-success-muted', text: 'text-success', dot: 'bg-success' },
  connected:    { bg: 'bg-success-muted', text: 'text-success', dot: 'bg-success' },
  delivered:    { bg: 'bg-success-muted', text: 'text-success', dot: 'bg-success' },
  generated:    { bg: 'bg-accent-muted',    text: 'text-accent',    dot: 'bg-accent' },
  testing:      { bg: 'bg-warning-muted',   text: 'text-warning',   dot: 'bg-warning' },
  pending:      { bg: 'bg-warning-muted',   text: 'text-warning',   dot: 'bg-warning' },
  draft:        { bg: 'bg-subtle',   text: 'text-text-secondary',    dot: 'bg-text-muted' },
  inactive:     { bg: 'bg-subtle',   text: 'text-text-secondary',    dot: 'bg-text-muted' },
  archived:     { bg: 'bg-subtle',   text: 'text-text-secondary',    dot: 'bg-text-muted' },
  disconnected: { bg: 'bg-danger-muted',     text: 'text-danger',     dot: 'bg-danger' },
  failed:       { bg: 'bg-danger-muted',     text: 'text-danger',     dot: 'bg-danger' },
};

export default function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium capitalize',
        config.bg, config.text
      )}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', config.dot)} />
      {status}
    </span>
  );
}
