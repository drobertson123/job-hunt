/**
 * Dev and prod configs are mutually exclusive on purpose:
 *  - dev:  `next dev` proxies /api -> FastAPI on :8000 (rewrites). No export.
 *  - prod: static export to `out/`, which FastAPI serves on a single origin.
 *          (rewrites do NOT apply to a static export, so we never set both.)
 */
const isDev = process.env.NODE_ENV === "development";

/** @type {import('next').NextConfig} */
const devConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

/** @type {import('next').NextConfig} */
const prodConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default isDev ? devConfig : prodConfig;
