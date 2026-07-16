export type Client = {
  id: number;
  name: string;
  industry: string;
  brand_color: string;
  profile_json?: string;
  owner?: string;
  priority?: number;
  archived?: boolean;
  site_relaunched_at?: string | null;
  created_at: string;
};

export type ClientProfile = {
  goals?: string;
  brand_voice?: string;
  do_not_touch?: string;
  competitors?: string;
  target_audience?: string;
  notes?: string;
  brand_terms?: string;
  primary_location?: string;
  service_areas?: string;
  exclude_areas?: string;
  success_contract?: {
    primary_metric?: string;
    secondary_metrics?: string[];
    target_delta_pct?: number;
    window_days?: number;
    notes?: string;
  };
};

export type TodayItem = {
  id: string;
  kind: string;
  priority: number;
  client_id: number;
  client_name: string;
  title: string;
  detail: string;
  cta: string;
  cta_tab: string;
  insight_id?: number;
  task_id?: number;
  effort?: string;
  assigned_to?: string;
  due_date?: string | null;
};

export type SuccessBoard = {
  ahead: number;
  on_track: number;
  behind: number;
  unset: number;
  no_data: number;
  overdue_execute: number;
  report_ready: number;
  client_count: number;
  shipped_7d?: number;
  ship_target_min?: number;
  ship_target_max?: number;
  clients_behind_pace?: number;
};

export type PortfolioBenchmark = {
  clients: PortfolioClient[];
  success_board: SuccessBoard;
};

export type PortfolioTopAction = {
  title: string;
  detail?: string;
  insight_id?: number | null;
  task_id?: number | null;
  cta_tab: string;
  effort?: string;
  playbook?: string;
};

export type PortfolioClient = {
  client_id: number;
  name: string;
  industry: string;
  brand_color: string;
  owner?: string;
  priority?: number;
  health_score: number;
  risk: "critical" | "stabilizing" | "watch" | "healthy" | "no_data";
  shipped_7d?: number;
  ship_cadence?: {
    fixes_done_7d: number;
    target_min: number;
    target_max: number;
    on_pace: boolean;
  };
  site_relaunched_at: string | null;
  days_since_relaunch: number | null;
  risk_reasons?: string[];
  slipping?: boolean;
  stale_days?: number | null;
  overdue_tasks?: number;
  risk_rank?: number;
  top_action?: PortfolioTopAction | null;
  pillars?: {
    search_visibility: number;
    conversion_performance: number;
    traffic_quality: number;
    efficiency: number;
    technical: number;
  };
  open_insights: number;
  open_insights_high: number;
  open_opportunities?: number;
  open_tasks: number;
  report_ready?: boolean;
  report_ready_count?: number;
  ai_value_score?: number | null;
  last_synced_at: string | null;
  success_contract?: {
    configured?: boolean;
    status?: string;
    contract?: {
      primary_metric?: string;
      target_delta_pct?: number;
      window_days?: number;
      label?: string;
    } | null;
    progress?: {
      label?: string;
      change_pct?: number | null;
      target_delta_pct?: number;
      current?: number;
    } | null;
  } | null;
  wow: {
    clicks: number | null;
    sessions: number | null;
    conversions: number | null;
    leads?: number | null;
    revenue?: number | null;
    ad_cost?: number | null;
  };
  metrics: {
    gsc_clicks: number;
    gsc_impressions: number;
    ga4_sessions: number;
    ga4_conversions: number;
    ctr: number;
    conversion_rate: number;
    month_clicks?: number;
    leads?: number;
    revenue?: number;
    ad_cost?: number;
  };
  rankings: Record<string, number>;
};

export type DataSource = {
  id: number;
  client_id: number;
  type: string;
  last_synced_at: string | null;
  status: string;
  last_error?: string | null;
  has_credentials?: boolean;
};

export type Metric = {
  id: number;
  client_id: number;
  source: string;
  date: string;
  metric_name: string;
  value: number;
  dimension_type: string | null;
  dimension_value: string | null;
};

export type Insight = {
  id: number;
  client_id: number;
  type: string;
  message: string;
  recommended_action: string | null;
  severity: string;
  kind?: "problem" | "opportunity" | string;
  priority_score?: number;
  created_at: string;
  resolved: boolean;
  target_query?: string | null;
  target_url?: string | null;
  evidence?: string | null;
  /** Sample-size evidence tier from the insight engine: high | medium | low | insufficient */
  confidence_tier?: "high" | "medium" | "low" | "insufficient" | string | null;
  sample_size?: number | null;
  algorithmic_caveat?: boolean | null;
};

export type Task = {
  id: number;
  client_id: number;
  insight_id: number | null;
  assigned_to: string;
  status: string;
  due_date: string | null;
  result_notes: string | null;
  /** win | loss | flat when measured; null = still needs Prove attention */
  impact_outcome?: string | null;
  brief_id?: number | null;
  lever_id?: number | null;
  playbook_pattern?: string | null;
  action_plan_id?: number | null;
  target_query?: string | null;
  target_url?: string | null;
  fingerprint?: string | null;
  created_at: string;
};

export type GrowthLever = {
  id: number;
  client_id: number;
  status: string;
  title: string;
  stage?: string | null;
  cause?: string | null;
  fix?: string | null;
  impact_score?: number | null;
  source_insight_ids?: number[];
  task_id?: number | null;
  brief_id?: number | null;
  impact_summary?: string | null;
  confidence_label?: string | null;
  include_in_report?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  resolved_at?: string | null;
};

export type WeeklySummary = {
  id: number;
  client_id: number;
  week_start: string;
  content: string;
  reviewed: boolean;
  created_at: string;
};

export type ContentBrief = {
  id: number;
  client_id: number;
  insight_id: number | null;
  keyword: string;
  title: string[];
  outline: unknown[];
  word_count: number | null;
  related_keywords: string[];
  status: string;
  created_at: string | null;
};

export type Opportunities = {
  client_id: number;
  days: number;
  period: { start: string; end: string };
  rising_queries: {
    query: string;
    impressions: number;
    prev_impressions: number;
    growth_pct: number;
    clicks: number;
    position: number;
    ctr: number;
  }[];
  ctr_underperformers: {
    page: string;
    impressions: number;
    clicks: number;
    ctr: number;
    expected_ctr: number;
    gap_pct: number;
    position: number;
  }[];
  landing_pages: {
    page: string;
    sessions: number;
    conversions: number;
    cvr: number;
    vs_avg: number;
  }[];
};

export type RankingRow = {
  query: string;
  position: number | null;
  prev_position: number | null;
  change: number | null;
  impressions: number;
  clicks: number;
  ctr: number;
  bucket: "top3" | "top10" | "page2" | "deeper" | "unknown";
  tracked: boolean;
  tracked_id: number | null;
  target_url: string | null;
  is_brand?: boolean;
};

export type RankingsReport = {
  client_id: number;
  days: number;
  brand_scope?: string;
  brand_terms?: string[];
  period: {
    start: string;
    end: string;
    prev_start: string;
    prev_end: string;
  };
  summary: {
    avg_position: number | null;
    queries_ranked: number;
    top10: number;
    striking_distance: number;
    improved: number;
    declined: number;
    tracked_count: number;
    buckets: {
      top3: number;
      top10: number;
      page2: number;
      deeper: number;
    };
  };
  rankings: RankingRow[];
  tracked: {
    id: number;
    keyword: string;
    target_url: string | null;
    notes: string | null;
    created_at: string | null;
  }[];
};

export type SuccessContractPayload = {
  client_id: number;
  configured: boolean;
  status: string;
  contract?: {
    primary_metric: string;
    secondary_metrics?: string[];
    target_delta_pct: number;
    window_days: number;
    notes?: string;
    label?: string;
  } | null;
  progress?: {
    primary_metric: string;
    label: string;
    current: number;
    compare_base: number;
    compare_mode: string;
    change_pct: number | null;
    target_delta_pct: number;
    progress_ratio: number | null;
    window_days: number;
    period_start: string;
    period_end: string;
  } | null;
  brand_split?: {
    days: number;
    brand_terms: string[];
    has_brand_terms: boolean;
    current: {
      brand_clicks: number;
      non_brand_clicks: number;
      brand_impressions: number;
      non_brand_impressions: number;
    };
    previous: {
      brand_clicks: number;
      non_brand_clicks: number;
      brand_impressions: number;
      non_brand_impressions: number;
    };
    change_pct: {
      brand_clicks: number | null;
      non_brand_clicks: number | null;
      brand_impressions: number | null;
      non_brand_impressions: number | null;
    };
  } | null;
};

export type KeywordHistory = {
  client_id: number;
  keyword: string;
  days: number;
  history: {
    date: string;
    position: number | null;
    impressions: number;
    clicks: number;
  }[];
};

export type FunnelReport = {
  client_id: number;
  period_start?: string;
  period_end?: string;
  totals: {
    impressions: number;
    clicks: number;
    sessions: number;
    conversions: number;
    paid_impressions?: number;
    paid_clicks?: number;
    leads?: number;
    closed_won?: number;
    revenue?: number;
    ad_cost?: number;
    [key: string]: number | undefined;
  };
  rates: {
    impression_to_click_pct: number;
    click_to_session_pct: number | null;
    session_to_conversion_pct: number;
    overall_conversion_pct?: number;
    conversion_to_lead_pct?: number | null;
    lead_to_closed_pct?: number | null;
    [key: string]: number | null | undefined;
  };
  stages: {
    stage: string;
    entered: number;
    exited: number;
    conversion_rate: number | null;
    dropoff: number | null;
    unreliable?: boolean;
    note?: string | null;
  }[];
  biggest_leak: { stage: string; dropoff: number } | null;
  leaks: {
    stage: string;
    leak_pct: number;
    lost_clicks?: number;
    lost_sessions?: number;
    lost_conversions?: number;
    lost_leads?: number;
    lost_revenue?: number;
    cause: string;
    fix: string;
  }[];
  growth_lever?: {
    stage?: string;
    title?: string;
    cause?: string;
    fix?: string;
    leak_pct?: number;
  } | null;
  has_paid?: boolean;
  has_crm?: boolean;
};

export type SuccessReport = {
  client: { id: number; name: string; industry: string; brand_color: string };
  agency?: ReportAgency;
  period: {
    days: number;
    start: string;
    end: string;
    mode?: string;
    year?: number;
    month?: number;
    month_name?: string;
  };
  /** diagnostic = detections/prescriptions only; success = work or proof present */
  report_kind?: "diagnostic" | "success";
  kpis: {
    key: string;
    label: string;
    source: string;
    current: number;
    previous: number;
    change_pct: number | null;
  }[];
  funnel?: FunnelReport;
  commercial_proof?: {
    story: string;
    clicks: number;
    sessions: number;
    conversions: number;
    leads: number;
    opportunities: number;
    closed_won: number;
    revenue: number;
    has_crm: boolean;
    has_paid: boolean;
    biggest_leak?: unknown;
    primary_contract?: string | null;
  };
  opportunities?: {
    rising_queries: { query: string; growth_pct: number; impressions?: number; clicks?: number }[];
    ctr_underperformers: { page: string; gap_pct: number; ctr?: number; impressions?: number }[];
    landing_pages: { page: string; cvr: number; sessions: number; conversions?: number }[];
  };
  campaigns?: {
    campaign: string;
    impressions: number;
    clicks: number;
    cost: number;
    conversions: number;
    conversion_value: number;
    ctr?: number;
    cpc?: number;
  }[];
  work: {
    insights_resolved: number;
    insights_open: number;
    tasks_completed: number;
    briefs_created?: number;
    completed_items?: { task_id: number; label: string }[];
  };
  impact_wins: {
    task_id: number;
    label: string;
    avg_primary_metric_change: number;
    proof_copy?: string;
  }[];
  next_actions: {
    title?: string;
    estimated_impact?: string;
    why_it_matters?: string;
    priority_score?: number;
  }[];
  narrative: string | null;
  glossary?: { term: string; definition: string }[];
  generated_at: string;
  from_cache?: boolean;
  monthly_report_id?: number;
  readiness?: ReportReadinessChecklist;
  stale?: boolean;
};

export type ReportLibraryItem = {
  id: number;
  year: number;
  month: number;
  month_name?: string;
  generated_at: string | null;
  narrative_ready?: boolean;
  stale?: boolean;
};

export type ReportReadinessChecklist = {
  data_synced: boolean;
  work_or_proof: boolean;
  has_saved_report: boolean;
  narrative_ready: boolean;
};

export type ReportLibrary = {
  client_id: number;
  client_name: string;
  status: "ready" | "draft" | "stale" | "unsaved" | string;
  has_saved: boolean;
  last_saved_at: string | null;
  data_freshness: string | null;
  proven_lever_count: number;
  tasks_completed: number;
  insights_open: number;
  checklist: ReportReadinessChecklist;
  reports: ReportLibraryItem[];
};

export type AppSettings = {
  ai_provider: string;
  ollama_base_url: string;
  ollama_model: string;
  ollama_fallback_model?: string;
  anthropic_configured: boolean;
  ai_ready: boolean;
  pagespeed_api_key: string;
  pagespeed_api_key_configured?: boolean;
  bing_api_key: string;
  bing_api_key_configured?: boolean;
  clarity_api_token: string;
  clarity_api_token_configured?: boolean;
  google_ads_developer_token?: string;
  google_ads_developer_token_configured?: boolean;
  assignee_presets?: string;
  /** Local workstation agent name — defaults My book / Work Board filters */
  my_agent_name?: string;
  impact_window_days?: number;
  /** White-label: agency name on report cover (empty → Kinexis) */
  agency_name?: string;
  /** White-label accent hex; empty → client brand → Studio Teal */
  agency_accent?: string;
  /** Logo URL or data URL for report cover */
  agency_logo_url?: string;
  /** Remote client portal — bind + share links */
  portal_enabled?: boolean;
  /** Public HTTPS base (Cloudflare Tunnel / ngrok), no trailing slash */
  public_base_url?: string;
  portal?: {
    portal_enabled: boolean;
    public_base_url: string;
    allow_remote: boolean;
    share_links_reachable: boolean;
    needs_restart: boolean;
    hint: string;
  };
  database_path?: string | null;
};

export type ReportAgency = {
  name: string;
  accent: string;
  logo_url: string;
  is_white_label: boolean;
};
