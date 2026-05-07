import { useState, useEffect, useCallback } from 'react';

/**
 * Generic async data-fetching hook.
 * Handles loading / error / data states.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useAsync(() => templateService.getAll());
 */
export function useAsync(asyncFn, immediate = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);

  const execute = useCallback(async (...args) => {
    try {
      setLoading(true);
      setError(null);
      const response = await asyncFn(...args);
      setData(response?.data ?? response);
      return response;
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [asyncFn]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, []);

  return { data, loading, error, refetch: execute };
}

/**
 * Debounce hook for search inputs.
 */
export function useDebounce(value, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Toggle hook for modals / sidebars / etc.
 */
export function useToggle(initial = false) {
  const [state, setState] = useState(initial);
  const toggle = useCallback(() => setState((s) => !s), []);
  const setTrue = useCallback(() => setState(true), []);
  const setFalse = useCallback(() => setState(false), []);
  return { state, toggle, setTrue, setFalse };
}
