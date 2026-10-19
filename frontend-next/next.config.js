/** @type {import('next').NextConfig} */
const nextConfig = {
  // Vercel's Next.js adapter owns the hosted output; other hosts use out/.
  ...(process.env.VERCEL === "1" ? {} : { output: "export" }),
  trailingSlash: true,
  images: { unoptimized: true },
};

module.exports = nextConfig;
