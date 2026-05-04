/**
 * Vaults store: list + cache the user's agent vaults plus pending tx state.
 */
import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/api/client";

export interface VaultRow {
  id: string;
  owner_pubkey: string;
  agent_name: string;
  vault_pda: string;
  policy_pda: string;
  delegation_pubkey: string;
  daily_cap_usdc: number;
  per_call_cap_usdc: number;
  endpoint_allowlist: string[];
  expires_at: string; // ISO
  paused: boolean;
  create_tx: string | null;
  created_at: string;
}

export interface UnsignedTxResponse {
  tx_b64: string;
  vault_pda: string;
  policy_pda: string;
  delegation_pubkey: string;
  pending_id: string;
}

export interface MCPSessionRow {
  token: string;
  label: string | null;
  mcp_url: string;
  created_at: string;
}

export const useVaultsStore = defineStore("vaults", () => {
  const vaults = ref<VaultRow[]>([]);
  const loading = ref(false);
  const lastError = ref<string | null>(null);

  async function refresh(): Promise<void> {
    loading.value = true;
    lastError.value = null;
    try {
      const res = await apiClient.get<{ vaults: VaultRow[] }>("/api/v1/vaults");
      vaults.value = res.data.vaults;
    } catch (err) {
      lastError.value = (err as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function buildCreateTx(payload: {
    agent_name: string;
    daily_cap_usdc: number;
    per_call_cap_usdc: number;
    endpoint_allowlist: string[];
    expires_at: string;
  }): Promise<UnsignedTxResponse> {
    return (await apiClient.post<UnsignedTxResponse>("/api/v1/vaults/create", payload)).data;
  }

  async function finalise(pendingId: string, txSignature: string): Promise<void> {
    await apiClient.post("/api/v1/vaults/finalise", {
      pending_id: pendingId,
      tx_signature: txSignature,
    });
  }

  async function buildOwnerActionTx(
    vaultId: string,
    action: "pause" | "resume" | "clawback"
  ): Promise<UnsignedTxResponse> {
    return (
      await apiClient.post<UnsignedTxResponse>(
        `/api/v1/vaults/${vaultId}/${action}`
      )
    ).data;
  }

  async function markPaused(vaultId: string, paused: boolean): Promise<void> {
    await apiClient.post(`/api/v1/vaults/${vaultId}/mark-paused`, null, {
      params: { paused },
    });
  }

  async function listMcpSessions(vaultId: string): Promise<MCPSessionRow[]> {
    return (
      await apiClient.get<MCPSessionRow[]>(
        `/api/v1/vaults/${vaultId}/mcp-sessions`
      )
    ).data;
  }

  async function createMcpSession(
    vaultId: string,
    label?: string
  ): Promise<MCPSessionRow> {
    return (
      await apiClient.post<MCPSessionRow>(`/api/v1/vaults/${vaultId}/mcp-sessions`, {
        label: label ?? null,
      })
    ).data;
  }

  async function revokeMcpSession(vaultId: string, token: string): Promise<void> {
    await apiClient.delete(`/api/v1/vaults/${vaultId}/mcp-sessions/${token}`);
  }

  return {
    vaults,
    loading,
    lastError,
    refresh,
    buildCreateTx,
    finalise,
    buildOwnerActionTx,
    markPaused,
    listMcpSessions,
    createMcpSession,
    revokeMcpSession,
  };
});
