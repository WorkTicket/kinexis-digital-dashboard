"use client";

import TitleBar from "@/components/TitleBar";
import ConnectAccounts from "@/components/ConnectAccounts";

type Props = {
  onReady: () => void | Promise<void>;
};

export default function ShellLoginGate({ onReady }: Props) {
  return (
    <div className="app-shell flex flex-col overflow-hidden">
      <TitleBar />
      <div className="flex-1 overflow-y-auto">
        <ConnectAccounts onReady={onReady} />
      </div>
    </div>
  );
}
