import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jarvis",
  description: "Personal voice assistant",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="az">
      <body className="bg-[#05070b] text-white antialiased">{children}</body>
    </html>
  );
}
