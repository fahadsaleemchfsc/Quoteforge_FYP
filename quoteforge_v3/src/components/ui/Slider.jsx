import clsx from 'clsx';
import Mono from './Mono';

// Custom-styled range slider. 4px thin track, 16px thumb, accent fill.
// Native <input type="range"> under the hood — keyboard + screen reader
// support stays; we just restyle via CSS.
export default function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 100,
  step = 0.5,
  format = (v) => `${v}`,
  className = '',
}) {
  const pct = max === min ? 0 : ((value - min) / (max - min)) * 100;

  return (
    <div className={clsx('w-full', className)}>
      {label && (
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider">
            {label}
          </span>
          <Mono className="text-[13px] text-text-primary font-medium">{format(value)}</Mono>
        </div>
      )}
      <div className="relative">
        <div
          aria-hidden
          className="absolute top-1/2 left-0 right-0 h-[4px] -translate-y-1/2 rounded-sm pointer-events-none"
          style={{
            background: `linear-gradient(to right, var(--accent) 0%, var(--accent) ${pct}%, var(--bg-muted) ${pct}%, var(--bg-muted) 100%)`,
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="qf-slider"
        />
      </div>
    </div>
  );
}

// Slider-specific CSS injected once globally.
if (typeof document !== 'undefined' && !document.getElementById('qf-slider-css')) {
  const style = document.createElement('style');
  style.id = 'qf-slider-css';
  style.textContent = `
    .qf-slider {
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      height: 16px;
      background: transparent;
      cursor: pointer;
      display: block;
    }
    .qf-slider:focus { outline: none; }
    .qf-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--bg-surface);
      border: 2px solid var(--accent);
      cursor: grab;
      transition: border-color 120ms ease, transform 120ms ease, box-shadow 120ms ease;
      box-shadow: 0 0 0 0 var(--accent-muted);
    }
    .qf-slider:focus::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--accent-muted); }
    .qf-slider::-webkit-slider-thumb:hover { transform: scale(1.1); }
    .qf-slider:active::-webkit-slider-thumb { cursor: grabbing; }
    .qf-slider::-moz-range-thumb {
      width: 16px; height: 16px; border-radius: 50%;
      background: var(--bg-surface); border: 2px solid var(--accent);
      cursor: grab;
    }
    .qf-slider::-moz-range-track { background: transparent; }
  `;
  document.head.appendChild(style);
}
