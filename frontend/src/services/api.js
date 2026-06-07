/**
 * Skywalker API service – all calls to the FastAPI backend.
 * Trägt beide WLAN-IPs in .env ein – App erkennt automatisch welche erreichbar ist.
 */
const CANDIDATE_URLS = [
  process.env.EXPO_PUBLIC_API_URL,
  process.env.EXPO_PUBLIC_API_URL_2,
  "http://localhost:8000",
].filter(Boolean);

let _resolvedBase = null;

async function getBaseUrl() {
  if (_resolvedBase) return _resolvedBase;
  const primary = process.env.EXPO_PUBLIC_API_URL;
  // In Production (HTTPS) direkt verbinden – kein Auto-Detect nötig
  if (primary?.startsWith("https://")) {
    _resolvedBase = primary;
    return primary;
  }
  // Im lokalen Netz: automatisch erreichbare URL finden
  for (const url of CANDIDATE_URLS) {
    try {
      const res = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) { _resolvedBase = url; return url; }
    } catch (_) {}
  }
  _resolvedBase = CANDIDATE_URLS[0];
  return _resolvedBase;
}

export const BASE_URL = CANDIDATE_URLS[0]; // für Auth-Service Import

import { getToken, logout } from "./auth";

let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) { _onUnauthorized = fn; }

async function request(path, options = {}) {
  const base = await getBaseUrl();
  const url = `${base}${path}`;
  const token = await getToken();
  try {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...options,
    });
    if (res.status === 401) {
      await logout();
      if (_onUnauthorized) _onUnauthorized();
      throw new Error("Sitzung abgelaufen – bitte neu einloggen.");
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`API ${res.status}: ${err}`);
    }
    return res.json();
  } catch (e) {
    throw new Error(e.message.startsWith("API ") || e.message.startsWith("Sitzung") ? e.message : `Verbindungsfehler: ${e.message}`);
  }
}

export const api = {
  health: () => request("/api/health"),
  dashboard: () => request("/api/dashboard"),
  activities: (limit = 20) => request(`/api/activities?limit=${limit}`),
  sleep: (days = 90) => request(`/api/sleep?days=${days}`),
  steps: (days = 30) => request(`/api/steps?days=${days}`),
  trends: (days = 90) => request(`/api/trends?days=${days}`),

  checkinToday: () => request("/api/checkin/today"),
  saveCheckin: (data) =>
    request("/api/checkin", { method: "POST", body: JSON.stringify(data) }),
  getMatrix: () => request("/api/checkin/matrix"),
  saveMatrix: (data) =>
    request("/api/checkin/matrix", { method: "POST", body: JSON.stringify(data) }),

  deleteActivity: (date, name) =>
    request(`/api/activities?date=${encodeURIComponent(date)}&name=${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  askCoach: (message, tp_context = null) =>
    request("/api/coach", {
      method: "POST",
      body: JSON.stringify({ message, tp_context }),
    }),

  saveGoals: (ftp_target) =>
    request("/api/auth/goals", {
      method: "PATCH",
      body: JSON.stringify({ ftp_target }),
    }),

  saveProfile: (data) =>
    request("/api/auth/profile", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getProfile: () => request("/api/auth/me"),

  downloadWorkout: async (xml, format) => {
    const base = await getBaseUrl();
    const token = await getToken();
    const res = await fetch(`${base}/api/workout/download/${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ xml }),
    });
    if (!res.ok) throw new Error(`Download fehlgeschlagen: ${res.status}`);
    return res.text();
  },

  intervalsplan: () => request("/api/intervals/plan"),

  stravaAuthUrl: () => request("/api/strava/auth"),
  stravaSync: () => request("/api/strava/sync", { method: "POST" }),
  stravaDisconnect: () => request("/api/strava/disconnect", { method: "DELETE" }),
  stravaWebhookSetup: () => request("/api/strava/webhook/setup"),
};
