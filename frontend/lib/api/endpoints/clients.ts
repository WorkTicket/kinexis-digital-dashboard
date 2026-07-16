import { request } from "../client";
import type { Client, DataSource } from "../types";

export const clients = {
  list: (includeArchived = false) =>
    request<Client[]>(`/clients/${includeArchived ? "?include_archived=true" : ""}`),
  get: (id: number) => request<Client>(`/clients/${id}`),
  create: (data: Partial<Client>) =>
    request<Client>("/clients/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Client>) =>
    request<Client>(`/clients/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  archive: (id: number) => request<{ ok: boolean }>(`/clients/${id}/archive`, { method: "POST" }),
  unarchive: (id: number) =>
    request<{ ok: boolean }>(`/clients/${id}/unarchive`, { method: "POST" }),
  delete: (id: number) => request<{ ok: boolean }>(`/clients/${id}`, { method: "DELETE" }),
  datasources: {
    list: (clientId: number) => request<DataSource[]>(`/clients/${clientId}/datasources`),
    create: (clientId: number, data: { type: string; credentials?: Record<string, unknown> }) =>
      request<DataSource>(`/clients/${clientId}/datasources`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    delete: (clientId: number, dsId: number) =>
      request<{ ok: boolean }>(`/clients/${clientId}/datasources/${dsId}`, { method: "DELETE" }),
    update: (
      clientId: number,
      dsId: number,
      data: { credentials?: Record<string, unknown>; status?: string }
    ) =>
      request<DataSource>(`/clients/${clientId}/datasources/${dsId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
  },
};
