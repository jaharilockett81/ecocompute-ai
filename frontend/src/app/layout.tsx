import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "EcoCompute AI",
  description: "Quality-aware, evidence-driven inference routing across NVIDIA Nemotron models on Nebius Token Factory.",
};

// Apply the saved theme before paint to avoid a flash.
const THEME_SCRIPT = `try{var t=localStorage.getItem("ecocompute.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${inter.variable} ${geistMono.variable} antialiased`}>
        <Nav />
        <main className="px-4 pb-16 pt-6 md:ml-60 md:px-10 md:pt-8">
          <div className="mx-auto max-w-[1280px]">{children}</div>
        </main>
      </body>
    </html>
  );
}
