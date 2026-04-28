/**
 * API Client Configuration
 * Educational Note: We create an axios instance with base configuration
 * to avoid repeating the base URL and headers in every request.
 * This is the single source of truth for API communication.
 */

import axios, { AxiosError } from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import {
  getAccessToken,
  getRefreshToken,
  getAssetToken,
  getSelectedWorkspaceId,
  setSession,
  clearSession,
} from '../auth/session';
import { createLogger } from '@/lib/logger';
import { parseAuthSessionResponse, parseErrorEnvelope } from './contracts';

const log = createLogger('api-client');

// Base host URL (without /api/v1 path) - used for file URLs, static assets.
// When VITE_API_HOST is set to "" (Docker via nginx proxy), same-origin requests
// are used. When unset (local dev), falls back to localhost:5001.
const envHost = import.meta.env.VITE_API_HOST;
export const API_HOST = envHost !== undefined ? envHost : 'http://localhost:5001';

// Full API URL (with /api/v1 path) - used for API requests
const envApiUrl = import.meta.env.VITE_API_URL;
const API_BASE_URL = envApiUrl !== undefined ? envApiUrl : `${API_HOST}/api/v1`;

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const attachAuthHeader = (config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  const workspaceId = getSelectedWorkspaceId();
  if (workspaceId) {
    config.headers = config.headers || {};
    config.headers['X-NoobBook-Workspace-Id'] = workspaceId;
  }
  return config;
};

// Attach auth header to all requests
api.interceptors.request.use(
  (config) => {
    return attachAuthHeader(config);
  },
  (error) => {
    log.error({ err: error }, 'request interceptor error');
    return Promise.reject(error);
  }
);

// Ensure global axios requests (non-api instance) include auth header too
axios.interceptors.request.use(attachAuthHeader);

// ---------- Auto-refresh on 401 ----------
// Educational Note: When the JWT expires (default ~1 hour), API calls return 401.
// Instead of forcing re-login, we intercept the 401, use the stored refresh_token
// to get a new token pair, then transparently retry the original request.
// A shared `refreshPromise` ensures concurrent 401s trigger only one refresh call;
// all queued requests wait on the same promise.

let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    const parsed = parseAuthSessionResponse(data);
    if (parsed.session?.access_token) {
      setSession(parsed.session.access_token, parsed.session.refresh_token, parsed.asset_token);
      return true;
    }
  } catch (err) {
    log.error({ err }, 'token refresh failed');
  }

  clearSession();
  return false;
}

function isAuthRoute(url: string | URL): boolean {
  return String(url).includes('/auth/');
}

function withAuthHeader(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  const workspaceId = getSelectedWorkspaceId();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  } else {
    headers.delete('Authorization');
  }
  if (workspaceId) {
    headers.set('X-NoobBook-Workspace-Id', workspaceId);
  } else {
    headers.delete('X-NoobBook-Workspace-Id');
  }
  return { ...init, headers };
}

export async function readApiErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('Content-Type') || '';
  if (contentType.includes('application/json')) {
    try {
      return parseErrorEnvelope(await response.clone().json()).error;
    } catch {
      // Fall through to text below.
    }
  }
  return response.text();
}

export async function fetchWithAuthRefresh(url: string | URL, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, withAuthHeader(init));
  if (response.status !== 401 || isAuthRoute(url)) {
    return response;
  }

  if (!refreshPromise) {
    refreshPromise = tryRefreshToken().finally(() => { refreshPromise = null; });
  }

  const refreshed = await refreshPromise;
  if (!refreshed) {
    return response;
  }

  return fetch(url, withAuthHeader(init));
}

// Shared 401 error handler used by both the `api` instance and global `axios` interceptors.
// Educational Note: axios.create() instances have separate interceptor chains, so registering
// on both the `api` instance AND the global `axios` default won't double-fire for `api` requests.
// The shared `refreshPromise` correctly deduplicates concurrent refresh attempts across both.
async function handle401Error(error: AxiosError, retryWith: typeof api | typeof axios): Promise<unknown> {
  const status = error.response?.status;
  const originalRequest = error.config as InternalAxiosRequestConfig & { _retried?: boolean };

  // Skip refresh for auth routes (avoid infinite loop) and already-retried requests
  const isAuthRoute = originalRequest?.url?.includes('/auth/');
  if (status === 401 && originalRequest && !originalRequest._retried && !isAuthRoute) {
    // Deduplicate concurrent refresh attempts
    if (!refreshPromise) {
      refreshPromise = tryRefreshToken().finally(() => { refreshPromise = null; });
    }

    const refreshed = await refreshPromise;
    if (refreshed) {
      originalRequest._retried = true;
      // Update the header with the fresh token and retry
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${getAccessToken()}`;
      return retryWith(originalRequest);
    }
  }

  log.error({ status, data: error.response?.data }, 'API response error');
  return Promise.reject(error);
}

// Response interceptor: auto-refresh expired tokens, log other errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => handle401Error(error, api)
);

// Also cover the 22+ files that use the global `axios` instance directly
// (studio APIs, chats, sources, settings, etc.)
axios.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => handle401Error(error, axios)
);

/**
 * Build an asset-scoped URL for browser elements that can't send Authorization headers.
 *
 * Educational Note: Elements like <img>, <video>, <audio>, and <iframe> make their own
 * HTTP requests without axios interceptors. We append a short-lived asset token
 * so the backend auth middleware can validate the asset route without exposing
 * the primary Supabase JWT in a browser-visible URL.
 *
 * @param url - Absolute URL or path starting with /api/. If it's a full URL (starts with http),
 *              the token is appended directly. If it's a path, API_HOST is prepended first.
 */
export function getAuthUrl(url: string): string {
  const token = getAssetToken();
  const fullUrl = url.startsWith('http') ? url : `${API_HOST}${url}`;
  if (!token) return fullUrl;
  const separator = fullUrl.includes('?') ? '&' : '?';
  return `${fullUrl}${separator}asset_token=${encodeURIComponent(token)}`;
}

export { API_BASE_URL };
