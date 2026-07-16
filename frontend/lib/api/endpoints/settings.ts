import { request } from "../client";
import type { AppSettings } from "../types";

export const settings = {
  get: () => request<AppSettings>("/settings/"),
  update: (data: Partial<AppSettings>) =>
    request<AppSettings>("/settings/", { method: "PUT", body: JSON.stringify(data) }),
  backup: () =>
    request<{ ok: boolean; path?: string; filename: string; message: string }>("/settings/backup", {
      method: "POST",
    }),
  resetAll: () =>
    request<{ ok: boolean; message: string }>("/settings/reset-all", { method: "POST" }),
  testAi: () =>
    request<{ ok: boolean; message: string; sample?: string }>(
      "/settings/test-ai",
      {
        method: "POST",
      },
      180000
    ),
  aiUsage: () =>
    request<{
      week_total_calls: number;
      week_estimated_cost_usd: number;
      by_client: {
        client_id: number | null;
        client_name: string;
        calls: number;
        input_tokens: number;
        output_tokens: number;
        estimated_cost_usd: number;
      }[];
      recent: {
        id: number;
        client_id: number | null;
        provider: string;
        model: string;
        purpose: string;
        input_tokens: number;
        output_tokens: number;
        estimated_cost_usd: number;
        created_at: string | null;
      }[];
    }>("/settings/ai-usage"),
};

export const onboarding = {
  status: () =>
    request<{
      cloudflare_connected: boolean;
      google_connected: boolean;
      fully_connected: boolean;
      hubspot_connected: boolean;
      onboarding_complete: boolean;
      client_count: number;
    }>("/onboarding/status", undefined, 5000),
  connectCloudflare: (apiToken: string) =>
    request<{
      success: boolean;
      account_name: string;
      clients_created: number;
      datasources_created: number;
      zone_count: number;
      errors: string[];
    }>("/onboarding/cloudflare/connect", {
      method: "POST",
      body: JSON.stringify({ api_token: apiToken }),
    }),
  complete: () => request<{ ok: boolean }>("/onboarding/complete", { method: "POST" }),
  reset: () => request<{ ok: boolean }>("/onboarding/reset", { method: "POST" }),
};

export const cloudflare = {
  status: () =>
    request<{
      configured: boolean;
      connected: boolean;
      email: string;
      account_name: string;
      zone_count: number;
      client_count: number;
    }>("/auth/cloudflare/status", undefined, 5000),
  start: () => request<{ auth_url: string }>("/auth/cloudflare/start", undefined, 5000),
  resync: () =>
    request<{
      ok: boolean;
      account_name: string;
      clients_created: number;
      zone_count: number;
    }>("/auth/cloudflare/resync", { method: "POST" }),
};

export const google = {
  status: () =>
    request<{
      configured: boolean;
      connected: boolean;
      email: string;
      gsc_linked: number;
      ga4_linked: number;
    }>("/auth/google/status", undefined, 5000),
  start: () => request<{ auth_url: string }>("/auth/google/start", undefined, 5000),
  resync: () =>
    request<{
      ok: boolean;
      gsc_linked: number;
      ga4_linked: number;
    }>("/auth/google/resync", { method: "POST" }),
};

export const auth = {
  status: () =>
    request<{
      fully_connected: boolean;
      cloudflare: {
        configured: boolean;
        connected: boolean;
        email: string;
        account_name: string;
      };
      google: {
        configured: boolean;
        connected: boolean;
        email: string;
      };
    }>("/auth/status", undefined, 5000),
  signOut: () => request<{ ok: boolean }>("/auth/signout", { method: "POST" }),
};
