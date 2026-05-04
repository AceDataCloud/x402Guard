/**
 * Single Axios client for the FastAPI backend. Handles:
 *  - Bearer token attachment from the auth store
 *  - JSON content-type defaults
 *  - 401 → clear session + redirect to home
 *
 * In dev, Vite proxies /api/* and /mcp/* to the FastAPI dev server so
 * we ship a relative baseURL and never hardcode origins outside of
 * `import.meta.env.VITE_API_BASE_URL` (production override).
 */
import axios, { AxiosError } from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "";

export const apiClient = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

let _sessionToken: string | null = null;

export function setSessionToken(token: string | null): void {
  _sessionToken = token;
  if (token) {
    localStorage.setItem("x402guard.session", token);
  } else {
    localStorage.removeItem("x402guard.session");
  }
}

export function getSessionToken(): string | null {
  if (_sessionToken) return _sessionToken;
  _sessionToken = localStorage.getItem("x402guard.session");
  return _sessionToken;
}

apiClient.interceptors.request.use((config) => {
  const t = getSessionToken();
  if (t) {
    config.headers.set("Authorization", `Bearer ${t}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      setSessionToken(null);
    }
    return Promise.reject(err);
  }
);
