"use client";

import { useState } from "react";
import { Plus, Trash2, Database } from "lucide-react";
import { api, DataSource } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Panel } from "@/components/ui/Panel";

const SOURCE_OPTIONS: {
  type: string;
  label: string;
  fields: { key: string; label: string; placeholder?: string; multiline?: boolean }[];
  hint?: string;
}[] = [
  {
    type: "hubspot",
    label: "HubSpot CRM",
    fields: [{ key: "access_token", label: "Private app access token" }],
    hint: "Creates daily leads, opportunities, closed-won, and revenue metrics for the full funnel. Seeds a Success Contract when first connected.",
  },
  {
    type: "google_ads",
    label: "Google Ads (live)",
    fields: [
      { key: "customer_id", label: "Customer ID", placeholder: "1234567890" },
      {
        key: "login_customer_id",
        label: "MCC / login customer ID (optional)",
        placeholder: "9876543210",
      },
      { key: "developer_token", label: "Developer token (or set in Settings)" },
      { key: "refresh_token", label: "OAuth refresh token (adwords scope)" },
      { key: "access_token", label: "Access token (optional if refresh set)" },
    ],
    hint: "Pulls last 30 days of campaign impressions, clicks, cost, conversions. Needs Ads API developer token + OAuth with adwords scope.",
  },
  {
    type: "meta_ads",
    label: "Meta Ads (live)",
    fields: [
      { key: "access_token", label: "Access token (ads_read)" },
      { key: "ad_account_id", label: "Ad account ID", placeholder: "act_1234567890" },
    ],
    hint: "Pulls last 30 days of campaign insights (spend, clicks, conversions).",
  },
  {
    type: "ads_csv",
    label: "Ads (CSV)",
    fields: [
      {
        key: "csv_text",
        label: "CSV data",
        placeholder:
          "date,campaign,impressions,clicks,cost,conversions,conversion_value\n2026-07-01,Brand,1000,50,25.5,3,150",
        multiline: true,
      },
    ],
    hint: "Paste Google/Meta export rows when live API access is not available yet.",
  },
  {
    type: "gbp",
    label: "Google Business Profile",
    fields: [
      {
        key: "location_id",
        label: "Location ID (live API)",
        placeholder: "locations/1234567890 or bare numeric id",
      },
      {
        key: "location_name",
        label: "Location name (optional)",
        placeholder: "Acme Roofing — Austin",
      },
      {
        key: "csv_text",
        label: "Fallback: GBP Insights CSV",
        placeholder:
          "Business Name,Search views,Map views,Website clicks,Direction requests,Phone calls,Direct searches,Discovery searches\nAcme Roofing,1200,800,90,60,40,700,500",
        multiline: true,
      },
    ],
    hint: "Preferred: set Location ID and re-auth Google (business.manage scope) for live Performance API sync. CSV remains a fallback.",
  },
  {
    type: "backlinks",
    label: "Backlinks",
    fields: [
      {
        key: "provider",
        label: "Provider",
        placeholder: "ahrefs or semrush",
      },
      {
        key: "api_key",
        label: "API key",
        placeholder: "Ahrefs/SEMrush API token",
      },
      {
        key: "domain",
        label: "Domain",
        placeholder: "example.com",
      },
      {
        key: "csv_text",
        label: "Fallback: backlink export CSV",
        placeholder:
          "Domain,Referring Domains,Total Backlinks,Domain Rating,New Links (30d),Lost Links (30d),Toxic Score\nexample.com,420,1800,38,12,3,5",
        multiline: true,
      },
    ],
    hint: "Preferred: API key + domain for live Ahrefs/SEMrush overview. CSV export remains a fallback.",
  },
  {
    type: "bing",
    label: "Bing Webmaster",
    fields: [
      { key: "api_key", label: "API key" },
      { key: "site_url", label: "Site URL", placeholder: "https://example.com" },
    ],
  },
  {
    type: "pagespeed",
    label: "PageSpeed Insights",
    fields: [
      { key: "api_key", label: "API key (optional if set in Settings)" },
      { key: "site_url", label: "Page URL", placeholder: "https://example.com" },
    ],
    hint: "If Settings has a PageSpeed API key, Sync auto-creates this for clients with a known URL.",
  },
  {
    type: "clarity",
    label: "Microsoft Clarity",
    fields: [
      {
        key: "api_token",
        label: "Project API token (optional if set in Settings)",
        placeholder: "Clarity Data Export token",
      },
    ],
    hint: "Uses Clarity Data Export API (URL dimension). Stores page-level sessions, derived bounce, rage/dead clicks. Settings token auto-wires on sync.",
  },
  {
    type: "crux",
    label: "Chrome UX Report (CrUX)",
    fields: [],
    hint: "Uses your PageSpeed API key from Settings. Syncs real-user LCP/INP/CLS for top GSC pages after each sync.",
  },
  {
    type: "cloudflare",
    label: "Cloudflare (zone link)",
    fields: [{ key: "domains", label: "Domain(s)", placeholder: "example.com" }],
    hint: "Usually created during Cloudflare onboarding. Add only if this client needs an extra zone link.",
  },
];

type Props = {
  clientId: number;
  datasources: DataSource[];
  onChanged: (list: DataSource[]) => void;
};

function statusTone(status?: string | null): "brand" | "success" | "warning" | "default" {
  const s = (status || "pending").toLowerCase();
  if (s === "connected" || s === "active" || s === "ok") return "success";
  if (s === "error" || s === "failed" || s === "reauth_required") return "warning";
  if (s.includes("sync")) return "brand";
  return "default";
}

export default function DatasourcesPanel({ clientId, datasources, onChanged }: Props) {
  const { success, error } = useToast();
  const [adding, setAdding] = useState(false);
  const [sourceType, setSourceType] = useState(SOURCE_OPTIONS[0]?.type ?? "");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<DataSource | null>(null);

  const option = SOURCE_OPTIONS.find((o) => o.type === sourceType) ?? SOURCE_OPTIONS[0];
  if (!option) return null;

  const refresh = async () => {
    const list = await api.clients.datasources.list(clientId);
    onChanged(list);
  };

  const handleAdd = async () => {
    setBusy(true);
    try {
      const credentials: Record<string, unknown> = {};
      for (const f of option.fields) {
        const v = (fields[f.key] || "").trim();
        if (v) {
          if (f.key === "domains") credentials.domains = v.split(/[,\s]+/).filter(Boolean);
          else credentials[f.key] = v;
        }
      }
      await api.clients.datasources.create(clientId, {
        type: sourceType,
        credentials: Object.keys(credentials).length ? credentials : undefined,
      });
      // CSV sources only become useful after sync — pull them in immediately.
      if (["ads_csv", "gbp", "backlinks"].includes(sourceType)) {
        await api.metrics.sync(clientId);
      }
      await refresh();
      setFields({});
      setAdding(false);
      success(`${option.label} connected`);
    } catch (e) {
      error(e instanceof Error ? e.message : "Failed to add datasource");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await api.clients.datasources.delete(clientId, confirmDelete.id);
      await refresh();
      success(`${confirmDelete.type.toUpperCase()} removed`);
      setConfirmDelete(null);
    } catch {
      error("Failed to remove datasource");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="section-label flex items-center gap-1.5">
          <Database size={12} /> Data sources
        </p>
        {!adding && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setAdding(true)}
            className="!text-kinexis-focus hover:!text-kinexis-focus"
          >
            <Plus size={11} /> Add
          </Button>
        )}
      </div>

      {datasources.length === 0 ? (
        <p className="text-muted py-1 text-xs leading-relaxed">
          No sources connected yet. Add HubSpot, Ads, GBP, Backlinks, Bing, or PageSpeed.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {datasources.map((ds) => (
            <li
              key={ds.id}
              className="flex items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] py-1.5 text-xs last:border-0"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="font-semibold uppercase text-ink">{ds.type}</span>
                <Badge tone={statusTone(ds.status)}>
                  {(ds.status || "pending").replace("_", " ")}
                </Badge>
                <span className="text-muted">
                  {ds.last_synced_at ? ds.last_synced_at.slice(0, 10) : "never synced"}
                </span>
              </div>
              <IconButton
                label={`Remove ${ds.type}`}
                size="sm"
                disabled={busy}
                onClick={() => setConfirmDelete(ds)}
                className="!h-6 !w-6 hover:!text-kinexis-risk"
              >
                <Trash2 size={12} />
              </IconButton>
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <div className="space-y-2.5 border-t border-[color:var(--border-subtle)] pt-1">
          <Select
            label="Source type"
            value={sourceType}
            onChange={(e) => {
              setSourceType(e.target.value);
              setFields({});
            }}
            className="!py-2 !text-xs"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.type} value={o.type}>
                {o.label}
              </option>
            ))}
          </Select>
          {option.hint && <p className="text-muted text-[11px] leading-relaxed">{option.hint}</p>}
          {option.fields.map((f) =>
            f.multiline ? (
              <Textarea
                key={f.key}
                label={f.label}
                className="!min-h-[120px] !py-2 font-mono !text-xs"
                value={fields[f.key] || ""}
                onChange={(e) => setFields((prev) => ({ ...prev, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                autoComplete="off"
              />
            ) : (
              <Input
                key={f.key}
                label={f.label}
                className="!py-2 !text-xs"
                type={f.key.includes("key") || f.key.includes("token") ? "password" : "text"}
                value={fields[f.key] || ""}
                onChange={(e) => setFields((prev) => ({ ...prev, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                autoComplete="off"
              />
            )
          )}
          <div className="flex gap-2">
            <Button type="button" variant="soft" onClick={() => void handleAdd()} disabled={busy}>
              {busy ? "Saving…" : "Save source"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setAdding(false);
                setFields({});
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title={`Remove ${confirmDelete?.type.toUpperCase()}?`}
        description="This disconnects the data source from this client. You can add it again later."
        confirmLabel="Remove"
        danger
        busy={busy}
        onConfirm={() => void handleDelete()}
        onCancel={() => !busy && setConfirmDelete(null)}
      />
    </Panel>
  );
}
