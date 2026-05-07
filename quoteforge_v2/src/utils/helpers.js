/**
 * Format a number as currency.
 * formatCurrency(45000) → "$45,000.00"
 */
export function formatCurrency(value, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(value);
}

/**
 * Format a number with commas.
 * formatNumber(12500) → "12,500"
 */
export function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(value);
}

/**
 * Relative time string.
 * timeAgo(date) → "2 minutes ago"
 */
export function timeAgo(date) {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  const intervals = [
    { label: 'year', seconds: 31536000 },
    { label: 'month', seconds: 2592000 },
    { label: 'week', seconds: 604800 },
    { label: 'day', seconds: 86400 },
    { label: 'hour', seconds: 3600 },
    { label: 'minute', seconds: 60 },
  ];

  for (const interval of intervals) {
    const count = Math.floor(seconds / interval.seconds);
    if (count >= 1) {
      return `${count} ${interval.label}${count > 1 ? 's' : ''} ago`;
    }
  }
  return 'just now';
}

/**
 * Truncate a string to a max length.
 */
export function truncate(str, maxLength = 50) {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + '…';
}

/**
 * Generate initials from a full name.
 * getInitials("Sarah Johnson") → "SJ"
 */
export function getInitials(name) {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase();
}

/**
 * Clamp a number between min and max.
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/**
 * Download a blob as a file.
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
