import "./globals.css";
import Providers from "./providers";
import Link from "next/link";

export const metadata = { title: "NeuroFlow" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <nav className="flex gap-6 border-b bg-white px-6 py-3 text-sm font-medium">
          <span className="font-bold">NeuroFlow</span>
          <Link href="/playground">Playground</Link>
          <Link href="/pipelines">Pipelines</Link>
          <Link href="/evaluations">Evaluations</Link>
          <Link href="/documents">Documents</Link>
        </nav>
        <Providers>
          <main className="p-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}