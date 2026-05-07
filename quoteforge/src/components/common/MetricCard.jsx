import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export default function MetricCard({ label, value, change, up, icon: Icon, color }) {
  return (
    <div className="card card-hover relative overflow-hidden group">
      {/* Background accent circle */}
      <div
        className="absolute -top-5 -right-5 w-20 h-20 rounded-full opacity-10"
        style={{ background: color }}
      />

      <div className="flex justify-between items-start mb-4">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center"
          style={{ background: `${color}15` }}
        >
          <Icon size={22} color={color} />
        </div>
        <span
          className={`inline-flex items-center gap-1 text-sm font-medium ${
            up ? 'text-emerald-600' : 'text-red-600'
          }`}
        >
          {up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
          {change}
        </span>
      </div>

      <div className="text-3xl font-bold text-gray-900 tracking-tight mb-1">{value}</div>
      <div className="text-sm text-gray-500 font-medium">{label}</div>
    </div>
  );
}
