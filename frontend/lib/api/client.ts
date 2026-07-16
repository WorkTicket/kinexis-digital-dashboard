export const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_BASE ||
      (window.location.protocol === "http:" &&
      (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost")
        ? `http://127.0.0.1:${window.kinexis?.backendPort || 8000}`
        : "")
    : "http://127.0.0.1:8000";

export async function getApiHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  let token = "";
  if (typeof window !== "undefined" && window.kinexis?.getApiToken) {
    try {
      token = (await window.kinexis.getApiToken()) || "";
    } catch {
      console.warn("Failed to retrieve API token from desktop bridge");
      token = "";
    }
  }
  if (!token && typeof process !== "undefined" && typeof process.env !== "undefined") {
    token = process.env.NEXT_PUBLIC_KINEXIS_API_TOKEN || "";
  }
  if (token) {
    headers["X-Kinexis-Token"] = token;
  }
  return headers;
}

export async function request<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = 30000
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const external = options?.signal;
  const onExternalAbort = () => controller.abort();
  if (external) {
    if (external.aborted) {
      clearTimeout(timeout);
      throw new DOMException("Aborted", "AbortError");
    }
    external.addEventListener("abort", onExternalAbort);
  }
  try {
    const { signal: _ignored, headers: optHeaders, ...rest } = options || {};
    const baseHeaders = await getApiHeaders();
    const res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: { ...baseHeaders, ...(optHeaders || {}) },
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`${res.status}: ${err}`);
    }
    if (res.status === 204) {
      return undefined as unknown as T;
    }
    const text = await res.text();
    if (!text) {
      return undefined as unknown as T;
    }
    return JSON.parse(text);
  } finally {
    clearTimeout(timeout);
    external?.removeEventListener("abort", onExternalAbort);
  }
}
