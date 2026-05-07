import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export default function MetricCard({ metric, index = 0 }) {
  const Icon = metric.icon;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div
          className="w-8 h-8 rounded flex items-center justify-center"
          style={{ background: metric.color + '14' }}
        >
          <Icon size={16} color={metric.color} strokeWidth={2} />
        </div>
        <span
          className={`inline-flex items-center gap-0.5 text-xs font-medium ${
            metric.up ? 'text-success' : 'text-danger'
          }`}
        >
          {metric.up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
          {metric.change}
        </span>
      </div>

      <div className="text-2xl font-semibold text-text-primary tracking-tight">
        {metric.value}
      </div>
      <div className="text-xs text-text-secondary mt-0.5">{metric.label}</div>
    </div>
  );
}
