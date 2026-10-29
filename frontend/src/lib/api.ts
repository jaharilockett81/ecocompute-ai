// Thin client for the EcoCompute FastAPI backend.

const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const LS_BASE = "ecocompute.apiBase";
const LS_CODE = "ecocompute.accessCode";

function lsGet(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function lsSet(key: string, value: string | null) {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
}

export function apiBase(): string {
  return (lsGet(LS_BASE) || DEFAULT_BASE).replace(/\/+$/, "");
}
export function setApiBase(v: string | null) {
  lsSet(LS_BASE, v);
}
export function defaultApiBase() {
  return DEFAULT_BASE;
}
export function accessCode(): string | null {
  return lsGet(LS_CODE);
}
export function setAccessCode(v: string | null) {
  lsSet(LS_CODE, v);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function headers(json = false): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const code = accessCode();
  if (code) h["X-Access-Code"] = code;
  return h;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let msg = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    /* not json */
  }
  return new ApiError(res.status, msg);
}

export async function apiGet<T = any>(path: string): Promise<T> {
  const res = await fetch(apiBase() + path, { headers: headers(), cache: "no-store" });
  if (!res.ok) throw await errorFrom(res);
  return res.json();
}

export async function apiPost<T = any>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(apiBase() + path, {
    method: "POST",
    headers: headers(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await errorFrom(res);
  return res.json();
}

export type TraceEvent = {
  seq: number;
  ts: number;
  step: string;
  status: "info" | "running" | "done" | "failed" | string;
  title: string;
  detail?: string;
  data?: any;
};

/** POST a workload and stream trace events (SSE over fetch, since EventSource can't POST). */
export function streamWorkload(body: unknown, onEvent: (e: TraceEvent) => void, signal?: AbortSignal): Promise<any> {
  return streamPost("/api/workloads/stream", body, onEvent, signal);
}

/** Run a Challenge scenario; events carry `lane` ("ecocompute" | "baseline"). */
export function streamChallenge(scenarioId: string, onEvent: (e: any) => void, signal?: AbortSignal): Promise<any> {
  return streamPost(`/api/challenge/${encodeURIComponent(scenarioId)}/stream`, undefined, onEvent, signal);
}

async function streamPost(path: string, body: unknown, onEvent: (e: any) => void, signal?: AbortSignal): Promise<any> {
  const res = await fetch(apiBase() + path, {
    method: "POST",
    headers: headers(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await errorFrom(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let kind = "message";
      const dataLines: string[] = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) kind = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) continue;
      const payload = JSON.parse(dataLines.join("\n"));
      if (kind === "event") onEvent(payload);
      else if (kind === "done") return payload;
      else if (kind === "error") throw new ApiError(500, payload.detail || "workload failed");
    }
  }
  throw new ApiError(500, "stream ended without a result");
}
