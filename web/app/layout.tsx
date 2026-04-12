import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { CrisisBanner } from "@/components/CrisisBanner";
import { SiteNav } from "@/components/SiteNav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Resource finder",
  description:
    "Find food pantries, shelter, and housing resources in Michigan.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <a className="skip-to-main" href="#main-content">
          Skip to main content
        </a>
        <CrisisBanner />
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
