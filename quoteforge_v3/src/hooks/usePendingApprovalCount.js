import { useEffect, useState } from 'react';
import api from '@/services/api';

const POLL_INTERVAL_MS = 30_000;

/**
 * Lightweight polling hook used by the sidebar badge and the Approvals page
 * header count. Returns the current pending_count and a manual refresh.
 */
export default function usePendingApprovalCount(enabled = true) {
  const [count, setCount] = useState(0);

  async function refresh() {
    if (!enabled) return;
    try {
      const res = await api.get('/approvals', { params: { status: 'pending', per_page: 1 } });
      setCount(res.data.pending_count ?? 0);
    } catch {
      // silent — nav should never error out
    }
  }

  useEffect(() => {
    if (!enabled) return undefined;
    refresh();
    const t = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  return { count, refresh };
}
