/** @type {import("next").NextConfig} */
const nextConfig = {
  experimental: {
    // A Word-export a terkepeket PNG-be rendereli (resvg, nativ modul) —
    // ne csomagolja a webpack, a fontokat pedig vigye a serverless fuggvennyel.
    serverComponentsExternalPackages: ["@resvg/resvg-js"],
    outputFileTracingIncludes: {
      "/api/command-brief/[week]/docx": ["./assets/fonts/**"],
      "/api/command-brief/template": ["./assets/fonts/**"],
    },
  },
};
export default nextConfig;
