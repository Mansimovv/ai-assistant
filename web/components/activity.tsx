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

  if (entries.length === 0) return <p className="text-sm text-gray-500">Hələ fəaliyyət yoxdur</p>;

  return (
    <ul className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.id} className="text-xs">
          <span className={entry.ok ? "text-green-600" : "text-red-600"}>{entry.ok ? "✓" : "✗"}</span>{" "}
          <span className="font-medium text-gray-800">{entry.tool}</span>
          <span className="text-gray-400"> · {entry.duration_ms}ms</span>
          {entry.error && <p className="text-red-600">{entry.error}</p>}
        </li>
      ))}
    </ul>
  );
}
