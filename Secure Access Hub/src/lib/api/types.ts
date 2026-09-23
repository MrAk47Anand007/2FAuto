/**
 * Typed contracts for the 2FAuto FastAPI backend.
 *
 * Each block is marked EXISTING (verified against the provided contract) or
 * ADDED (must be implemented on the backend — see docs/API-CONTRACT.md).
 */

export type Role = "admin" | "user";

/* ADDED: GET /api/v1/me */
export interface MeResponse {
  id: number;
  username: string;
  role: Role;
  csrf_token: string;
  session_expires_at?: number | null;
  step_up_expires_at?: number | null;
}

/* ADDED: POST /api/v1/auth/login */
export interface LoginResponse {
  id: number;
  username: string;
  role: Role;
  csrf_token: string;
}

/* EXISTING: POST /api/v1/me/step-up */
export interface StepUpResponse {
  step_up: boolean;
  valid_for_seconds: number;
}

/* EXISTING: GET /api/v1/me/sessions */
export interface SessionRecord {
  id: string;
  created_at: string | number;
  last_active_at: string | number | null;
  expires_at: string | number | null;
  revoked_at: string | number | null;
  current: boolean;
}

/* EXISTING: GET /api/ui/portals */
export interface PortalSummary {
  portal_name: string;
  display_name: string;
  period: number;
}

/* EXISTING: POST /api/ui/portals/{portal_name}/otp */
export interface OtpResponse {
  otp: string;
  portal_name: string;
  display_name: string;
  period: number;
  valid_for_seconds: number;
  timestamp: number;
  issued_at: number;
  expires_at: number;
  server_time: number;
  request_id: string;
}

/* ADDED: GET /api/v1/admin/portals */
export interface AdminPortal {
  portal_name: string;
  display_name: string;
  period: number;
  status: "active" | "disabled";
  created_at?: string | number | null;
  grants: AdminGrant[];
}

export interface AdminGrant {
  username: string;
  expires_at: string | number | null;
  source: "direct" | "team";
  team_name?: string | null;
}

/* ADDED: GET /api/v1/admin/users */
export interface AdminUser {
  id: number;
  username: string;
  role: Role;
  status: "active" | "disabled";
  created_at?: string | number | null;
  last_login_at?: string | number | null;
}

/* ADDED: GET /api/v1/admin/teams */
export interface AdminTeam {
  name: string;
  members: string[];
  grants: Array<{ portal_name: string; expires_at: string | number | null }>;
}

/* EXISTING: GET /api/v1/clients */
export interface AutomationClient {
  id: number;
  name: string;
  environment: string;
  status?: string;
  revoked_at?: string | number | null;
  expires_at?: string | number | null;
  created_at?: string | number | null;
}

/* EXISTING: GET /api/v1/clients/{id}/credentials */
export interface ClientCredential {
  id: number;
  created_at?: string | number | null;
  expires_at?: string | number | null;
  revoked_at?: string | number | null;
  last_used_at?: string | number | null;
}

/* EXISTING: GET /admin/api/v1/audit?limit=100 */
export interface AuditEvent {
  id: number | string;
  created_at?: string | number | null;
  timestamp?: string | number | null;
  event?: string;
  action?: string;
  actor?: string | null;
  username?: string | null;
  portal_name?: string | null;
  outcome?: string | null;
  detail?: string | null;
  ip_address?: string | null;
}
