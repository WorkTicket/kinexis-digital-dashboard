"use client";

import OnboardingChecklist from "@/components/OnboardingChecklist";
import PortfolioView from "@/components/PortfolioView";

type Props = {
  clientCount: number;
  hasSynced: boolean;
  hasGsc?: boolean;
  hasGa4?: boolean;
  hasHubspot?: boolean;
  hasContract?: boolean;
  hasVisitedSituation: boolean;
  hasCompletedFix: boolean;
  hasProvenWin?: boolean;
  hasGeneratedReport: boolean;
  onGoPortfolio: () => void;
  onAddClient: () => void;
  onConnectCrm?: () => void;
  onSync: () => void;
  onOpenSituation: () => void;
  onOpenFixQueue: () => void;
  onOpenProve?: () => void;
  onOpenReport: () => void;
  onSelectClient: (id: number) => void;
  onOpenClient: (
    clientId: number,
    hint?: {
      open_insights?: number;
      open_tasks?: number;
      risk?: string;
      tab?: string;
      insight_id?: number;
      task_id?: number;
    }
  ) => void;
  onCompare?: () => void;
};

export default function PortfolioHomeContent({
  clientCount,
  hasSynced,
  hasGsc = false,
  hasGa4 = false,
  hasHubspot = false,
  hasContract = false,
  hasVisitedSituation,
  hasCompletedFix,
  hasProvenWin = false,
  hasGeneratedReport,
  onGoPortfolio,
  onAddClient,
  onConnectCrm,
  onSync,
  onOpenSituation,
  onOpenFixQueue,
  onOpenProve,
  onOpenReport,
  onSelectClient,
  onOpenClient,
  onCompare,
}: Props) {
  return (
    <>
      <div className="workspace-content !pb-0">
        <OnboardingChecklist
          clientCount={clientCount}
          hasSynced={hasSynced}
          hasGsc={hasGsc}
          hasGa4={hasGa4}
          hasHubspot={hasHubspot}
          hasContract={hasContract}
          hasVisitedSituation={hasVisitedSituation}
          hasCompletedFix={hasCompletedFix}
          hasProvenWin={hasProvenWin}
          hasGeneratedReport={hasGeneratedReport}
          onGoPortfolio={onGoPortfolio}
          onAddClient={onAddClient}
          onConnectGsc={onConnectCrm}
          onConnectGa4={onConnectCrm}
          onConnectCrm={onConnectCrm}
          onSync={onSync}
          onOpenContract={onOpenSituation}
          onOpenSituation={onOpenSituation}
          onOpenFixQueue={onOpenFixQueue}
          onOpenProve={onOpenProve}
          onOpenReport={onOpenReport}
        />
      </div>
      <PortfolioView
        onSelectClient={onSelectClient}
        onOpenClient={onOpenClient}
        onCompare={onCompare}
      />
    </>
  );
}
