/** @type {import('next').NextConfig} */
const allowedDevOrigins = [
  'localhost',
  '127.0.0.1',
  '192.168.0.152',
  ...(process.env.NEXT_ALLOWED_DEV_ORIGINS || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
]

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  allowedDevOrigins,
  turbopack: {
    root: __dirname,
  },
}

module.exports = nextConfig
