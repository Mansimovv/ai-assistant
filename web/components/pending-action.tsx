"use client";

import type { PendingAction } from "@/lib/api";

type Props = {
  action: PendingAction;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function PendingActionCard({ action, busy, onConfirm, onCancel }: Props) {
  const command = typeof action.arguments.command === "string" ? action.arguments.command : null;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <p className="text-sm font-medium text-amber-900">Təsdiq lazımdır — riskli əməliyyat</p>
      <p className="mt-1 text-xs text-amber-800">{action.tool}</p>
      <pre className="mt-2 overflow-x-auto rounded bg-amber-100 p-2 text-xs text-amber-950">
        {command ?? JSON.stringify(action.arguments, null, 2)}
      </pre>
      <div className="mt-3 flex gap-2">
        <button
          onClick={onConfirm}
          disabled={busy}
          className="rounded bg-amber-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {busy ? "İcra olunur…" : "Təsdiq et"}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="rounded border border-amber-400 px-3 py-1.5 text-sm text-amber-900 disabled:opacity-50"
        >
          Ləğv et
        </button>
      </div>
    </div>
  );
}
