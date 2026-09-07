/** @type {import('next').NextConfig} */

// Static export for a Hugging Face Static Space, which serves files and runs no
// server. Route handlers cannot exist here, so lib/api.ts runs the demo entirely
// in the browser instead.
const nextConfig = {
  output: "export",
  // No image optimiser without a server.
  images: { unoptimized: true },
  // HF serves the Space from a subpath on hf.space? No -- Spaces get their own
  // origin, so no basePath is needed. Trailing slashes keep static hosts happy
  // with directory-style URLs.
  trailingSlash: true,
};

module.exports = nextConfig;
