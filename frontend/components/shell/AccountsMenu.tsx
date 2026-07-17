"use client";

import { useEffect, useState } from "react";
import { Cloud, LogOut, User, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Menu, MenuItem } from "@/components/ui/Menu";
import {
  CLOUDFLARE_ORANGE,
  GOOGLE_BLUE,
  GOOGLE_GREEN,
  GOOGLE_YELLOW,
  GOOGLE_RED,
} from "@/lib/brandColors";

type Props = {
  onSignOut: () => void | Promise<void>;
};

export default function AccountsMenu({ onSignOut }: Props) {
  const { error } = useToast();
  const [signingOut, setSigningOut] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [authStatus, setAuthStatus] = useState<{
    cloudflare: { connected: boolean; email: string; account_name: string };
    google: { connected: boolean; email: string; configured?: boolean };
  } | null>(null);

  useEffect(() => {
    api.auth
      .status()
      .then(setAuthStatus)
      .catch(() => {});
  }, []);

  const doSignOut = async () => {
    setSigningOut(true);
    try {
      await onSignOut();
      setConfirmSignOut(false);
    } catch {
      error("Sign out failed");
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <>
      <Menu
        align="right"
        side="bottom"
        trigger={({ open, toggle, menuId }) => (
          <button
            type="button"
            onClick={toggle}
            aria-expanded={open}
            aria-haspopup="menu"
            aria-controls={open ? menuId : undefined}
            aria-label="Accounts"
            className={`icon-btn titlebar-no-drag !w-auto gap-2 !px-2 ${
              open ? "text-kinexis-focus" : ""
            }`}
          >
            <User size={15} strokeWidth={1.5} />
            <ChevronDown
              size={12}
              className={`text-muted motion-micro-transform hidden sm:block ${open ? "rotate-180" : ""}`}
              strokeWidth={1.75}
            />
          </button>
        )}
      >
        <div className="border-b border-[color:var(--border-subtle)] px-4 py-3">
          <p className="section-label text-muted mb-3 text-[11px] font-semibold">Signed in</p>
          <div className="space-y-3">
            <div className="flex items-start gap-2">
              <Cloud
                size={14}
                className="mt-0.5 shrink-0"
                strokeWidth={1.75}
                style={{ color: CLOUDFLARE_ORANGE }}
              />
              <div className="min-w-0">
                <p className="text-muted mb-0.5 text-[11px] font-medium">Cloudflare</p>
                <p className="truncate text-[13px] leading-snug text-ink">
                  {authStatus
                    ? authStatus.cloudflare.account_name ||
                      authStatus.cloudflare.email ||
                      "Not connected"
                    : "Checking…"}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <svg viewBox="0 0 24 24" className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden>
                <path
                  fill={GOOGLE_BLUE}
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill={GOOGLE_GREEN}
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill={GOOGLE_YELLOW}
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill={GOOGLE_RED}
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              <div className="min-w-0">
                <p className="text-muted mb-0.5 text-[11px] font-medium">Google</p>
                <p className="truncate text-[13px] leading-snug text-ink">
                  {authStatus ? authStatus.google.email || "Not connected" : "Checking…"}
                </p>
              </div>
            </div>
          </div>
        </div>
        <MenuItem
          danger
          icon={<LogOut size={14} />}
          disabled={signingOut}
          onClick={() => setConfirmSignOut(true)}
        >
          Sign out
        </MenuItem>
      </Menu>

      <ConfirmDialog
        open={confirmSignOut}
        title="Sign out?"
        description="You'll need to reconnect Cloudflare to use Kinexis again."
        confirmLabel="Sign out"
        danger
        busy={signingOut}
        onConfirm={() => void doSignOut()}
        onCancel={() => !signingOut && setConfirmSignOut(false)}
      />
    </>
  );
}
