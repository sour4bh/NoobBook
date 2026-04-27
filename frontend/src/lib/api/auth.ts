import type { AxiosError } from 'axios';
import { api } from './client';
import { setSession, setAssetToken, clearSession } from '../auth/session';
import {
  parseAuthSessionResponse,
  parseMeResponse,
  type AuthSessionResponse,
  type MeResponse,
} from './contracts';

export type { MeResponse };
export type AuthResponse = AuthSessionResponse | { success: false; error: string };

interface ApiErrorBody {
  error?: string;
  message?: string;
}

export const authAPI = {
  async me(): Promise<MeResponse> {
    const response = await api.get('/auth/me');
    const data = parseMeResponse(response.data);
    setAssetToken(data.asset_token);
    return data;
  },

  async signIn(email: string, password: string): Promise<AuthResponse> {
    try {
      const response = await api.post('/auth/signin', { email, password });
      const data = parseAuthSessionResponse(response.data);
      if (data.session?.access_token) {
        setSession(data.session.access_token, data.session.refresh_token, data.asset_token);
      }
      return data;
    } catch (err) {
      const error = err as AxiosError<ApiErrorBody>;
      const message =
        error.response?.data?.error ||
        error.response?.data?.message ||
        error.message ||
        'Sign in failed';
      return { success: false, error: message };
    }
  },

  async signUp(email: string, password: string): Promise<AuthResponse> {
    try {
      const response = await api.post('/auth/signup', { email, password });
      const data = parseAuthSessionResponse(response.data);
      if (data.session?.access_token) {
        setSession(data.session.access_token, data.session.refresh_token, data.asset_token);
      }
      return data;
    } catch (err) {
      const error = err as AxiosError<ApiErrorBody>;
      const message =
        error.response?.data?.error ||
        error.response?.data?.message ||
        error.message ||
        'Sign up failed';
      return { success: false, error: message };
    }
  },

  async signOut(): Promise<void> {
    try {
      await api.post('/auth/signout');
    } finally {
      clearSession();
    }
  },
};
