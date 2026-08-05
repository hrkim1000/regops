/** @type {import('next').NextConfig} */

// The browser never talks to a service directly. `/api/<svc>/*` rewrites to that service's
// `/api/v1/*`, so a client island uses one origin and the JWT cookie stays first-party.
const services = {
  'platform-core': process.env.PLATFORM_CORE_URL ?? 'http://platform-core:8000',
  regulation: process.env.REGULATION_URL ?? 'http://regulation:8000',
  monitoring: process.env.MONITORING_URL ?? 'http://monitoring:8000',
  assistant: process.env.ASSISTANT_URL ?? 'http://assistant:8000',
};

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    return Object.entries(services).map(([name, origin]) => ({
      source: `/api/${name}/:path*`,
      destination: `${origin}/api/v1/:path*`,
    }));
  },
};

export default nextConfig;
