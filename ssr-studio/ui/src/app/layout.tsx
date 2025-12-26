import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SSR Studio",
  description: "Self-Play SWE-RL Demo & Research Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <nav className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between h-16">
                  <div className="flex items-center">
                    <a href="/" className="flex items-center space-x-2">
                      <span className="text-2xl font-bold text-primary-600">SSR</span>
                      <span className="text-xl text-gray-600 dark:text-gray-300">Studio</span>
                    </a>
                  </div>
                  <div className="flex items-center space-x-4">
                    <a
                      href="/environments"
                      className="text-gray-600 dark:text-gray-300 hover:text-primary-600 px-3 py-2"
                    >
                      Environments
                    </a>
                    <a
                      href="/episodes"
                      className="text-gray-600 dark:text-gray-300 hover:text-primary-600 px-3 py-2"
                    >
                      Episodes
                    </a>
                    <a
                      href="/metrics"
                      className="text-gray-600 dark:text-gray-300 hover:text-primary-600 px-3 py-2"
                    >
                      Metrics
                    </a>
                  </div>
                </div>
              </div>
            </nav>
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
