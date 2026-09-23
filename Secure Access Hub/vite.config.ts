// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { IncomingMessage, ServerResponse } from "node:http";

/**
 * Backend origin for local development. The dev server forwards the FastAPI
 * paths so the browser only ever talks to one origin — same-origin cookies,
 * same-origin CSRF, no CORS and no wildcard origins.
 */
const BACKEND = process.env["VITE_BACKEND_ORIGIN"] ?? "http://localhost:8000";

/**
 * Only backend-owned prefixes are forwarded. `/login` and `/logout` stay with
 * the SPA: the React app authenticates through `/api/v1/auth/login|logout`.
 */
const PROXIED_PREFIXES = ["/api/", "/admin/", "/admin", "/health", "/ready"];

function shouldProxy(url: string): boolean {
  return PROXIED_PREFIXES.some((prefix) => url === prefix || url.startsWith(prefix));
}

/**
 * Dev-only backend bridge. Implemented as connect middleware (instead of
 * `server.proxy`) so it survives environments that strip proxy config.
 *
 * The proxy rewrites Origin to the backend origin. The browser can therefore
 * keep one Vite origin for its HttpOnly cookie while FastAPI receives a
 * same-origin request and continues enforcing its strict origin check.
 */
function backendBridge() {
  return {
    name: "twofauto-backend-bridge",
    apply: "serve" as const,
    configureServer(server: {
      middlewares: {
        use: (fn: (req: IncomingMessage, res: ServerResponse, next: () => void) => void) => void;
      };
    }) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        if (!shouldProxy(url)) {
          next();
          return;
        }

        void (async () => {
          const chunks: Buffer[] = [];
          for await (const chunk of req) chunks.push(chunk as Buffer);

          const headers = new Headers();
          for (const [key, value] of Object.entries(req.headers)) {
            if (value === undefined) continue;
            if (["host", "connection", "content-length"].includes(key)) continue;
            headers.set(key, Array.isArray(value) ? value.join(", ") : value);
          }
          headers.set("origin", new URL(BACKEND).origin);

          try {
            const upstream = await fetch(new URL(url, BACKEND), {
              method: req.method ?? "GET",
              headers,
              ...(chunks.length ? { body: Buffer.concat(chunks) } : {}),
              redirect: "manual",
            });

            res.statusCode = upstream.status;
            upstream.headers.forEach((value, key) => {
              if (key === "content-encoding" || key === "content-length") return;
              if (key === "set-cookie") return;
              res.setHeader(key, value);
            });
            const setCookie = upstream.headers.getSetCookie?.() ?? [];
            if (setCookie.length) res.setHeader("set-cookie", setCookie);
            res.setHeader("Referrer-Policy", "same-origin");
            res.end(Buffer.from(await upstream.arrayBuffer()));
          } catch {
            // 503, not 502: a 502 from the dev server is interpreted as a Vite
            // build failure. This is a reachability problem, not a build error.
            res.statusCode = 503;
            res.setHeader("content-type", "application/json");
            res.setHeader("cache-control", "no-store");
            res.end(
              JSON.stringify({
                detail: `The 2FAuto backend is not reachable at ${BACKEND}. Start FastAPI (or set VITE_BACKEND_ORIGIN) and retry.`,
              }),
            );
          }
        })();
      });
    },
  };
}

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    plugins: [backendBridge()],
  },
});
