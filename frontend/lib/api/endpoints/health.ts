import { request } from "../client";

export const health = {
  check: () => request<{ db: string; status: string }>("/health"),
  forClient: (clientId: number) =>
    request<{
      client_id: number;
      name: string;
      health_score: number | null;
      risk: string;
      risk_reasons: string[];
      top_action?: {
        title: string;
        detail?: string;
        insight_id?: number | null;
        task_id?: number | null;
        cta_tab?: string;
        effort?: string;
        playbook?: string;
      } | null;
      pillars?: {
        search_visibility: number;
        conversion_performance: number;
        traffic_quality: number;
        efficiency: number;
        technical: number;
      } | null;
    }>(`/actions/health/${clientId}`),
};
