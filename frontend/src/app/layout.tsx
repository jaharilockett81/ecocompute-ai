import type { Metadata } from "next";
import { Geist_Mono, Inter, Newsreader } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin"], style: ["normal", "italic"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "EcoCompute AI",
  description: "Find wasted inference compute, keep the quality. An evidence-driven optimization agent on NVIDIA Nemotron via Nebius Token Factory.",
};

// Apply the saved theme before paint to avoid a flash.
const THEME_SCRIPT = `try{var t=localStorage.getItem("ecocompute.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${inter.variable} ${newsreader.variable} ${geistMono.variable} antialiased`}>
        <Nav />
        <main className="px-4 pb-16 pt-6 md:ml-64 md:px-12 md:pt-10">
          <div className="mx-auto max-w-[1280px]">{children}</div>
        </main>
      </body>
    </html>
  );
}
