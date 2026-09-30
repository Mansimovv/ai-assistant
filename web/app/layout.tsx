import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Assistant",
  description: "Personal assistant dashboard",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">{children}</body>
    </html>
  );
}
