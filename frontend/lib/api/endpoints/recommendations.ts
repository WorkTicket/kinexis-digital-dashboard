import { request } from "../client";

export type Recommendation = {
  id: number;
  client_id: number;
  insight_id?: number | null;
  task_id?: number | null;
  status: string;
  fix_type?: string | null;
  title: string;
  expected_lift_pct?: number | null;
  expected_metric?: string | null;
  actual_lift_pct?: number | null;
  outcome?: string | null;
  notes?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  verified_at?: string | null;
};

export type RecommendationEffectiveness = {
  fix_type: string;
  wins: number;
  losses: number;
  flat: number;
  total: number;
  win_rate: number | null;
  median_lift_pct: number | null;
  measured: boolean;
};

export const recommendations = {
  list: (opts?: { client_id?: number; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.client_id != null) params.set("client_id", String(opts.client_id));
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return request<Recommendation[]>(q ? `/recommendations/?${q}` : "/recommendations/");
  },
  effectiveness: () =>
    request<{ fixes: RecommendationEffectiveness[] }>("/recommendations/effectiveness"),
  propose: (insightId: number) =>
    request<Recommendation>("/recommendations/propose", {
      method: "POST",
      body: JSON.stringify({ insight_id: insightId }),
    }),
  fromTask: (taskId: number) =>
    request<Recommendation>(`/recommendations/from-task/${taskId}`, { method: "POST" }),
};
