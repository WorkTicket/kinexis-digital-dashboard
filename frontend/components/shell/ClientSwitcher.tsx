"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  Plus,
  Search,
  Archive,
  ArchiveRestore,
  Trash2,
  MoreVertical,
  ChevronDown,
  ChevronRight,
  Check,
  LayoutGrid,
} from "lucide-react";
import { api, Client } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Menu, MenuItem, MenuSeparator, MenuIconTrigger } from "@/components/ui/Menu";

type Props = {
  selectedClientId: number | null;
  activeTab: string;
  onSelectClient: (id: number) => void;
  onGoPortfolio: () => void;
  onClientsLoaded?: (clients: Client[]) => void;
  onClientRemoved?: (id: number) => void;
  /** External open request (e.g. from empty-state “Add client”) */
  requestOpen?: number;
  onRequestAdd?: () => void;
};

export default function ClientSwitcher({
  selectedClientId,
  activeTab,
  onSelectClient,
  onGoPortfolio,
  onClientsLoaded,
  onClientRemoved,
  requestOpen = 0,
}: Props) {
  const { success, error } = useToast();
  const [open, setOpen] = useState(false);
  const [clients, setClients] = useState<Client[]>([]);
  const [archived, setArchived] = useState<Client[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [filter, setFilter] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<Client | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
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
  }, [loadClients]);

  useEffect(() => {
    if (requestOpen > 0) {
      setOpen(true);
      setShowAdd(true);
    }
  }, [requestOpen]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

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

  const selected = clients.find((c) => c.id === selectedClientId);
  const inClientWorkspace =
    Boolean(selectedClientId) && activeTab !== "portfolio" && activeTab !== "settings";
  const triggerLabel = inClientWorkspace && selected ? selected.name : "Mission Control";

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
      setOpen(false);
      onSelectClient(c.id);
      success(`Added ${c.name}`);
    } catch {
      error("Failed to create client");
    }
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

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="command-switcher titlebar-no-drag motion-micro flex max-w-[240px] items-center gap-2 px-3 py-2 text-left sm:max-w-[280px]"
      >
        {!inClientWorkspace && (
          <LayoutGrid size={14} className="shrink-0 text-ink-dim" strokeWidth={1.75} />
        )}
        <span className="truncate text-[13px] font-semibold text-ink">{triggerLabel}</span>
        <ChevronDown
          size={14}
          className={`text-muted motion-micro-transform shrink-0 ${open ? "rotate-180" : ""}`}
          strokeWidth={1.75}
        />
      </button>

      {open && (
        <div
          className="command-popover titlebar-no-drag absolute left-0 top-[calc(100%+6px)] z-[80] w-[min(360px,calc(100vw-2rem))] overflow-hidden"
          role="listbox"
        >
          <div className="border-b border-[color:var(--border-subtle)] p-2">
            <button
              type="button"
              onClick={() => {
                onGoPortfolio();
                setOpen(false);
              }}
              className={`motion-micro flex w-full items-center gap-2 px-3 py-3 text-left text-[13px] font-medium ${
                !inClientWorkspace
                  ? "bg-kinexis-focus/10 text-kinexis-focus"
                  : "text-ink-secondary hover:bg-[color:var(--hover-fill)] hover:text-ink"
              }`}
              style={{ borderRadius: "var(--radius-md)" }}
            >
              <LayoutGrid size={15} strokeWidth={1.75} className="shrink-0 opacity-70" />
              Mission Control
              {!inClientWorkspace && <Check size={14} className="ml-auto shrink-0" />}
            </button>
          </div>

          <div className="relative px-2 pt-2">
            <Search
              size={14}
              className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-ink-dim"
              strokeWidth={1.75}
            />
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Find a client…"
              className="input-field !py-2 !pl-9 !text-[13px]"
              autoFocus
            />
          </div>

          <div className="flex items-center justify-between px-3 pb-1 pt-3">
            <span className="section-label text-muted text-[11px] font-semibold">Clients</span>
            <button
              type="button"
              onClick={() => setShowAdd((v) => !v)}
              className="icon-btn !h-7 !w-7"
              aria-label="Add client"
            >
              <Plus size={14} strokeWidth={2} />
            </button>
          </div>

          {showAdd && (
            <div className="animate-fade-up px-2 pb-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void addClient()}
                placeholder="Client name…"
                className="input-field !py-2 !text-[13px]"
                autoFocus
              />
            </div>
          )}

          <div className="max-h-[280px] overflow-y-auto px-2 pb-2">
            <div className="space-y-0.5">
              {filtered.map((client) => {
                const active = inClientWorkspace && selectedClientId === client.id;
                return (
                  <div
                    key={client.id}
                    className={`motion-micro group flex items-center gap-0.5 ${
                      active ? "bg-kinexis-focus/10" : "hover:bg-[color:var(--hover-fill)]"
                    }`}
                    style={{ borderRadius: "var(--radius-md)" }}
                  >
                    <button
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => {
                        onSelectClient(client.id);
                        setOpen(false);
                      }}
                      className="flex min-w-0 flex-1 items-center gap-2 px-3 py-3 text-left text-[13px] font-medium text-ink"
                    >
                      <span className="truncate">{client.name}</span>
                      {client.priority != null && client.priority >= 2 && (
                        <span className="shrink-0 rounded bg-kinexis-focus/10 px-2 py-0.5 text-[11px] font-bold text-kinexis-focus">
                          P{client.priority}
                        </span>
                      )}
                      {active && (
                        <Check size={14} className="ml-auto shrink-0 text-kinexis-focus" />
                      )}
                    </button>
                    <Menu
                      align="right"
                      side="auto"
                      trigger={({ open: menuOpen, toggle, menuId }) => (
                        <MenuIconTrigger
                          label={`Actions for ${client.name}`}
                          open={menuOpen}
                          menuId={menuId}
                          onClick={toggle}
                          disabled={isProcessing}
                          className={
                            menuOpen || active
                              ? "text-ink opacity-100"
                              : "text-muted/60 opacity-0 hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
                          }
                        >
                          <MoreVertical size={14} strokeWidth={2} />
                        </MenuIconTrigger>
                      )}
                    >
                      <MenuItem
                        icon={<Archive size={13} />}
                        disabled={isProcessing}
                        onClick={() => void archiveClient(client)}
                      >
                        Archive
                      </MenuItem>
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
              })}
              {clients.length === 0 && (
                <p className="px-3 py-6 text-center text-[13px] text-ink-dim">
                  Add your first client to begin
                </p>
              )}
              {clients.length > 0 && filtered.length === 0 && filter.trim() && (
                <p className="px-3 py-6 text-center text-[13px] text-ink-dim">
                  No matching clients
                </p>
              )}
            </div>

            {(archived.length > 0 || filteredArchived.length > 0) && (
              <div className="mt-3 border-t border-[color:var(--border-subtle)] pt-2">
                <button
                  type="button"
                  onClick={() => setShowArchived((v) => !v)}
                  aria-expanded={showArchived}
                  className="motion-micro flex w-full items-center gap-2 px-3 py-2 text-left"
                  style={{ borderRadius: "var(--radius-md)" }}
                >
                  {showArchived ? (
                    <ChevronDown size={13} className="text-ink-dim" strokeWidth={1.75} />
                  ) : (
                    <ChevronRight size={13} className="text-ink-dim" strokeWidth={1.75} />
                  )}
                  <span className="section-label text-muted text-[11px] font-semibold">
                    Archived
                  </span>
                  <span className="ml-auto text-[11px] tabular-nums text-ink-dim">
                    {filteredArchived.length}
                  </span>
                </button>
                {showArchived &&
                  filteredArchived.map((client) => (
                    <div
                      key={client.id}
                      className="group flex items-center gap-0.5 opacity-70"
                      style={{ borderRadius: "var(--radius-md)" }}
                    >
                      <span className="min-w-0 flex-1 truncate px-3 py-2 text-[13px] text-ink">
                        {client.name}
                      </span>
                      <Menu
                        align="right"
                        side="auto"
                        trigger={({ open: menuOpen, toggle, menuId }) => (
                          <MenuIconTrigger
                            label={`Actions for ${client.name}`}
                            open={menuOpen}
                            menuId={menuId}
                            onClick={toggle}
                            disabled={isProcessing}
                          >
                            <MoreVertical size={14} strokeWidth={2} />
                          </MenuIconTrigger>
                        )}
                      >
                        <MenuItem
                          icon={<ArchiveRestore size={13} />}
                          disabled={isProcessing}
                          onClick={() => void restoreClient(client)}
                        >
                          Restore
                        </MenuItem>
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
                  ))}
              </div>
            )}
          </div>
        </div>
      )}

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
    </div>
  );
}
