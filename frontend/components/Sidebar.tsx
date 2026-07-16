"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  Plus,
  Cloud,
  LogOut,
  User,
  X,
  LayoutGrid,
  Cog,
  Search,
  Archive,
  ArchiveRestore,
  Trash2,
  MoreVertical,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { api, Client } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Menu, MenuItem, MenuSeparator, MenuIconTrigger } from "@/components/ui/Menu";

type SidebarProps = {
  selectedClientId: number | null;
  activeTab: string;
  onSelectClient: (id: number) => void;
  onNavigate: (tab: "portfolio" | "settings") => void;
  onSignOut: () => void | Promise<void>;
  onClientsLoaded?: (clients: Client[]) => void;
  onClientRemoved?: (id: number) => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
};

export default function Sidebar({
  selectedClientId,
  activeTab,
  onSelectClient,
  onNavigate,
  onSignOut,
  onClientsLoaded,
  onClientRemoved,
  mobileOpen = false,
  onMobileClose,
}: SidebarProps) {
  const { success, error } = useToast();
  const [clients, setClients] = useState<Client[]>([]);
  const [archived, setArchived] = useState<Client[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [filter, setFilter] = useState("");
  const [authStatus, setAuthStatus] = useState<{
    cloudflare: { connected: boolean; email: string; account_name: string };
    google: { connected: boolean; email: string; configured?: boolean };
  } | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Client | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const onClientsLoadedRef = useRef(onClientsLoaded);
  onClientsLoadedRef.current = onClientsLoaded;

  const loadClients = useCallback(async () => {
    try {
      const [activeList, allList] = await Promise.all([
        api.clients.list(false),
        api.clients.list(true),
      ]);
      setClients(activeList);
      setArchived(allList.filter((c) => c.archived));
      onClientsLoadedRef.current?.(activeList);
    } catch {
      error("Failed to load clients");
      onClientsLoadedRef.current?.([]);
    }
  }, [error]);

  useEffect(() => {
    void loadClients();
    api.auth
      .status()
      .then(setAuthStatus)
      .catch((e) => {
        console.warn("Failed to load auth status", e);
      });
  }, [loadClients]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return clients;
    return clients.filter(
      (c) =>
        c.name.toLowerCase().includes(q) || (c.industry && c.industry.toLowerCase().includes(q))
    );
  }, [clients, filter]);

  const filteredArchived = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return archived;
    return archived.filter(
      (c) =>
        c.name.toLowerCase().includes(q) || (c.industry && c.industry.toLowerCase().includes(q))
    );
  }, [archived, filter]);

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

  const addClient = async () => {
    if (!newName.trim()) return;
    try {
      const c = await api.clients.create({ name: newName.trim() });
      setClients((prev) => {
        const next = [...prev, c];
        onClientsLoaded?.(next);
        return next;
      });
      setNewName("");
      setShowAdd(false);
      onSelectClient(c.id);
      onMobileClose?.();
      success(`Added ${c.name}`);
    } catch {
      error("Failed to create client");
    }
  };

  const selectClient = (id: number) => {
    onSelectClient(id);
    onMobileClose?.();
  };

  const go = (tab: "portfolio" | "settings") => {
    onNavigate(tab);
    onMobileClose?.();
  };

  const archiveClient = async (client: Client) => {
    setIsProcessing(true);
    try {
      await api.clients.archive(client.id);
      setClients((prev) => prev.filter((c) => c.id !== client.id));
      setArchived((prev) => [...prev, { ...client, archived: true }]);
      onClientRemoved?.(client.id);
      success(`Archived ${client.name}`, {
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await api.clients.unarchive(client.id);
              setArchived((prev) => prev.filter((c) => c.id !== client.id));
              setClients((prev) => {
                const next = [...prev, { ...client, archived: false }].sort((a, b) =>
                  a.name.localeCompare(b.name)
                );
                onClientsLoaded?.(next);
                return next;
              });
              success(`Restored ${client.name}`);
            } catch {
              error("Failed to restore client");
            }
          },
        },
      });
    } catch {
      error("Failed to archive client");
    } finally {
      setIsProcessing(false);
    }
  };

  const restoreClient = async (client: Client) => {
    setIsProcessing(true);
    try {
      await api.clients.unarchive(client.id);
      setArchived((prev) => prev.filter((c) => c.id !== client.id));
      setClients((prev) => {
        const next = [...prev, { ...client, archived: false }].sort((a, b) =>
          a.name.localeCompare(b.name)
        );
        onClientsLoaded?.(next);
        return next;
      });
      success(`Restored ${client.name}`);
    } catch {
      error("Failed to restore client");
    } finally {
      setIsProcessing(false);
    }
  };

  const deleteClient = async () => {
    if (!confirmDelete) return;
    setIsProcessing(true);
    try {
      await api.clients.delete(confirmDelete.id);
      setClients((prev) => prev.filter((c) => c.id !== confirmDelete.id));
      setArchived((prev) => prev.filter((c) => c.id !== confirmDelete.id));
      onClientRemoved?.(confirmDelete.id);
      success(`Deleted ${confirmDelete.name}`);
      setConfirmDelete(null);
    } catch {
      error("Failed to delete client");
    } finally {
      setIsProcessing(false);
    }
  };

  const renderClientRow = (client: Client, opts: { archived?: boolean } = {}) => {
    const active =
      !opts.archived &&
      selectedClientId === client.id &&
      activeTab !== "portfolio" &&
      activeTab !== "settings";

    return (
      <div
        key={client.id}
        className={`motion-micro group flex items-center gap-1 pr-1 ${
          active ? "nav-row-active" : "hover:bg-[color:var(--hover-fill)]"
        }`}
        style={{ borderRadius: "var(--radius-md)" }}
      >
        <button
          type="button"
          onClick={() => (opts.archived ? undefined : selectClient(client.id))}
          disabled={opts.archived}
          className={`nav-item min-w-0 flex-1 !bg-transparent !py-2.5 !shadow-none ${
            active ? "text-ink" : "nav-item-idle"
          } ${opts.archived ? "cursor-default opacity-70" : ""}`}
        >
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="truncate">{client.name}</span>
            {!opts.archived && client.priority && client.priority >= 2 && (
              <span className="shrink-0 rounded bg-kinexis-focus/10 px-1.5 py-0.5 text-[11px] font-bold text-kinexis-focus">
                P{client.priority}
              </span>
            )}
          </div>
        </button>
        <Menu
          align="right"
          side="auto"
          trigger={({ open, toggle, menuId }) => (
            <MenuIconTrigger
              label={`Actions for ${client.name}`}
              open={open}
              menuId={menuId}
              onClick={toggle}
              disabled={isProcessing}
              className={
                open || active
                  ? "text-ink opacity-100"
                  : "text-muted/60 opacity-0 hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
              }
            >
              <MoreVertical size={15} strokeWidth={2} />
            </MenuIconTrigger>
          )}
        >
          {opts.archived ? (
            <MenuItem
              icon={<ArchiveRestore size={13} />}
              disabled={isProcessing}
              onClick={() => void restoreClient(client)}
            >
              Restore
            </MenuItem>
          ) : (
            <MenuItem
              icon={<Archive size={13} />}
              disabled={isProcessing}
              onClick={() => void archiveClient(client)}
            >
              Archive
            </MenuItem>
          )}
          <MenuSeparator />
          <MenuItem
            danger
            icon={<Trash2 size={13} />}
            disabled={isProcessing}
            onClick={() => setConfirmDelete(client)}
          >
            Delete
          </MenuItem>
        </Menu>
      </div>
    );
  };

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="animate-fade-in fixed inset-0 z-40 bg-ink/40 backdrop-blur-sm lg:hidden"
          onClick={onMobileClose}
        />
      )}

      <aside
        className={`shell-rail motion-micro-transform fixed inset-y-0 left-0 z-50 flex h-full w-[var(--rail-w)] shrink-0 flex-col lg:static ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"} `}
      >
        {/* Workspace nav */}
        <div className="px-4 pb-4 pt-6">
          <div className="mb-5 flex items-center justify-between px-1 lg:hidden">
            <div className="flex items-center gap-2.5">
              <div className="mark">
                <img src="/logo.svg" alt="Kinexis" />
              </div>
              <span className="text-wordmark text-[18px] leading-none">Kinexis</span>
            </div>
            {onMobileClose && (
              <button
                type="button"
                onClick={onMobileClose}
                className="icon-btn"
                aria-label="Close sidebar"
              >
                <X size={16} />
              </button>
            )}
          </div>

          <p className="section-label text-muted mb-2.5 px-3 text-[12px] font-semibold">
            Workspace
          </p>
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => go("portfolio")}
              className={`nav-item !py-2.5 ${
                activeTab === "portfolio" || (!selectedClientId && activeTab !== "settings")
                  ? "nav-item-active"
                  : "nav-item-idle"
              }`}
            >
              <LayoutGrid size={16} className="shrink-0 opacity-70" strokeWidth={1.75} />
              Portfolio
            </button>
            <button
              type="button"
              onClick={() => go("settings")}
              className={`nav-item !py-2.5 ${
                activeTab === "settings" ? "nav-item-active" : "nav-item-idle"
              }`}
            >
              <Cog size={16} className="shrink-0 opacity-70" strokeWidth={1.75} />
              Settings
            </button>
          </div>
        </div>

        {/* Filter */}
        <div className="px-4 pb-3">
          <div className="relative">
            <Search
              size={15}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-dim"
              strokeWidth={1.75}
            />
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter clients…"
              className="input-field !py-2.5 !pl-10 !text-[13px]"
            />
          </div>
        </div>

        {/* Clients */}
        <nav className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="mb-2.5 mt-2 flex items-center justify-between px-1">
            <span className="section-label text-muted text-[12px] font-semibold">Clients</span>
            <button
              type="button"
              onClick={() => setShowAdd(!showAdd)}
              className="icon-btn !h-7 !w-7"
              title="Add client"
              aria-label="Add client"
            >
              <Plus size={15} strokeWidth={2} />
            </button>
          </div>

          {showAdd && (
            <div className="animate-fade-up mb-3 px-0.5">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void addClient()}
                placeholder="Client name…"
                className="input-field !py-2.5 !text-[13px]"
                autoFocus
              />
            </div>
          )}

          <div className="space-y-0.5">
            {filtered.map((client) => renderClientRow(client))}
            {clients.length === 0 && (
              <p className="px-3 py-14 text-center text-[13px] leading-relaxed text-ink-dim">
                Add your first client to begin
              </p>
            )}
            {clients.length > 0 && filtered.length === 0 && filter.trim() && (
              <p className="px-3 py-8 text-center text-[13px] text-ink-dim">No matching clients</p>
            )}
          </div>

          {(archived.length > 0 || filteredArchived.length > 0) && (
            <div className="mt-6 border-t border-[color:var(--border-subtle)] pt-4">
              <button
                type="button"
                onClick={() => setShowArchived((v) => !v)}
                aria-expanded={showArchived}
                aria-controls="archived-clients-panel"
                className="motion-micro flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[color:var(--hover-fill)]"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                {showArchived ? (
                  <ChevronDown size={14} className="shrink-0 text-ink-dim" strokeWidth={1.75} />
                ) : (
                  <ChevronRight size={14} className="shrink-0 text-ink-dim" strokeWidth={1.75} />
                )}
                <span className="section-label text-muted text-[12px] font-semibold">Archived</span>
                <span className="ml-auto text-[12px] font-medium tabular-nums text-ink-dim">
                  {filteredArchived.length}
                </span>
              </button>
              {showArchived && (
                <div id="archived-clients-panel" className="mt-1.5 space-y-0.5">
                  {filteredArchived.map((client) => renderClientRow(client, { archived: true }))}
                  {filteredArchived.length === 0 && (
                    <p className="px-3 py-4 text-center text-[13px] text-ink-dim">
                      No matching archived clients
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </nav>

        {/* Accounts footer */}
        <div className="border-t border-[color:var(--border-subtle)] px-4 py-4">
          <Menu
            align="left"
            side="top"
            className="w-full"
            contentClassName="!min-w-full left-0 right-0"
            trigger={({ open, toggle, menuId }) => (
              <button
                type="button"
                onClick={toggle}
                aria-expanded={open}
                aria-haspopup="menu"
                aria-controls={open ? menuId : undefined}
                className={`motion-micro flex w-full items-center gap-3 px-3 py-3 text-[13px] font-medium ${
                  open
                    ? "bg-kinexis-focus/10 text-kinexis-focus"
                    : "text-ink-secondary hover:bg-[color:var(--hover-fill)] hover:text-ink"
                }`}
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <span
                  className={`inline-flex h-7 w-7 shrink-0 items-center justify-center ${
                    open
                      ? "bg-kinexis-focus/15 text-kinexis-focus"
                      : "text-muted bg-[color:var(--hover-fill)]"
                  }`}
                  style={{ borderRadius: "var(--radius-sm)" }}
                >
                  <User size={14} strokeWidth={1.75} />
                </span>
                <span className="flex-1 truncate text-left">Accounts</span>
                <ChevronDown
                  size={14}
                  className={`text-muted motion-micro-transform shrink-0 ${
                    open ? "rotate-180" : ""
                  }`}
                  strokeWidth={1.75}
                />
              </button>
            )}
          >
            <div className="border-b border-[color:var(--border-subtle)] px-3.5 py-3">
              <p className="section-label text-muted mb-3 text-[12px] font-semibold">Signed in</p>
              <div className="space-y-3">
                <div className="flex items-start gap-2.5">
                  <Cloud size={14} className="mt-0.5 shrink-0 text-[#F6821F]" strokeWidth={1.75} />
                  <div className="min-w-0">
                    <p className="text-muted mb-0.5 text-[12px] font-medium">Cloudflare</p>
                    <p
                      className="truncate text-[13px] leading-snug text-ink"
                      title={authStatus?.cloudflare.account_name || authStatus?.cloudflare.email}
                    >
                      {authStatus
                        ? authStatus.cloudflare.account_name ||
                          authStatus.cloudflare.email ||
                          "Not connected"
                        : "Checking…"}
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <svg
                    viewBox="0 0 24 24"
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                    aria-hidden="true"
                  >
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  <div className="min-w-0">
                    <p className="text-muted mb-0.5 text-[12px] font-medium">Google</p>
                    <p
                      className="truncate text-[13px] leading-snug text-ink"
                      title={authStatus?.google.email}
                    >
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
        </div>
      </aside>

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
      <ConfirmDialog
        open={!!confirmDelete}
        title={`Delete ${confirmDelete?.name}?`}
        description="This permanently removes the client, metrics, insights, and tasks. Prefer Archive if you might need them later."
        confirmLabel="Delete forever"
        danger
        busy={isProcessing}
        onConfirm={() => void deleteClient()}
        onCancel={() => !isProcessing && setConfirmDelete(null)}
      />
    </>
  );
}
