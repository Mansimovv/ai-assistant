"use client";

import { useEffect, useState } from "react";

import { Activity } from "@/components/activity";
import { Chat } from "@/components/chat";
import { DeviceList } from "@/components/device-list";
import { getInfo } from "@/lib/api";

export default function Home() {
  // The name comes from the backend, so renaming the assistant is one setting.
  const [name, setName] = useState("Assistant");
  const [activityKey, setActivityKey] = useState(0);

  useEffect(() => {
    getInfo()
      .then((info) => setName(info.name))
      .catch(() => undefined);
  }, []);

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-6 border-b border-gray-200 pb-3 text-2xl font-semibold">{name}</h1>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <Chat onActed={() => setActivityKey((key) => key + 1)} />

        <aside className="space-y-8">
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Cihazlar</h2>
            <DeviceList />
          </section>
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Son fəaliyyət</h2>
            <Activity reloadKey={activityKey} />
          </section>
        </aside>
      </div>
    </main>
  );
}
