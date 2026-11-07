/**
 * Click API data contract (camelCase JSON from the Django API).
 * Mirrors backend serializers; any change here must match the backend.
 * Money values are decimal strings (e.g. "249.00") to avoid float rounding.
 */

export type UUID = string;
export type Money = string;
export type ISODateTime = string;

export type StoreType = 'restaurant' | 'grocery' | 'retail';
export type Dietary = 'veg' | 'non_veg' | 'vegan' | 'unspecified';

export interface Paginated<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// --- Identity ---------------------------------------------------------
export type Role = 'customer' | 'staff';

export interface User {
  id: UUID;
  email: string;
  fullName: string;
  phone: string;
  roles: Role[];
  createdAt: ISODateTime;
}

export interface Session {
  user: User;
  access: string;
}

// --- Discovery ----------------------------------------------------------
export interface StoreCategory {
  id: UUID;
  name: string;
  slug: string;
  storeType: StoreType;
}

export interface StoreOffer {
  id: UUID;
  title: string;
  description: string;
}

export interface Store {
  id: UUID;
  slug: string;
  name: string;
  storeType: StoreType;
  description: string;
  imageUrl: string;
  categories: StoreCategory[];
  city: string;
  locality: string;
  ratingAverage: string;
  ratingCount: number;
  priceLevel: 1 | 2 | 3 | 4;
  deliveryTimeMin: number;
  deliveryTimeMax: number;
  deliveryFee: Money;
  minOrderAmount: Money;
  currency: string;
  isOpen: boolean;
  offers: StoreOffer[];
}

export interface StoreQuery {
  type?: StoreType;
  search?: string;
  category?: string;
  city?: string;
  open?: boolean;
  page?: number;
}

export interface Product {
  id: UUID;
  storeId: UUID;
  categoryId: UUID | null;
  name: string;
  description: string;
  imageUrl: string;
  price: Money;
  dietary: Dietary;
  isAvailable: boolean;
  isFeatured: boolean;
}

export interface MenuCategory {
  id: UUID;
  name: string;
  products: Product[];
}

export interface StoreMenu {
  storeId: UUID;
  categories: MenuCategory[];
}

// --- Customer -------------------------------------------------------------
export type AddressLabel = 'home' | 'work' | 'other';

export interface Address {
  id: UUID;
  label: AddressLabel;
  recipientName: string;
  phone: string;
  line1: string;
  line2: string;
  landmark: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
  latitude: string | null;
  longitude: string | null;
  isDefault: boolean;
  createdAt: ISODateTime;
}

export type AddressInput = Omit<Address, 'id' | 'createdAt' | 'latitude' | 'longitude'> &
  Partial<Pick<Address, 'latitude' | 'longitude'>>;

export interface CartTotals {
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  total: Money;
}

export interface CartItem {
  id: UUID;
  product: Product;
  quantity: number;
  note: string;
  lineTotal: Money;
}

export interface CartStore {
  id: UUID;
  slug: string;
  name: string;
  imageUrl: string;
  deliveryFee: Money;
  minOrderAmount: Money;
  currency: string;
  isOpen: boolean;
  deliveryTimeMin: number;
  deliveryTimeMax: number;
}

export interface Cart {
  id: UUID;
  store: CartStore | null;
  items: CartItem[];
  itemCount: number;
  totals: CartTotals;
}

// --- Orders -----------------------------------------------------------------
export type OrderStatus =
  | 'placed'
  | 'confirmed'
  | 'preparing'
  | 'ready'
  | 'out_for_delivery'
  | 'delivered'
  | 'cancelled';

export type PaymentMethod = 'cash_on_delivery';
export type PaymentStatus = 'pending' | 'authorized' | 'captured' | 'failed' | 'cancelled' | 'refunded';

export interface OrderSummary {
  id: UUID;
  number: string;
  status: OrderStatus;
  store: { id: UUID; slug: string; name: string; imageUrl: string };
  total: Money;
  currency: string;
  itemCount: number;
  createdAt: ISODateTime;
}

export interface OrderItem {
  id: UUID;
  productId: UUID | null;
  productName: string;
  unitPrice: Money;
  quantity: number;
  lineTotal: Money;
  note: string;
}

export interface OrderStatusEvent {
  fromStatus: OrderStatus | '';
  toStatus: OrderStatus;
  note: string;
  createdAt: ISODateTime;
}

export interface Payment {
  id: UUID;
  method: PaymentMethod;
  status: PaymentStatus;
  amount: Money;
  currency: string;
  createdAt: ISODateTime;
}

export interface OrderDetail extends OrderSummary {
  items: OrderItem[];
  events: OrderStatusEvent[];
  payments: Payment[];
  deliveryAddress: Omit<Address, 'id' | 'createdAt' | 'isDefault'>;
  customerNote: string;
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  estimatedDeliveryAt: ISODateTime | null;
  cancelledAt: ISODateTime | null;
  deliveredAt: ISODateTime | null;
  canCancel: boolean;
}

export interface PlaceOrderInput {
  addressId: UUID;
  paymentMethod: PaymentMethod;
  idempotencyKey: UUID;
  customerNote?: string;
}
