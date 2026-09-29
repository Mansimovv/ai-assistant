export type ActivityEntry = {
  id: string;
  kind: "user" | "assistant" | "error";
  text: string;
  time: Date;
};

const LABELS: Record<ActivityEntry["kind"], string> = {
  user: "You",
  assistant: "Personal AI",
  error: "Error",
};

export function ActivityFeed({ entries }: { entries: ActivityEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-sm text-gray-500">No activity yet</p>;
  }

  return (
    <ul className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.id} className="text-sm">
          <span className={entry.kind === "error" ? "font-medium text-red-600" : "font-medium"}>
            {LABELS[entry.kind]}
          </span>
          <span className="ml-2 text-xs text-gray-400">{entry.time.toLocaleTimeString()}</span>
          <p className="whitespace-pre-wrap text-gray-700">{entry.text}</p>
        </li>
      ))}
    </ul>
  );
}
