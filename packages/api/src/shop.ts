/** Click. Shopping (marketplace) API shapes. Mirrors backend/apps/shop/serializers.py. */
import type { DeliveryEstimate, ISODateTime, Money, UUID } from './types';

export type ShopBadge = 'best_seller' | 'trending' | 'new' | 'top_rated' | 'limited_deal';

export interface ShopImage { src: string; srcSet: string; width: number | null; height: number | null; alt: string }

export interface ShopDeal {
  kind: 'limited' | 'flash' | 'price_drop';
  label: string;
  percentOff: number;
  /** Countdowns are computed from this backend end time only. */
  endsAt: ISODateTime;
  /** Units left at the deal price, when the deal is limited by quantity. */
  remaining: number | null;
}

export interface ShopCard {
  id: UUID;
  name: string;
  brand: string;
  brandSlug: string | null;
  category: string | null;
  categorySlug: string | null;
  categoryIcon: string;
  image: ShopImage | null;
  price: Money;
  /** Genuine reference price (seller's compare-at price, or the list price during a deal). */
  referencePrice: Money | null;
  discountPercent: number | null;
  /** True when variants have different prices (price is the lowest). */
  fromPrice: boolean;
  rating: number | null;
  ratingCount: number;
  badges: ShopBadge[];
  deal: ShopDeal | null;
  inStock: boolean;
  hasVariants: boolean;
  seller: { name: string; slug: string; isVerified: boolean };
  freeDeliveryAbove: Money | null;
  codAvailable: boolean;
  /** Why it's recommended (personal sections only). */
  reason: string | null;
}

export interface ShopCategory {
  id: UUID;
  slug: string;
  name: string;
  description: string;
  imageUrl: string;
  icon: string;
  parentSlug: string | null;
  productCount: number | null;
}

export interface ShopCampaign {
  id: UUID;
  kind: string;
  eyebrow: string;
  title: string;
  subtitle: string;
  imageUrl: string;
  ctaLabel: string;
  ctaPath: string;
  endsAt: ISODateTime;
}

export interface ShopBrand { id: UUID; name: string; slug: string; logoUrl: string; productCount: number }

export type ShopSection =
  | { id: string; kind: 'products'; title: string; subtitle: string | null; link: string | null; products: ShopCard[] }
  | { id: string; kind: 'brands'; title: string; subtitle: string | null; link: string | null; brands: ShopBrand[] };

export interface ShopHome { campaigns: ShopCampaign[]; categories: ShopCategory[]; sections: ShopSection[]; personalized: boolean }
export interface ShopFeedPage { results: ShopCard[]; nextCursor: string | null; personalized: boolean }

export interface ShopInterpretation {
  text: string;
  terms: string[];
  category: string | null;
  brand: string | null;
  colour: string | null;
  minPrice: number | null;
  maxPrice: number | null;
  sort: string | null;
  gift: boolean;
  age: number | null;
  /** Only what the search actually understood and applied. */
  understood: { kind: string; label: string }[];
}

export interface ShopFacetValue { value: string; count: number }
export interface ShopFacets {
  categories: { slug: string; name: string; count: number }[];
  brands: { slug: string; name: string; count: number }[];
  sellers: { slug: string; name: string; count: number }[];
  price: { min: Money | null; max: Money | null };
  ratings: { value: number; count: number }[];
  discounts: { value: number; count: number }[];
  /** Category-specific specs (only once a category is known). */
  attributes: { code: string; name: string; values: ShopFacetValue[] }[];
  /** Variant options such as Size and Color. */
  options: { code: string; name: string; values: ShopFacetValue[] }[];
}

export type ShopSort = 'relevance' | 'popular' | 'price_asc' | 'price_desc' | 'rating' | 'newest' | 'discount';

export interface ShopSearchResult {
  query: string;
  interpretation: ShopInterpretation | null;
  sort: ShopSort;
  category: ShopCategory | null;
  correction: string | null;
  count: number;
  page: number;
  hasMore: boolean;
  results: ShopCard[];
  facets: ShopFacets;
  applied: { minPrice: number | null; maxPrice: number | null; brands: string[] };
}

export interface ShopSuggestions {
  query: string;
  suggestions: { text: string; kind: 'category' | 'brand' | 'product'; path: string | null }[];
  trending: string[];
  categories: ShopCategory[];
}

export interface ShopCategoryPage {
  category: ShopCategory;
  parent: ShopCategory | null;
  children: ShopCategory[];
  siblings: ShopCategory[];
  campaigns: ShopCampaign[];
  highlight: { title: string; products: ShopCard[] } | null;
}

export interface ShopVariant {
  id: UUID;
  options: Record<string, string>;
  label: string;
  price: Money;
  referencePrice: Money | null;
  discountPercent: number | null;
  inStock: boolean;
  lowStock: boolean;
}

export interface ShopReview {
  id: UUID;
  rating: number;
  title: string;
  body: string;
  variantLabel: string;
  verifiedPurchase: boolean;
  author: string;
  createdAt: ISODateTime;
  edited: boolean;
}

export interface ShopProductDetail extends ShopCard {
  description: string;
  highlights: string[];
  unitLabel: string;
  gallery: ShopImage[];
  variants: ShopVariant[];
  axes: { name: string; values: string[] }[];
  specs: { name: string; value: string; code: string }[];
  seller: ShopCard['seller'] & {
    id: UUID; rating: number | null; ratingCount: number; city: string; isOpen: boolean; dispatchDays: number;
    returnPolicy: string; deliveryFee: Money; freeDeliveryAbove: Money | null;
  };
  policies: { returnDays: number | null; replacementOnly: boolean; warranty: string; codAvailable: boolean; securePayment: boolean };
  delivery: DeliveryEstimate | null;
  ratingSummary: { average: number | null; count: number; distribution: Record<string, number> };
  reviews: ShopReview[];
  myReview: ShopReview | null;
  canReview: boolean;
  similar: ShopCard[];
  boughtTogether: ShopCard[];
  lowStock: boolean;
  /** The seller's current offers (redeemable ones are applied at checkout by the server). */
  offers: { id: UUID; title: string; description: string; minOrderAmount: Money; redeemable: boolean }[];
}

export interface ShopReviewPage { results: ShopReview[]; count: number; page: number; hasMore: boolean }
export interface ShopComparison { products: ShopCard[]; rows: { label: string; values: (string | null)[]; differs: boolean }[] }
export interface ShopReviewInput { rating: number; title?: string; body?: string }
