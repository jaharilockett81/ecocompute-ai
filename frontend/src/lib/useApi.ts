"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "./api";

/** GET a backend path; optionally re-poll every `intervalMs` while `poll` is true. */
export function useApi<T = any>(path: string | null, opts: { intervalMs?: number; poll?: boolean } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const pathRef = useRef(path);
  pathRef.current = path;

  const reload = useCallback(async () => {
    const p = pathRef.current;
    if (!p) return;
    try {
      const d = await apiGet<T>(p);
      if (pathRef.current === p) {
        setData(d);
        setError(null);
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(!!path);
    reload();
  }, [path, reload]);

  useEffect(() => {
    if (!opts.poll || !opts.intervalMs || !path) return;
    const t = setInterval(reload, opts.intervalMs);
    return () => clearInterval(t);
  }, [opts.poll, opts.intervalMs, path, reload]);

  return { data, error, loading, reload };
}
