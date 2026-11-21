/**
 * ============================================================================
 *  TEMPORARY MOCK DATA — REPLACE WITH REAL API DATA
 * ============================================================================
 *  10 restaurants + menus used ONLY when VITE_STORES_SOURCE=mock, so the
 *  discovery UI can be evaluated without the backend (layout, images, badges,
 *  closed state, offers, search/filter, loading/empty/error states).
 *
 *  Typed against the real API contract (@click/api), so components cannot
 *  depend on mock-only fields. The real equivalent is served by Django
 *  (`python manage.py seed_dev_data` in development).
 *
 *  Delete this folder once discovery is verified against production data.
 * ============================================================================
 */

import type { MenuCategory, Product, Store, StoreCategory } from '@click/api';

const cat = (slug: string, name: string): StoreCategory => ({ id: `mock-cat-${slug}`, slug, name, storeType: 'restaurant' });

export const MOCK_CATEGORIES: StoreCategory[] = [
  cat('biryani', 'Biryani'),
  cat('pizza', 'Pizza'),
  cat('south-indian', 'South Indian'),
  cat('burgers', 'Burgers'),
  cat('healthy', 'Healthy'),
  cat('desserts', 'Desserts'),
  cat('chinese', 'Chinese'),
  cat('north-indian', 'North Indian'),
  cat('cafe', 'Cafe'),
];
const C = Object.fromEntries(MOCK_CATEGORIES.map((c) => [c.slug, c])) as Record<string, StoreCategory>;

const unsplash = (id: string) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=800&q=70`;

type Seed = [slug: string, name: string, cats: string[], rating: string, count: number, price: 1 | 2 | 3 | 4,
  eta: [number, number], fee: string, min: string, open: boolean, offer: string | null, image: string];

const SEEDS: Seed[] = [
  ['saffron-smoke-biryani-house', 'Saffron Smoke Biryani House', ['biryani', 'north-indian'], '4.6', 2140, 2, [25, 35], '29', '149', true, '20% off up to ₹100', ''],
  ['crust-coal-pizzeria', 'Crust & Coal Pizzeria', ['pizza'], '4.4', 980, 3, [30, 40], '39', '199', true, 'Free delivery over ₹399', unsplash('1513104890138-7c749659a591')],
  ['dosa-district', 'Dosa District', ['south-indian'], '4.7', 3520, 1, [20, 30], '19', '99', true, null, ''],
  ['stack-burger-lab', 'Stack Burger Lab', ['burgers'], '4.2', 760, 2, [25, 35], '29', '149', true, 'Buy 1 get 1 on classics', unsplash('1568901346375-23c9450c58cd')],
  ['green-bowl-kitchen', 'Green Bowl Kitchen', ['healthy'], '4.5', 640, 3, [20, 30], '35', '199', true, null, unsplash('1512621776951-a57141f2eefd')],
  ['midnight-mithai', 'Midnight Mithai', ['desserts'], '4.8', 1890, 2, [15, 25], '25', '99', true, '₹50 off first order', ''],
  ['wok-theory', 'Wok Theory', ['chinese'], '4.1', 520, 2, [30, 45], '35', '149', true, null, ''],
  ['tandoor-republic', 'Tandoor Republic', ['north-indian'], '4.3', 1430, 3, [35, 50], '45', '249', true, '15% off weekends', unsplash('1504674900247-0877df9cc836')],
  ['brew-ritual-cafe', 'Brew Ritual Cafe', ['cafe', 'desserts'], '4.6', 410, 2, [15, 25], '19', '99', true, null, ''],
  ['coastal-curry-co', 'Coastal Curry Co.', ['south-indian', 'north-indian'], '3.9', 210, 2, [40, 55], '49', '199', false, null, ''],
];

export const MOCK_STORES: Store[] = SEEDS.map(([slug, name, cats, rating, count, price, eta, fee, min, open, offer, image], i) => ({
  id: `mock-store-${i + 1}`,
  slug,
  name,
  storeType: 'restaurant',
  description: `${cats.map((c) => C[c]!.name).join(' · ')} favourites, cooked fresh.`,
  imageUrl: image,
  categories: cats.map((c) => C[c]!),
  city: 'Bengaluru',
  locality: 'Indiranagar',
  ratingAverage: rating,
  ratingCount: count,
  priceLevel: price,
  deliveryTimeMin: eta[0],
  deliveryTimeMax: eta[1],
  deliveryFee: `${fee}.00`,
  minOrderAmount: `${min}.00`,
  currency: 'INR',
  isOpen: open,
  offers: offer ? [{ id: `mock-offer-${i + 1}`, title: offer, description: '', endsAt: null, discountType: '', discountValue: '0.00', maxDiscount: null, minOrderAmount: '0.00', isRedeemable: false }] : [],
  distanceKm: null,
}));

const MENU_ITEMS: Record<string, [string, Product['dietary'], string][]> = {
  biryani: [['Hyderabadi Chicken Biryani', 'non_veg', '289'], ['Paneer Tikka Biryani', 'veg', '249'], ['Mutton Dum Biryani', 'non_veg', '369']],
  pizza: [['Margherita Classica', 'veg', '249'], ['Smoked Chicken Pesto', 'non_veg', '389'], ['Four Cheese Bianca', 'veg', '349']],
  'south-indian': [['Ghee Roast Dosa', 'veg', '129'], ['Idli Vada Combo', 'veg', '99'], ['Mysore Masala Dosa', 'veg', '139']],
  burgers: [['The Classic Stack', 'non_veg', '199'], ['Crispy Paneer Burger', 'veg', '179'], ['Double Smash', 'non_veg', '279']],
  healthy: [['Quinoa Power Bowl', 'vegan', '299'], ['Grilled Chicken Salad', 'non_veg', '319'], ['Avocado Toast', 'veg', '249']],
  desserts: [['Kesar Rasmalai (2 pc)', 'veg', '149'], ['Gulab Jamun Cheesecake', 'veg', '199'], ['Hot Chocolate Fudge', 'veg', '179']],
  chinese: [['Chilli Garlic Noodles', 'veg', '199'], ['Kung Pao Chicken', 'non_veg', '279'], ['Veg Manchurian Gravy', 'veg', '219']],
  'north-indian': [['Butter Chicken', 'non_veg', '339'], ['Dal Makhani', 'veg', '239'], ['Garlic Naan', 'veg', '59']],
  cafe: [['Cold Brew Tonic', 'vegan', '189'], ['Hazelnut Cappuccino', 'veg', '169'], ['Almond Croissant', 'veg', '149']],
};

export const MOCK_MENUS: Record<string, MenuCategory[]> = Object.fromEntries(
  MOCK_STORES.map((store) => [
    store.slug,
    store.categories.map((c, ci) => ({
      id: `${store.id}-menu-${c.slug}`,
      name: c.name,
      products: MENU_ITEMS[c.slug]!.map(([name, dietary, price], pi) => ({
        id: `${store.id}-p-${c.slug}-${pi}`,
        storeId: store.id,
        categoryId: `${store.id}-menu-${c.slug}`,
        name,
        description: `House-made ${name.toLowerCase()}.`,
        imageUrl: '',
        price: `${price}.00`,
        compareAtPrice: null,
        discountPercent: null,
        brand: '',
        unitLabel: '',
        lowStock: false,
        dietary,
        isAvailable: !(ci === 0 && pi === 2 && store.slug === 'tandoor-republic'),
        isFeatured: pi === 0,
        optionGroups: [], shopCategoryId: null, hasVariants: false,
      })),
    })),
  ]),
);
