/**
 * Central API configuration. All backend calls must go through this module —
 * never hard-code URLs inside components.
 */
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
