"use client";

import { useEffect, useState } from "react";

import { getActivity, type ActivityEntry } from "@/lib/api";

export function Activity({ reloadKey }: { reloadKey: number }) {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);

  useEffect(() => {
    getActivity()
      .then(setEntries)
      .catch(() => undefined);
  }, [reloadKey]);

  if (entries.length === 0) return <p className="text-sm text-white/40">Hələ fəaliyyət yoxdur</p>;

  return (
    <ul className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.id} className="text-xs">
          <span className={entry.ok ? "text-emerald-400" : "text-rose-400"}>{entry.ok ? "✓" : "✗"}</span>{" "}
          <span className="font-medium text-white/85">{entry.tool}</span>
          <span className="text-white/40"> · {entry.duration_ms}ms</span>
          {entry.error && <p className="text-rose-400">{entry.error}</p>}
        </li>
      ))}
    </ul>
  );
}
