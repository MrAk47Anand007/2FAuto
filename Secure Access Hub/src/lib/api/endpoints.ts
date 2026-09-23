/**
 * Endpoint adapters. EXISTING = verified backend routes. ADDED = routes this
 * frontend requires the backend to implement (see docs/API-CONTRACT.md).
 */
import { apiRequest } from "./client";
import type {
  AdminPortal,
  AdminTeam,
  AdminUser,
  AuditEvent,
  AutomationClient,
  ClientCredential,
  LoginResponse,
  MeResponse,
  OtpResponse,
  PortalSummary,
  SessionRecord,
  StepUpResponse,
} from "./types";

/* ---------------------------------- auth --------------------------------- */

/** ADDED */
export const getMe = () => apiRequest<MeResponse>("/api/v1/me", { ignoreUnauthorized: true });

/** ADDED (JSON adapter over the existing POST /login) */
export const login = (username: string, password: string) =>
  apiRequest<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    json: { username, password },
    ignoreUnauthorized: true,
  });

/** ADDED (JSON adapter over the existing POST /logout) */
export const logout = () => apiRequest<{ ok?: boolean }>("/api/v1/auth/logout", { method: "POST" });

/** EXISTING */
export const stepUp = (password: string) =>
  apiRequest<StepUpResponse>("/api/v1/me/step-up", { method: "POST", form: { password } });

/* -------------------------------- sessions -------------------------------- */

/** EXISTING */
export const listSessions = () => apiRequest<{ sessions: SessionRecord[] }>("/api/v1/me/sessions");

/** EXISTING */
export const revokeSession = (sessionId: string) =>
  apiRequest<unknown>(`/api/v1/me/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });

/* --------------------------------- portals -------------------------------- */

/** EXISTING */
export const listMyPortals = () => apiRequest<{ portals: PortalSummary[] }>("/api/ui/portals");

/** EXISTING — only ever called from an explicit Reveal action. */
export const revealOtp = (portalName: string, signal?: AbortSignal) =>
  apiRequest<OtpResponse>(`/api/ui/portals/${encodeURIComponent(portalName)}/otp`, {
    method: "POST",
    ...(signal ? { signal } : {}),
  });

/* ----------------------------- admin: portals ----------------------------- */

/** ADDED */
export const adminListPortals = () =>
  apiRequest<{ portals: AdminPortal[] }>("/admin/api/v1/admin/portals");

/** EXISTING form endpoints */
export const adminCreatePortal = (input: {
  portal_name: string;
  display_name: string;
  secret: string;
  period: number;
}) => apiRequest<unknown>("/admin/portals", { method: "POST", form: input });

export const adminEditPortal = (
  portalName: string,
  input: { display_name: string; period: number },
) =>
  apiRequest<unknown>(`/admin/portals/${encodeURIComponent(portalName)}/edit`, {
    method: "POST",
    form: input,
  });

export const adminPortalAction = (
  portalName: string,
  action: "disable" | "reactivate" | "delete",
) =>
  apiRequest<unknown>(`/admin/portals/${encodeURIComponent(portalName)}/${action}`, {
    method: "POST",
  });

export const adminGrantPortal = (
  portalName: string,
  input: { username: string; expires_in_days: number },
) =>
  apiRequest<unknown>(`/admin/portals/${encodeURIComponent(portalName)}/grants`, {
    method: "POST",
    form: input,
  });

export const adminRevokePortalGrant = (portalName: string, username: string) =>
  apiRequest<unknown>(
    `/admin/portals/${encodeURIComponent(portalName)}/grants/${encodeURIComponent(username)}/revoke`,
    { method: "POST" },
  );

/* ------------------------------ admin: people ----------------------------- */

/** ADDED */
export const adminListUsers = () => apiRequest<{ users: AdminUser[] }>("/admin/api/v1/admin/users");

/** EXISTING form endpoints */
export const adminCreateUser = (input: {
  username: string;
  password: string;
  role: "admin" | "user";
}) => apiRequest<unknown>("/admin/users", { method: "POST", form: input });

export const adminUserAction = (username: string, action: "disable" | "reactivate") =>
  apiRequest<unknown>(`/admin/users/${encodeURIComponent(username)}/${action}`, { method: "POST" });

/* ------------------------------ admin: teams ------------------------------ */

/** ADDED */
export const adminListTeams = () => apiRequest<{ teams: AdminTeam[] }>("/admin/api/v1/admin/teams");

/** EXISTING form endpoints */
export const adminCreateTeam = (name: string) =>
  apiRequest<unknown>("/admin/teams", { method: "POST", form: { name } });

export const adminAddTeamMember = (teamName: string, username: string) =>
  apiRequest<unknown>(`/admin/teams/${encodeURIComponent(teamName)}/members`, {
    method: "POST",
    form: { username },
  });

export const adminRemoveTeamMember = (teamName: string, username: string) =>
  apiRequest<unknown>(`/admin/teams/${encodeURIComponent(teamName)}/members/remove`, {
    method: "POST",
    form: { username },
  });

export const adminGrantTeamPortal = (
  teamName: string,
  portalName: string,
  expires_in_days: number,
) =>
  apiRequest<unknown>(
    `/admin/teams/${encodeURIComponent(teamName)}/grants/${encodeURIComponent(portalName)}`,
    { method: "POST", form: { expires_in_days } },
  );

export const adminRevokeTeamGrant = (teamName: string, portalName: string) =>
  apiRequest<unknown>(
    `/admin/teams/${encodeURIComponent(teamName)}/grants/${encodeURIComponent(portalName)}/revoke`,
    { method: "POST" },
  );

/* ---------------------------- automation clients --------------------------- */

/** EXISTING */
export const listClients = () => apiRequest<{ clients: AutomationClient[] }>("/api/v1/clients");

export const createClient = (input: {
  name: string;
  environment: string;
  expires_in_days: number;
}) =>
  apiRequest<{ client_id: number; name: string }>("/api/v1/clients", {
    method: "POST",
    json: input,
  });

export const listClientCredentials = (clientId: number) =>
  apiRequest<{ client_id: number; credentials: ClientCredential[] }>(
    `/api/v1/clients/${clientId}/credentials`,
  );

export const issueClientCredential = (clientId: number, expires_in_days: number) =>
  apiRequest<{ client_id: number; credential: string; warning?: string }>(
    `/api/v1/clients/${clientId}/credentials`,
    { method: "POST", json: { expires_in_days } },
  );

export const revokeClientCredential = (clientId: number, credentialId: number) =>
  apiRequest<unknown>(`/api/v1/clients/${clientId}/credentials/${credentialId}/revoke`, {
    method: "POST",
  });

export const grantClientPortal = (clientId: number, portalName: string, expires_in_days: number) =>
  apiRequest<unknown>(`/api/v1/clients/${clientId}/grants/${encodeURIComponent(portalName)}`, {
    method: "POST",
    json: { expires_in_days },
  });

export const revokeClient = (clientId: number) =>
  apiRequest<unknown>(`/api/v1/clients/${clientId}/revoke`, { method: "POST" });

/* ---------------------------------- audit --------------------------------- */

/** EXISTING — recent-event feed, limit bounded 1..500 */
export const listAuditEvents = (limit = 100) =>
  apiRequest<{ events: AuditEvent[] }>(
    `/admin/api/v1/audit?limit=${Math.min(Math.max(limit, 1), 500)}`,
  );
