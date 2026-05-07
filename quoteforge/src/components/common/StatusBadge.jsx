import { STATUS_CONFIG } from '@utils/constants';
import { cn } from '@utils/helpers';

export default function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;

  return (
    <span className={cn('badge', config.bg, config.text)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', config.dot)} />
      {status}
    </span>
  );
}
