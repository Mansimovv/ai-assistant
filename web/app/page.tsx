"use client";

import { useState } from "react";

import { ActivityFeed, type ActivityEntry } from "@/components/activity-feed";
import { ChatForm } from "@/components/chat-form";
import { DeviceList } from "@/components/device-list";

export default function Home() {
  const [activity, setActivity] = useState<ActivityEntry[]>([]);

  function addActivity(kind: ActivityEntry["kind"], text: string) {
    setActivity((entries) => [{ id: crypto.randomUUID(), kind, text, time: new Date() }, ...entries]);
  }

  return (
    <main className="mx-auto max-w-2xl space-y-10 p-6">
      <section className="space-y-4">
        <h1 className="border-b border-gray-200 pb-2 text-2xl font-semibold">Personal AI</h1>
        <ChatForm onActivity={addActivity} />
      </section>

      <section className="space-y-3">
        <h2 className="border-b border-gray-200 pb-2 text-lg font-semibold">Devices</h2>
        <DeviceList />
      </section>

      <section className="space-y-3">
        <h2 className="border-b border-gray-200 pb-2 text-lg font-semibold">Recent activity</h2>
        <ActivityFeed entries={activity} />
      </section>
    </main>
  );
}
