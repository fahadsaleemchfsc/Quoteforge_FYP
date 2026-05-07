import { clsx } from 'clsx';

/**
 * Merge class names conditionally (wrapper around clsx)
 */
export function cn(...inputs) {
  return clsx(inputs);
}

/**
 * Format number with commas: 1247 → "1,247"
 */
export function formatNumber(num) {
  if (num == null) return '—';
  return num.toLocaleString('en-US');
}

/**
 * Format currency: 45000 → "$45,000"
 */
export function formatCurrency(amount, currency = 'USD') {
  if (amount == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Truncate text with ellipsis
 */
export function truncate(str, maxLength = 50) {
  if (!str) return '';
  return str.length > maxLength ? str.slice(0, maxLength) + '…' : str;
}

/**
 * Generate initials from a full name: "Sarah Johnson" → "SJ"
 */
export function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Generate a deterministic HSL color from a string (for avatars)
 */
export function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return {
    bg: `hsl(${hue}, 60%, 92%)`,
    text: `hsl(${hue}, 60%, 40%)`,
  };
}

/**
 * Delay utility for async operations
 */
export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Capitalize first letter
 */
export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}
