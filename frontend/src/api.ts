/**
 * Typed API client for the Document Intake Assistant backend.
 * All requests go to http://localhost:8000
 */

const BASE = "http://localhost:8000";

export interface Executor {
  name: string | null;
  relationship: string | null;
}

export interface SpecificGift {
  recipient: string;
  description: string;
}

export interface PersonalWishesState {
  full_name: string | null;
  home_address: string | null;
  covers_worldwide_assets: boolean | null;
  has_children: boolean | null;
  children_names: string[];
  executor: Executor | null;
  specific_gifts: SpecificGift[] | null;
  additional_wishes: string | null;
}

export interface ChatResponse {
  reply: string;
  state: PersonalWishesState;
  document: string;
  missing_fields: string[];
}

export interface StateResponse {
  state: PersonalWishesState;
  missing_fields: string[];
  document: string;
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  chat: (message: string): Promise<ChatResponse> =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  getState: (): Promise<StateResponse> =>
    request<StateResponse>("/api/state"),

  manualEdit: (field: string, value: unknown): Promise<StateResponse> =>
    request<StateResponse>("/api/state/manual-edit", {
      method: "POST",
      body: JSON.stringify({ field, value }),
    }),

  reset: (): Promise<ChatResponse> =>
    request<ChatResponse>("/api/reset", { method: "POST" }),
};
