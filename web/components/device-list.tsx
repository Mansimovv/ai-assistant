"use client";

import { useEffect, useState } from "react";

import { getDevices, type Device } from "@/lib/api";

export function DeviceList() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDevices()
      .then(setDevices)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (devices === null) return <p className="text-sm text-gray-500">Loading…</p>;
  if (devices.length === 0) {
    return <p className="text-sm text-gray-500">No devices yet. A device appears here once its agent connects.</p>;
  }

  return (
    <ul className="space-y-1">
      {devices.map((device) => (
        <li key={device.id} className="flex justify-between text-sm">
          <span>{device.name}</span>
          <span className={device.status === "online" ? "text-green-600" : "text-gray-500"}>
            {device.status === "online" ? "Online" : "Offline"}
          </span>
        </li>
      ))}
    </ul>
  );
}
