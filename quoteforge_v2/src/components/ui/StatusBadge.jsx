import clsx from 'clsx';

const STATUS_CONFIG = {
  active:       { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  connected:    { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  delivered:    { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  generated:    { bg: 'bg-blue-100',  text: 'text-blue-800',  dot: 'bg-blue-500' },
  testing:      { bg: 'bg-amber-100', text: 'text-amber-800', dot: 'bg-amber-500' },
  pending:      { bg: 'bg-amber-100', text: 'text-amber-800', dot: 'bg-amber-500' },
  draft:        { bg: 'bg-gray-100',  text: 'text-gray-600',  dot: 'bg-gray-400' },
  inactive:     { bg: 'bg-gray-100',  text: 'text-gray-600',  dot: 'bg-gray-400' },
  archived:     { bg: 'bg-gray-100',  text: 'text-gray-600',  dot: 'bg-gray-400' },
  disconnected: { bg: 'bg-red-100',   text: 'text-red-800',   dot: 'bg-red-500' },
  failed:       { bg: 'bg-red-100',   text: 'text-red-800',   dot: 'bg-red-500' },
};

export default function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium capitalize',
        config.bg,
        config.text
      )}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', config.dot)} />
      {status}
    </span>
  );
}
