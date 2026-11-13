import type { HttpClient } from './http';
import type {
  ShopCategoryPage, ShopComparison, ShopFeedPage, ShopHome, ShopProductDetail, ShopReview, ShopReviewInput, ShopReviewPage,
  ShopSearchResult, ShopSuggestions, ShopBrand, ShopCategory,
} from './shop';

/** Query for /shop/search. `attr_<code>` and `opt_<axis>` keys carry category filters (comma-separated values). */
export type ShopSearchQuery = Record<string, string | number | boolean | undefined>;

/** Click. Shopping discovery (public; personal sections when signed in) and the customer's own reviews. */
export const shopApi = (http: HttpClient) => ({
  home: () => http.request<ShopHome>('/shop/home'),
  feed: (cursor?: string | null) => http.request<ShopFeedPage>('/shop/feed', { query: { cursor: cursor ?? undefined } }),
  search: (query: ShopSearchQuery) => http.request<ShopSearchResult>('/shop/search', { query }),
  suggest: (q: string) => http.request<ShopSuggestions>('/shop/suggest', { query: { q } }),
  categories: () => http.request<{ results: ShopCategory[] }>('/shop/categories'),
  category: (slug: string) => http.request<ShopCategoryPage>(`/shop/categories/${slug}`),
  brands: () => http.request<{ results: ShopBrand[] }>('/shop/brands'),
  product: (id: string, at?: { lat?: number; lng?: number; city?: string }) =>
    http.request<ShopProductDetail>(`/shop/products/${id}`, { query: { lat: at?.lat, lng: at?.lng, city: at?.city } }),
  reviews: (id: string, opts: { page?: number; rating?: number } = {}) =>
    http.request<ShopReviewPage>(`/shop/products/${id}/reviews`, { query: opts }),
  compare: (ids: string[]) => http.request<ShopComparison>('/shop/compare', { query: { ids: ids.join(',') } }),
  /** Image search through the configured vision provider (503 `visual_search_unavailable` when none). */
  visualSearch: (file: Blob) => {
    const form = new FormData();
    form.append('image', file, 'photo');
    return http.request<{ query: string }>('/shop/visual-search', { method: 'POST', body: form });
  },
  review: {
    create: (productId: string, input: ShopReviewInput) =>
      http.request<ShopReview>(`/customer/shop/products/${productId}/review`, { method: 'POST', body: input }),
    update: (productId: string, input: ShopReviewInput) =>
      http.request<ShopReview>(`/customer/shop/products/${productId}/review`, { method: 'PATCH', body: input }),
    remove: (productId: string) => http.request<void>(`/customer/shop/products/${productId}/review`, { method: 'DELETE' }),
  },
});
