import type { Metadata } from 'next'
import { Providers } from '@/components/providers'
import './globals.css'

export const metadata: Metadata = {
  title: 'AutoDS Agent',
  description: 'Autonomous Data Science Agent Interface',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen overflow-hidden">
        <Providers>
          <div className="flex h-screen">
            {children}
          </div>
        </Providers>
      </body>
    </html>
  )
}
