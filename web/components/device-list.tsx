"use client";

import { useEffect, useState } from "react";

import { getDevices, type Device } from "@/lib/api";

const REFRESH_MS = 10_000;

export function DeviceList() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      getDevices()
        .then((list) => {
          setDevices(list);
          setError(null);
        })
        .catch((err: Error) => setError(err.message));

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (devices === null) return <p className="text-sm text-gray-500">Yüklənir…</p>;
  if (devices.length === 0) {
    return <p className="text-sm text-gray-500">Hələ cihaz yoxdur. Agent qoşulanda burada görünəcək.</p>;
  }

  return (
    <ul className="space-y-3">
      {devices.map((device) => (
        <li key={device.id}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{device.name}</span>
            <span className={device.status === "online" ? "text-xs text-green-600" : "text-xs text-gray-400"}>
              {device.status === "online" ? "● online" : "○ offline"}
            </span>
          </div>
          <p className="text-xs text-gray-500">
            {device.type}
            {device.capabilities.length > 0 && ` · ${device.capabilities.length} bacarıq`}
          </p>
        </li>
      ))}
    </ul>
  );
}
