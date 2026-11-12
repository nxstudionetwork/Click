import { authApi, catalogApi, createClickClient, buddyApi, customerApi, eventHubApi, eventsApi, groceriesApi, hotelsApi, parcelsApi, servicesApi, shopApi, showtimeApi, storesApi } from '@click/api';

/** Session wiring (in-memory access token, httpOnly refresh cookie) is shared via @click/api. */
const client = createClickClient({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1', clientId: 'customer-web' });

export const { http, session, refreshSession } = client;

export const api = {
  auth: authApi(http),
  stores: storesApi(http),
  catalog: catalogApi(http),
  events: eventsApi(http),
  customer: customerApi(http),
  shop: shopApi(http),
  showtime: showtimeApi(http),
  groceries: groceriesApi(http),
  parcels: parcelsApi(http),
  services: servicesApi(http),
  /** Click. Events: plan events, teams, venues, quotes and bookings (not Showtime's `events`). */
  eventHub: eventHubApi(http),
  hotels: hotelsApi(http),
  /** Buddy conversations and the secure action layer. */
  buddy: buddyApi(http),
};
