import type { Metadata } from "next";
import { Geist_Mono, Outfit } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const outfit = Outfit({ variable: "--font-outfit", subsets: ["latin"], weight: ["200", "300", "400", "500", "600"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "EcoCompute AI",
  description: "Quality-aware, evidence-driven inference routing across NVIDIA Nemotron models on Nebius Token Factory.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${outfit.variable} ${geistMono.variable} antialiased`}>
        <Nav />
        <main className="mx-auto max-w-7xl px-4 pb-16 pt-8 md:px-8">{children}</main>
        <footer className="mx-auto max-w-7xl border-t border-border px-4 py-8 text-xs text-muted md:px-8">
          EcoCompute AI · NVIDIA Nemotron on Nebius Token Factory · MIT licensed
        </footer>
      </body>
    </html>
  );
}
