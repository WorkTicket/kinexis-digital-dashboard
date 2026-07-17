"use client";

import { Insight } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { X } from "lucide-react";

type Props = {
  insight: Insight;
  assigneePresets: string[];
  taskForm: { assigned_to: string; due_date: string };
  setTaskForm: React.Dispatch<React.SetStateAction<{ assigned_to: string; due_date: string }>>;
  creating: boolean;
  onClose: () => void;
  onCreate: () => void;
};

/** Task creation modal extracted from the app shell. */
export default function TaskCreateModal({
  insight,
  assigneePresets,
  taskForm,
  setTaskForm,
  creating,
  onClose,
  onCreate,
}: Props) {
  return (
    <div
      className="modal-backdrop animate-fade-in z-[70]"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Create work item"
        className="panel-elevated animate-scale-in w-full max-w-md p-4 shadow-panel-lg"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Create work item</p>
            <p className="text-muted mt-1 line-clamp-2 text-xs">
              {insight.recommended_action || insight.message}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted rounded-md p-1 hover:text-ink"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="space-y-3">
          <Select
            label="Assignee"
            value={
              assigneePresets.includes(taskForm.assigned_to) ? taskForm.assigned_to : "__custom__"
            }
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__custom__") {
                setTaskForm((f) => ({ ...f, assigned_to: "" }));
              } else {
                setTaskForm((f) => ({ ...f, assigned_to: v }));
              }
            }}
          >
            {assigneePresets.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
            <option value="__custom__">Custom…</option>
          </Select>
          {!assigneePresets.includes(taskForm.assigned_to) && (
            <Input
              label="Custom assignee"
              value={taskForm.assigned_to}
              onChange={(e) => setTaskForm((f) => ({ ...f, assigned_to: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === "Enter") onCreate();
              }}
              placeholder="Name"
              autoFocus
            />
          )}
          <Input
            label="Due date"
            type="date"
            value={taskForm.due_date}
            onChange={(e) => setTaskForm((f) => ({ ...f, due_date: e.target.value }))}
            className="[color-scheme:dark]"
          />
          <Button type="button" onClick={onCreate} disabled={creating} className="mt-1 w-full">
            {creating ? "Creating…" : "Create work item"}
          </Button>
        </div>
      </div>
    </div>
  );
}
