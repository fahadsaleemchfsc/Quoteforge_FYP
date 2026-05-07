import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export default function MetricCard({ metric, index = 0 }) {
  const Icon = metric.icon;

  return (
    <div
      className="card card-hover p-6 relative overflow-hidden animate-slide-up"
      style={{ animationDelay: `${index * 0.1}s` }}
    >
      {/* Background accent circle */}
      <div
        className="absolute -top-5 -right-5 w-20 h-20 rounded-full opacity-10"
        style={{ background: metric.color }}
      />

      {/* Header: icon + change */}
      <div className="flex justify-between items-start mb-4">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center"
          style={{ background: metric.color + '18' }}
        >
          <Icon size={22} color={metric.color} />
        </div>
        <span
          className={`inline-flex items-center gap-1 text-sm font-medium ${
            metric.up ? 'text-emerald-600' : 'text-red-600'
          }`}
        >
          {metric.up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
          {metric.change}
        </span>
      </div>

      {/* Value */}
      <div className="text-3xl font-bold text-gray-900 tracking-tight mb-1">
        {metric.value}
      </div>
      <div className="text-sm text-gray-500 font-medium">{metric.label}</div>
    </div>
  );
}
