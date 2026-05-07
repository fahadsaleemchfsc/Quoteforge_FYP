import clsx from 'clsx';
import Mono from './Mono';

// Horizontal KPI pill. Label · value · optional delta arrow.
// Used in the dashboard compressed KPI strip.
export default function StatRow({ label, value, delta, deltaDirection }) {
  const dirColor = deltaDirection === 'up'
    ? 'text-success'
    : deltaDirection === 'down'
    ? 'text-danger'
    : 'text-text-secondary';
  return (
    <div className="inline-flex items-baseline gap-2">
      <span className="text-[11px] text-text-muted font-medium uppercase tracking-wider">
        {label}
      </span>
      <Mono className="text-[13px] text-text-primary font-semibold">{value}</Mono>
      {delta && (
        <Mono className={clsx('text-[11px]', dirColor)}>
          {delta}
        </Mono>
      )}
    </div>
  );
}
