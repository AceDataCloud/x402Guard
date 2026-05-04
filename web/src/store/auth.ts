/**
 * Auth store: Phantom-signed challenge → backend session token.
 *
 * Persists across reloads via localStorage (managed inside `client.ts`).
 * Re-hydrates on app boot if the token is still valid; otherwise exposes
 * `signIn()` for the home page.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { apiClient, getSessionToken, setSessionToken } from "@/api/client";
import { connectPhantom, disconnectPhantom, signMessage } from "@/wallet/phantom";

interface ChallengeResponse {
  nonce: string;
  message: string;
}
interface LoginResponse {
  session_token: string;
  pubkey: string;
  expires_in: number;
}

export const useAuthStore = defineStore("auth", () => {
  const pubkey = ref<string | null>(localStorage.getItem("x402guard.pubkey"));
  const token = ref<string | null>(getSessionToken());
  const signingIn = ref(false);

  const isAuthenticated = computed(() => !!token.value && !!pubkey.value);

  async function signIn(): Promise<void> {
    signingIn.value = true;
    try {
      const owner = await connectPhantom();
      const challenge = (
        await apiClient.get<ChallengeResponse>("/api/v1/auth/challenge")
      ).data;
      const signature = await signMessage(challenge.message);
      const loginRes = (
        await apiClient.post<LoginResponse>("/api/v1/auth/login", {
          pubkey: owner,
          message: challenge.message,
          signature,
        })
      ).data;
      setSessionToken(loginRes.session_token);
      token.value = loginRes.session_token;
      pubkey.value = loginRes.pubkey;
      localStorage.setItem("x402guard.pubkey", loginRes.pubkey);
    } finally {
      signingIn.value = false;
    }
  }

  async function signOut(): Promise<void> {
    setSessionToken(null);
    token.value = null;
    pubkey.value = null;
    localStorage.removeItem("x402guard.pubkey");
    await disconnectPhantom();
  }

  return { pubkey, token, signingIn, isAuthenticated, signIn, signOut };
});
