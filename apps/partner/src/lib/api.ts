import { authApi, buzzEngageApi, createClickClient, driverApi, partnerApi, partnerBuzzApi, restaurantApi } from '@click/api';

/** Same Click identity and session model as every Click app (in-memory access token, httpOnly refresh cookie). */
const client = createClickClient({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1', clientId: 'partner-web' });

export const { http, session, refreshSession, restoreSession } = client;

export const api = {
  auth: authApi(http),
  partner: partnerApi(http),
  restaurant: restaurantApi(http),
  driver: driverApi(http),
  buzz: partnerBuzzApi(http),
  buzzEngage: buzzEngageApi(http),
};
