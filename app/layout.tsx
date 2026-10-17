import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "STMA Macro Signal Observatory",
  description: "Local, deterministic quant dashboard for STMA macro sentiment data.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="th"><body>{children}</body></html>;
}
