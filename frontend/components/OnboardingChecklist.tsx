"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { X, CheckCircle2, Circle, ArrowRight } from "lucide-react";

const STORAGE_KEY = "kinexis_onboarding_checklist_v2";

type StepId =
  | "add_client"
  | "connect_gsc"
  | "connect_ga4"
  | "connect_crm"
  | "sync"
  | "contract"
  | "situation"
  | "fix"
  | "prove"
  | "report";

type Props = {
  clientCount: number;
  hasSynced?: boolean;
  hasGsc?: boolean;
  hasGa4?: boolean;
  hasHubspot?: boolean;
  hasContract?: boolean;
  hasVisitedSituation?: boolean;
  hasCompletedFix?: boolean;
  hasProvenWin?: boolean;
  hasGeneratedReport?: boolean;
  onDismiss?: () => void;
  onGoPortfolio?: () => void;
  onAddClient?: () => void;
  onConnectGsc?: () => void;
  onConnectGa4?: () => void;
  onConnectCrm?: () => void;
  onSync?: () => void;
  onOpenContract?: () => void;
  onOpenSituation?: () => void;
  onOpenFixQueue?: () => void;
  onOpenProve?: () => void;
  onOpenReport?: () => void;
};

const STEPS: {
  id: StepId;
  label: string;
  hint: string;
  cta: string;
}[] = [
  {
    id: "add_client",
    label: "Add a client",
    hint: "Command bar switcher → add client",
    cta: "Open clients",
  },
  {
    id: "connect_gsc",
    label: "Connect GSC (required)",
    hint: "Organic demand + CTR diagnosis needs Search Console",
    cta: "Connect GSC",
  },
  {
    id: "connect_ga4",
    label: "Connect GA4 (required)",
    hint: "Sessions + conversions for CRO and funnel proof",
    cta: "Connect GA4",
  },
  {
    id: "connect_crm",
    label: "Connect HubSpot (required)",
    hint: "Leads & revenue unlock commercial Success Contracts + Prove",
    cta: "Open Settings",
  },
  {
    id: "sync",
    label: "Sync data",
    hint: "Pull GSC / GA4 / HubSpot — keep sync < 7 days stale",
    cta: "Sync now",
  },
  {
    id: "contract",
    label: "Set Success Contract",
    hint: "Primary KPI (usually HubSpot leads) + target lift",
    cta: "Set contract",
  },
  {
    id: "situation",
    label: "Review Situation",
    hint: "Detect → Situation — see the top growth lever",
    cta: "Open Situation",
  },
  {
    id: "fix",
    label: "Ship 3–5 ranked fixes / week",
    hint: "Prescribe → Start → Execute → done (baseline auto-captures)",
    cta: "Open Fix queue",
  },
  {
    id: "prove",
    label: "Wait for Prove",
    hint: "Never report a win until recheck on the contract KPI",
    cta: "Open Prove",
  },
  {
    id: "report",
    label: "Lead report with contract + proven levers",
    hint: "Report library → Generate — outcomes first, vanity SEO last",
    cta: "Open Report",
  },
];

export default function OnboardingChecklist({
  clientCount,
  hasSynced = false,
  hasGsc = false,
  hasGa4 = false,
  hasHubspot = false,
  hasContract = false,
  hasVisitedSituation = false,
  hasCompletedFix = false,
  hasProvenWin = false,
  hasGeneratedReport = false,
  onDismiss,
  onGoPortfolio,
  onAddClient,
  onConnectGsc,
  onConnectGa4,
  onConnectCrm,
  onSync,
  onOpenContract,
  onOpenSituation,
  onOpenFixQueue,
  onOpenProve,
  onOpenReport,
}: Props) {
  const [dismissed, setDismissed] = useState(true);
  const [done, setDone] = useState<Partial<Record<StepId, boolean>>>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.dismissed) {
          setDismissed(true);
          return;
        }
        setDone(parsed?.done || {});
        setDismissed(false);
      } else {
        setDismissed(false);
      }
    } catch {
      setDismissed(false);
    }
  }, []);

  useEffect(() => {
    setDone((prev) => {
      const next = {
        ...prev,
        add_client: prev.add_client || clientCount > 0,
        connect_gsc: prev.connect_gsc || hasGsc,
        connect_ga4: prev.connect_ga4 || hasGa4,
        connect_crm: prev.connect_crm || hasHubspot,
        sync: prev.sync || hasSynced,
        contract: prev.contract || hasContract,
        situation: prev.situation || hasVisitedSituation,
        fix: prev.fix || hasCompletedFix,
        prove: prev.prove || hasProvenWin,
        report: prev.report || hasGeneratedReport,
      };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ dismissed: false, done: next }));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [
    clientCount,
    hasGsc,
    hasGa4,
    hasHubspot,
    hasSynced,
    hasContract,
    hasVisitedSituation,
    hasCompletedFix,
    hasProvenWin,
    hasGeneratedReport,
  ]);

  if (dismissed) return null;

  const completedCount = STEPS.filter((s) => done[s.id]).length;
  const nextStep = STEPS.find((s) => !done[s.id]);

  const runCta = (id: StepId) => {
    switch (id) {
      case "add_client":
        onAddClient?.();
        break;
      case "connect_gsc":
        (onConnectGsc || onConnectCrm)?.();
        break;
      case "connect_ga4":
        (onConnectGa4 || onConnectCrm)?.();
        break;
      case "connect_crm":
        onConnectCrm?.();
        break;
      case "sync":
        onSync?.();
        break;
      case "contract":
        (onOpenContract || onOpenSituation)?.();
        break;
      case "situation":
        onOpenSituation?.();
        break;
      case "fix":
        onOpenFixQueue?.();
        break;
      case "prove":
        (onOpenProve || onOpenFixQueue)?.();
        break;
      case "report":
        onOpenReport?.();
        break;
      default:
        onGoPortfolio?.();
    }
  };

  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ dismissed: true, done }));
    } catch {
      /* ignore */
    }
    onDismiss?.();
  };

  return (
    <Panel className="mb-4 border border-[color:var(--border-subtle)] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-dim">
            Agency operating system
          </p>
          <h3 className="text-[15px] font-semibold text-ink">
            Mandate connectors → ship → prove → report
          </h3>
          <p className="text-muted mt-1 text-[12px]">
            {completedCount}/{STEPS.length} complete
            {nextStep ? ` · Next: ${nextStep.label}` : " · Ready for the book"}
          </p>
        </div>
        <button
          type="button"
          className="text-muted hover:text-ink"
          aria-label="Dismiss checklist"
          onClick={dismiss}
        >
          <X size={16} />
        </button>
      </div>
      <ul className="space-y-2">
        {STEPS.map((step) => {
          const isDone = Boolean(done[step.id]);
          return (
            <li key={step.id} className="flex items-start gap-2">
              {isDone ? (
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-kinexis-proof" />
              ) : (
                <Circle size={16} className="mt-0.5 shrink-0 text-ink-dim" />
              )}
              <div className="min-w-0 flex-1">
                <p className={`text-[13px] font-medium ${isDone ? "text-ink-dim" : "text-ink"}`}>
                  {step.label}
                </p>
                <p className="text-muted text-[12px]">{step.hint}</p>
              </div>
              {!isDone && (
                <Button size="sm" variant="soft" onClick={() => runCta(step.id)}>
                  {step.cta}
                  <ArrowRight size={12} />
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
