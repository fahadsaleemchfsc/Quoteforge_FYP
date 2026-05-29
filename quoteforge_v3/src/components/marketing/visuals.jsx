import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';

/**
 * Visual primitives for the marketing pages.
 * Pure CSS animation under the hood — see styles/marketing.css for
 * the .m-* class definitions.
 */

// ─── FloatingOrbs ────────────────────────────────────────────
// Drops 3-4 large blurred gradient blobs in a section. Position
// each absolutely via the `orbs` array (each entry → {x, y, size,
// color, delay}). Wrap inside a `relative overflow-hidden` parent.
const DEFAULT_ORBS = [
  { x: '-10%', y: '-20%', size: 520, color: 'radial-gradient(circle, #8B5CF6, transparent 70%)',  delay: '0s'  },
  { x: '60%',  y: '0%',   size: 420, color: 'radial-gradient(circle, #D946EF, transparent 70%)',  delay: '-6s' },
  { x: '20%',  y: '60%',  size: 380, color: 'radial-gradient(circle, #06B6D4, transparent 70%)',  delay: '-12s'},
];

export function FloatingOrbs({ orbs = DEFAULT_ORBS, className = '' }) {
  return (
    <div className={clsx('absolute inset-0 pointer-events-none overflow-hidden', className)} aria-hidden>
      {orbs.map((o, i) => (
        <span
          key={i}
          className="m-orb"
          style={{
            left: o.x,
            top: o.y,
            ['--m-orb-size']: typeof o.size === 'number' ? `${o.size}px` : o.size,
            background: o.color,
            animationDelay: o.delay || `${-i * 4}s`,
          }}
        />
      ))}
    </div>
  );
}

// ─── GlassCard ───────────────────────────────────────────────
// Frosted card. `tone="dark"` flips to glass-on-dark-bg.
export function GlassCard({ tone = 'light', className = '', children, ...rest }) {
  return (
    <div
      className={clsx(
        'rounded-2xl',
        tone === 'dark' ? 'm-glass-dark' : 'm-glass',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

// ─── TiltCard ────────────────────────────────────────────────
// Children get a CSS-only 3D tilt (perspective from .m-stage on
// the parent). Hover settles toward flat for a tactile feel.
export function TiltCard({ className = '', children, ...rest }) {
  return (
    <div className={clsx('m-tilt', className)} {...rest}>
      {children}
    </div>
  );
}

// ─── Reveal ──────────────────────────────────────────────────
// Wraps children in a fade+rise-on-enter container. Triggers via
// IntersectionObserver on first viewport intersection. Honor
// prefers-reduced-motion via CSS in marketing.css.
export function Reveal({ as: Tag = 'div', delay = 0, className = '', children, ...rest }) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setShown(true);
            obs.disconnect();
            break;
          }
        }
      },
      { rootMargin: '0px 0px -10% 0px', threshold: 0.05 },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={clsx('m-reveal', shown && 'm-reveal--show', className)}
      style={{ ['--m-reveal-delay']: `${delay}ms` }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

// ─── AnimatedCounter ─────────────────────────────────────────
// Counts from 0 → target on first view. Useful for stat callouts.
export function AnimatedCounter({ to, prefix = '', suffix = '', duration = 1400, className = '' }) {
  const ref = useRef(null);
  const [val, setVal] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setVal(to);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const start = performance.now();
            const tick = (now) => {
              const t = Math.min(1, (now - start) / duration);
              // ease-out-cubic
              const eased = 1 - Math.pow(1 - t, 3);
              setVal(Math.round(to * eased));
              if (t < 1) requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
            obs.disconnect();
            break;
          }
        }
      },
      { threshold: 0.4 },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [to, duration]);

  return (
    <span ref={ref} className={className}>
      {prefix}{val.toLocaleString('en-US')}{suffix}
    </span>
  );
}
