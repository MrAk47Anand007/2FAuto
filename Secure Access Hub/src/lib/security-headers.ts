const isProduction = process.env.NODE_ENV === "production";
const reportOnly =
  (process.env.CONTENT_SECURITY_POLICY_REPORT_ONLY ?? "false").toLowerCase() === "true";

export function buildContentSecurityPolicy(): string {
  const scriptSrc = isProduction
    ? "'self'"
    : "'self' 'unsafe-inline' 'unsafe-eval'";
  const connectSrc = isProduction
    ? "'self'"
    : "'self' ws: wss: http://localhost:* http://127.0.0.1:*";

  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

export function applySecurityHeaders(headers: Headers): void {
  const policy = buildContentSecurityPolicy();
  headers.set(
    reportOnly ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy",
    policy,
  );
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "same-origin");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()");
  if (isProduction) {
    headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  }
}

export function withSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  applySecurityHeaders(headers);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
