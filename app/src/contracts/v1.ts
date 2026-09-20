/**
 * Hand-maintained browser representation of contracts/python/cloud_compass_contracts/v1.py.
 * TenantContext is response/internal-context data only: callers must never send a tenant or
 * role selector to choose their authorization scope.
 */

export const CONTRACT_VERSION = "v1" as const;

export type Role = "viewer" | "operator" | "admin";
export type Provider = "aws" | "gcp" | "azure" | "simulated_aws";
export type ConnectionStatus =
  | "draft"
  | "validating"
  | "active"
  | "degraded"
  | "disabled"
  | "failed";

export interface UserIdentity {
  sub: string;
  email?: string | null;
  display_name?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
}

export interface TenantContext {
  tenant_id: string;
  user_id: string;
  role: Role;
  membership_id: string;
}

export interface ProviderConnection {
  id: string;
  provider: Provider;
  status: ConnectionStatus;
  display_name: string;
  account_id?: string | null;
  default_region?: string | null;
  validated_at?: string | null;
  freshness_at?: string | null;
}

export interface ProviderError {
  code: string;
  message: string;
  retryable: boolean;
  provider?: Provider | null;
  account_id?: string | null;
  region?: string | null;
}

export interface ProviderResult<T> {
  data: T;
  provider: Provider;
  retrieved_at: string;
  freshness_at?: string | null;
  partial: boolean;
  errors: ProviderError[];
  next_cursor?: string | null;
}

export interface CloudEvent {
  id: string;
  source: string;
  type: string;
  subject?: string | null;
  occurred_at: string;
  received_at: string;
  provider: Provider;
  account_id?: string | null;
  region?: string | null;
  idempotency_key: string;
  correlation_id?: string | null;
  attributes: Record<string, string | number | boolean | null>;
}

export interface Citation {
  id: string;
  source_type: "provider_result" | "curated_runbook";
  source_id: string;
  title: string;
  retrieved_at: string;
  excerpt?: string | null;
  url?: string | null;
}

export type ApiErrorCode =
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "validation"
  | "conflict"
  | "rate_limited"
  | "provider_failure"
  | "internal";

export interface ApiError {
  code: ApiErrorCode;
  message: string;
  request_id: string;
  retryable: boolean;
  details: Record<string, string | number | boolean | null>;
}

export interface ApiErrorEnvelope {
  api_version: typeof CONTRACT_VERSION;
  error: ApiError;
}
