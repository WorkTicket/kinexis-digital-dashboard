"use client";

import { useMemo, useState, useCallback, DragEvent } from "react";
import { Insight, Task } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { motion } from "@/lib/motion";
import {
  CheckCircle2,
  Clock,
  FileText,
  Pencil,
  ArrowRight,
  SkipForward,
  Users,
  Trash2,
  AlertTriangle,
  Play,
} from "lucide-react";

type Filter = "active" | "open" | "in_progress" | "done" | "skipped" | "all";

type Props = {
  tasks: Task[];
  insightById: Map<number, Insight>;
  onUpdateTask: (taskId: number, updates: Partial<Task>) => Promise<void>;
  onDeleteTask?: (taskId: number) => Promise<void>;
  onGoToFixes: () => void;
  onGoToProve?: () => void;
  assigneePresets?: string[];
};

function statusBadgeTone(status: Task["status"]): "proof" | "momentum" | "default" | "danger" {
  if (status === "done") return "proof";
  if (status === "in_progress") return "momentum";
  if (status === "skipped") return "default";
  return "default";
}

export default function WorkBoard({
  tasks,
  insightById,
  onUpdateTask,
  onDeleteTask,
  onGoToFixes,
  onGoToProve,
  assigneePresets = ["Unassigned"],
}: Props) {
  const { success, error } = useToast();
  const [filter, setFilter] = useState<Filter>("active");
  const [assigneeFilter, setAssigneeFilter] = useState<string>(() => {
    try {
      return localStorage.getItem("kinexis-my-book-owner") || "all";
    } catch {
      return "all";
    }
  });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({
    assigned_to: "",
    due_date: "",
    result_notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [completeTarget, setCompleteTarget] = useState<Task | null>(null);
  const [completing, setCompleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [boardView, setBoardView] = useState<"list" | "board">("list");
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTargetCol, setDropTargetCol] = useState<string | null>(null);

  const todayIso = useMemo(() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }, []);

  const statusFiltered = useMemo(() => {
    switch (filter) {
      case "active":
        return tasks.filter((t) => t.status !== "done" && t.status !== "skipped");
      case "open":
        return tasks.filter((t) => t.status === "open");
      case "in_progress":
        return tasks.filter((t) => t.status === "in_progress");
      case "done":
        return tasks.filter((t) => t.status === "done");
      case "skipped":
        return tasks.filter((t) => t.status === "skipped");
      default:
        return tasks;
    }
  }, [tasks, filter]);

  const filtered = useMemo(() => {
    if (assigneeFilter === "all") return statusFiltered;
    if (assigneeFilter === "unassigned") {
      return statusFiltered.filter((t) => !(t.assigned_to || "").trim());
    }
    return statusFiltered.filter((t) => (t.assigned_to || "").trim() === assigneeFilter);
  }, [statusFiltered, assigneeFilter]);

  const counts = useMemo(
    () => ({
      active: tasks.filter((t) => t.status !== "done" && t.status !== "skipped").length,
      open: tasks.filter((t) => t.status === "open").length,
      in_progress: tasks.filter((t) => t.status === "in_progress").length,
      done: tasks.filter((t) => t.status === "done").length,
      skipped: tasks.filter((t) => t.status === "skipped").length,
      all: tasks.length,
    }),
    [tasks]
  );

  const assigneeChips = useMemo(() => {
    const names = new Set<string>();
    const selfNames = new Set(["self", "me", "myself"]);
    for (const t of tasks) {
      const name = (t.assigned_to || "").trim().toLowerCase();
      if (name && !selfNames.has(name)) names.add(t.assigned_to!.trim());
    }
    for (const p of assigneePresets) {
      const trimmed = p.trim();
      if (trimmed && !selfNames.has(trimmed.toLowerCase())) names.add(trimmed);
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [tasks, assigneePresets]);

  const boardColumns = useMemo(() => {
    const open: Task[] = [];
    const in_progress: Task[] = [];
    const done: Task[] = [];
    for (const t of filtered) {
      if (t.status === "open") open.push(t);
      else if (t.status === "in_progress") in_progress.push(t);
      else if (t.status === "done") done.push(t);
    }
    return { open, in_progress, done };
  }, [filtered]);

  const handleDragStart = useCallback((e: DragEvent, task: Task) => {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(task.id));
    setDraggingId(task.id);
  }, []);

  const handleDragOver = useCallback((e: DragEvent, col: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDropTargetCol(col);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDropTargetCol(null);
  }, []);

  const handleDrop = useCallback(
    async (e: DragEvent, targetStatus: Task["status"]) => {
      e.preventDefault();
      setDropTargetCol(null);
      setDraggingId(null);
      const taskId = Number(e.dataTransfer.getData("text/plain"));
      if (!taskId) return;
      const task = tasks.find((t) => t.id === taskId);
      if (!task || task.status === targetStatus) return;
      try {
        await onUpdateTask(taskId, { status: targetStatus });
        success("Work item moved");
      } catch {
        error("Failed to move work item");
      }
    },
    [tasks, onUpdateTask, success, error]
  );

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setDropTargetCol(null);
  }, []);

  const slaLabel = (
    task: Task
  ): { label: string; tone: "danger" | "warning" | "default" } | null => {
    if (task.status === "done" || task.status === "skipped") return null;
    if (task.due_date && task.due_date < todayIso) {
      return { label: "Overdue", tone: "danger" };
    }
    if (task.due_date && task.due_date === todayIso) {
      return { label: "Due today", tone: "warning" };
    }
    if (task.status === "in_progress") {
      return { label: "In flight", tone: "default" };
    }
    return null;
  };

  const startEdit = (task: Task) => {
    setEditingId(task.id);
    setEditForm({
      assigned_to: task.assigned_to || "",
      due_date: task.due_date || "",
      result_notes: task.result_notes || "",
    });
  };

  const saveEdit = async (taskId: number) => {
    setSaving(true);
    try {
      await onUpdateTask(taskId, {
        assigned_to: editForm.assigned_to || "Cursor",
        due_date: editForm.due_date || null,
        result_notes: editForm.result_notes || null,
      });
      success("Work item updated");
      setEditingId(null);
    } catch {
      error("Failed to update work item");
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async (task: Task) => {
    try {
      await onUpdateTask(task.id, { status: "skipped" });
      success("Task skipped");
    } catch {
      error("Failed to skip work item");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget || !onDeleteTask) return;
    setDeleting(true);
    try {
      await onDeleteTask(deleteTarget.id);
      success("Work item deleted");
      setDeleteTarget(null);
    } catch {
      error("Failed to delete work item");
    } finally {
      setDeleting(false);
    }
  };

  const handleStart = async (task: Task) => {
    try {
      await onUpdateTask(task.id, { status: "in_progress" });
      success("Work started");
    } catch {
      error("Failed to start work item");
    }
  };

  const handleComplete = async () => {
    if (!completeTarget) return;
    const previous = { ...completeTarget };
    setCompleting(true);
    try {
      await onUpdateTask(completeTarget.id, { status: "done" });
      success("Work marked complete \u2014 impact snapshot saved for Prove", {
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await onUpdateTask(previous.id, { status: previous.status });
              success("Work reopened");
            } catch {
              error("Failed to undo");
            }
          },
        },
      });
      setCompleteTarget(null);
      onGoToProve?.();
    } catch {
      error("Failed to complete work item");
    } finally {
      setCompleting(false);
    }
  };

  const overdueCount = useMemo(
    () =>
      filtered.filter(
        (t) => t.due_date && t.due_date < todayIso && t.status !== "done" && t.status !== "skipped"
      ).length,
    [filtered, todayIso]
  );

  const filters: { id: Filter; label: string }[] = [
    { id: "active", label: "Active" },
    { id: "open", label: "Open" },
    { id: "in_progress", label: "In progress" },
    { id: "done", label: "Done" },
    { id: "skipped", label: "Skipped" },
    { id: "all", label: "All" },
  ];

  const renderTaskCard = (task: Task, idx: number) => {
    const linked = task.insight_id ? insightById.get(task.insight_id) : null;
    const isEditing = editingId === task.id;
    const stateMotion =
      task.status === "done" || task.status === "skipped" ? motion.resolve : motion.settle;
    const sla = slaLabel(task);

    return (
      <Panel
        key={`${task.id}-${task.status}`}
        className={`hover:border-[color:var(--border-strong)] ${motion.micro} ${motion.loadIn} ${motion.staggerClass(idx % 4)} ${stateMotion}`}
        padding={false}
      >
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
          <div className="mt-0.5 shrink-0">
            {task.status === "done" ? (
              <CheckCircle2 size={16} strokeWidth={1.75} className="text-kinexis-proof" />
            ) : task.status === "in_progress" ? (
              <Clock size={16} strokeWidth={1.75} className="text-kinexis-momentum" />
            ) : task.status === "skipped" ? (
              <SkipForward size={16} strokeWidth={1.75} className="text-muted" />
            ) : (
              <FileText size={16} strokeWidth={1.75} className="text-muted" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <Badge tone={statusBadgeTone(task.status)}>{task.status.replace("_", " ")}</Badge>
              {sla && <Badge tone={sla.tone}>{sla.label}</Badge>}
              {!isEditing && task.assigned_to && (
                <span className="text-muted text-xs">{task.assigned_to}</span>
              )}
              {!isEditing && task.due_date && (
                <span
                  className={`font-mono-data text-xs ${
                    task.due_date < todayIso ? "text-kinexis-risk" : "text-muted"
                  }`}
                >
                  Due {task.due_date}
                </span>
              )}
              {!isEditing && task.brief_id != null && <Badge tone="brand">brief</Badge>}
            </div>

            {isEditing ? (
              <div className="mt-2 space-y-2.5">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {assigneePresets.length > 0 ? (
                    <Select
                      value={
                        assigneePresets.includes(editForm.assigned_to)
                          ? editForm.assigned_to
                          : editForm.assigned_to
                            ? "__custom__"
                            : assigneePresets[0]
                      }
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "__custom__") return;
                        setEditForm((f) => ({ ...f, assigned_to: v }));
                      }}
                      className="py-2"
                    >
                      {assigneePresets.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                      {editForm.assigned_to && !assigneePresets.includes(editForm.assigned_to) && (
                        <option value="__custom__">{editForm.assigned_to}</option>
                      )}
                    </Select>
                  ) : (
                    <Input
                      type="text"
                      value={editForm.assigned_to}
                      onChange={(e) => setEditForm((f) => ({ ...f, assigned_to: e.target.value }))}
                      placeholder="Assigned to"
                      className="py-2"
                    />
                  )}
                  <Input
                    type="date"
                    value={editForm.due_date}
                    onChange={(e) => setEditForm((f) => ({ ...f, due_date: e.target.value }))}
                    className="py-2 [color-scheme:dark]"
                  />
                </div>
                <Textarea
                  value={editForm.result_notes}
                  onChange={(e) => setEditForm((f) => ({ ...f, result_notes: e.target.value }))}
                  placeholder="Notes"
                  rows={3}
                  className="min-h-[72px]"
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => void saveEdit(task.id)} disabled={saving}>
                    {saving ? "Saving\u2026" : "Save"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingId(null)}
                    disabled={saving}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                {linked ? (
                  <>
                    <p className="mb-1 whitespace-pre-wrap text-[13px] font-medium leading-relaxed text-ink">
                      {(linked.recommended_action || linked.message || "").split("\n")[0]}
                    </p>
                    {linked.recommended_action && linked.recommended_action.includes("\n") && (
                      <p className="mb-1 line-clamp-6 whitespace-pre-wrap text-xs leading-relaxed text-ink-secondary">
                        {linked.recommended_action}
                      </p>
                    )}
                    <p className="text-muted line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed">
                      {linked.message}
                    </p>
                  </>
                ) : task.result_notes ? (
                  <div className="space-y-1.5">
                    {task.result_notes.split(/\n\n+/).map((block, i) => (
                      <p
                        key={i}
                        className={`whitespace-pre-wrap text-[13px] leading-relaxed ${
                          i === 0 ? "font-medium text-ink" : "text-ink-secondary"
                        }`}
                      >
                        {block}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-[13px] font-medium text-ink">
                    {task.playbook_pattern
                      ? task.playbook_pattern.replace(/_/g, " ")
                      : task.target_url
                        ? `Fix: ${task.target_url}`
                        : task.target_query
                          ? `Fix: ${task.target_query}`
                          : `Work item #${task.id}`}
                  </p>
                )}
                {task.result_notes && linked && (
                  <p className="text-muted mt-1.5 line-clamp-4 whitespace-pre-wrap text-xs">
                    Notes: {task.result_notes}
                  </p>
                )}
              </>
            )}
          </div>

          {!isEditing && (
            <div className="flex shrink-0 items-center gap-1 sm:self-start">
              <IconButton label="Edit work item" size="sm" onClick={() => startEdit(task)}>
                <Pencil size={14} />
              </IconButton>
              {task.status === "open" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="!text-kinexis-momentum hover:!bg-kinexis-momentum/10"
                  onClick={() => void handleStart(task)}
                >
                  <Play size={12} /> Start
                </Button>
              )}
              {task.status === "in_progress" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="!text-kinexis-focus hover:!bg-kinexis-focus/10"
                  onClick={() => setCompleteTarget(task)}
                >
                  Complete
                </Button>
              )}
              {task.status !== "done" && task.status !== "skipped" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="!text-muted hover:!bg-kinexis-risk/10"
                  onClick={() => void handleSkip(task)}
                >
                  Skip
                </Button>
              )}
              {onDeleteTask && (
                <IconButton
                  label="Delete work item"
                  size="sm"
                  className="hover:!bg-kinexis-risk/10 hover:!text-kinexis-risk"
                  onClick={() => setDeleteTarget(task)}
                >
                  <Trash2 size={14} />
                </IconButton>
              )}
            </div>
          )}
        </div>
      </Panel>
    );
  };

  return (
    <div className="animate-fade-up space-y-3">
      {tasks.length > 0 && (
        <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="panel flex items-center gap-2.5 !p-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-kinexis-focus/10">
              <Clock size={14} className="text-kinexis-focus" />
            </div>
            <div>
              <p className="text-muted text-[11px] font-medium">Active</p>
              <p className="font-mono-data text-[15px] font-semibold text-ink">{counts.active}</p>
            </div>
          </div>
          <div className="panel flex items-center gap-2.5 !p-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-kinexis-proof/10">
              <CheckCircle2 size={14} className="text-kinexis-proof" />
            </div>
            <div>
              <p className="text-muted text-[11px] font-medium">Done</p>
              <p className="font-mono-data text-[15px] font-semibold text-ink">{counts.done}</p>
            </div>
          </div>
          <div className="panel flex items-center gap-2.5 !p-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-kinexis-signal/10">
              <SkipForward size={14} className="text-kinexis-signal" />
            </div>
            <div>
              <p className="text-muted text-[11px] font-medium">Skipped</p>
              <p className="font-mono-data text-[15px] font-semibold text-ink">{counts.skipped}</p>
            </div>
          </div>
          <div className="panel flex items-center gap-2.5 !p-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-lighter">
              <Users size={14} className="text-muted" />
            </div>
            <div>
              <p className="text-muted text-[11px] font-medium">Assignees</p>
              <p className="font-mono-data text-[15px] font-semibold text-ink">
                {assigneeChips.length}
              </p>
            </div>
          </div>
        </div>
      )}

      {overdueCount > 0 && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-kinexis-risk/20 bg-kinexis-risk/5 px-3 py-2 text-xs text-kinexis-risk">
          <AlertTriangle size={12} />
          {overdueCount} overdue item{overdueCount === 1 ? "" : "s"} — prioritize these first
        </div>
      )}

      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setAssigneeFilter("all")}
            className={`chip ${assigneeFilter === "all" ? "chip-active" : ""}`}
          >
            All assignees
          </button>
          <button
            type="button"
            onClick={() => setAssigneeFilter("unassigned")}
            className={`chip ${assigneeFilter === "unassigned" ? "chip-active" : ""}`}
          >
            Unassigned
          </button>
          {assigneeChips.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setAssigneeFilter(name)}
              className={`chip ${assigneeFilter === name ? "chip-active" : ""}`}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setBoardView((v) => (v === "list" ? "board" : "list"))}
            className="text-muted rounded-md px-2 py-1 text-[11px] font-medium hover:text-ink-secondary"
          >
            {boardView === "list" ? "Board view" : "List view"}
          </button>
          <SegmentedControl
            size="sm"
            ariaLabel="Work filters"
            value={filter}
            onChange={setFilter}
            options={filters.map((f) => ({
              id: f.id,
              label: f.label,
              count: counts[f.id],
            }))}
          />
        </div>
      </div>

      {tasks.length === 0 && (
        <EmptyState
          title="No work items yet"
          description="Go to Prescribe \u2192 Fix queue, open a fix, and click Assign."
          action={
            <Button variant="soft" onClick={onGoToFixes}>
              Go to Fix queue <ArrowRight size={12} />
            </Button>
          }
        />
      )}

      {tasks.length > 0 && filtered.length === 0 && (
        <EmptyState className="!py-8" title="No items in this filter" />
      )}

      {boardView === "board" && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {(["open", "in_progress", "done"] as const).map((col) => (
            <div
              key={col}
              className="space-y-2"
              onDragOver={(e) => handleDragOver(e as unknown as DragEvent, col)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e as unknown as DragEvent, col)}
            >
              <div className="flex items-center gap-2 px-1">
                <span className="text-label text-muted">
                  {col === "open" ? "To do" : col === "in_progress" ? "In progress" : "Done"}
                </span>
                <span className="text-muted font-mono-data text-[11px]">
                  {boardColumns[col].length}
                </span>
              </div>
              <div
                className={`min-h-[80px] rounded-lg border-2 ${
                  dropTargetCol === col
                    ? "border-dashed border-kinexis-focus/50 bg-kinexis-focus/[0.04]"
                    : "border-dashed border-transparent"
                }`}
              >
                {boardColumns[col].map((task, idx) => (
                  <div
                    key={`${task.id}-${task.status}`}
                    draggable
                    onDragStart={(e) => handleDragStart(e as unknown as DragEvent, task)}
                    onDragEnd={handleDragEnd}
                    className={draggingId === task.id ? "opacity-40" : ""}
                  >
                    {renderTaskCard(task, idx)}
                  </div>
                ))}
                {boardColumns[col].length === 0 && (
                  <Panel padding="md" className="!border-dashed">
                    <p className="text-muted text-center text-xs">Drop tasks here</p>
                  </Panel>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {boardView === "list" && filtered.map((task, idx) => renderTaskCard(task, idx))}

      <ConfirmDialog
        open={!!completeTarget}
        title="Mark work complete?"
        description="This captures a baseline for impact measurement. You can recheck results later in Prove."
        confirmLabel="Complete"
        busy={completing}
        onConfirm={handleComplete}
        onCancel={() => !completing && setCompleteTarget(null)}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete work item"
        description={
          deleteTarget
            ? `Permanently remove "${deleteTarget.playbook_pattern?.replace(/_/g, " ") || deleteTarget.target_url || deleteTarget.target_query || `work item #${deleteTarget.id}`}"? This cannot be undone.`
            : ""
        }
        confirmLabel={deleting ? "Deleting\u2026" : "Delete"}
        danger
        busy={deleting}
        onConfirm={handleDelete}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
      {onGoToProve && tasks.some((t) => t.status === "done") && (
        <Panel padding="md">
          <p className="text-[13px] font-medium text-ink">Waiting for Prove</p>
          <p className="text-muted mt-1 text-xs">
            Completed work is ready for impact recheck \u2014 measure lift before the next report.
          </p>
          <Button variant="soft" size="sm" className="mt-3" onClick={onGoToProve}>
            Open Prove <ArrowRight size={12} />
          </Button>
        </Panel>
      )}
    </div>
  );
}
