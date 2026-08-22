import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "Nomercy AI",
  description:
    "Nomercy AI — a precise, cybersecurity-specialist AI assistant. Ask, research, and get grounded answers with citations.",
  applicationName: "Nomercy AI",
  openGraph: {
    title: "Nomercy AI",
    description: "A precise, cybersecurity-specialist AI assistant.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#0f1118",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
