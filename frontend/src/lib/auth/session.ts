const ACCESS_TOKEN_KEY = 'noobbook.access_token';
const REFRESH_TOKEN_KEY = 'noobbook.refresh_token';
const ASSET_TOKEN_KEY = 'noobbook.asset_token';

export const getAccessToken = (): string | null => {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

export const getAssetToken = (): string | null => {
  return localStorage.getItem(ASSET_TOKEN_KEY);
};

export const setAssetToken = (assetToken?: string | null) => {
  if (assetToken) {
    localStorage.setItem(ASSET_TOKEN_KEY, assetToken);
  }
};

export const setSession = (accessToken: string, refreshToken?: string | null, assetToken?: string | null) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  setAssetToken(assetToken);
};

export const clearSession = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(ASSET_TOKEN_KEY);
};
