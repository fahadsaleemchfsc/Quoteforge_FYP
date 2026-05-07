import clsx from 'clsx';

// Inline monospace wrapper with tabular numerics. Used for SKUs, IDs,
// timestamps, currency, anything with a column-alignment requirement.
export default function Mono({ className = '', children }) {
  return (
    <span className={clsx('font-mono', className)} style={{ fontFeatureSettings: '"tnum"' }}>
      {children}
    </span>
  );
}
