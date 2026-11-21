import { describe, expect, it } from 'vitest';
import type { OfferWithStore } from '@click/api';
import { daypart, greetingFor, momentsFor } from '../../config/home';
import { servicePhoto } from '../../config/media';
import { resolveScan } from '../assist/CameraSearch';
import { clearRecentSearches, recentSearches, rememberSearch } from '../search/recent';
import { interleaveOffers, offerHeadline } from './OfferCarousel';

const at = (iso: string) => new Date(iso);

describe('Home configuration', () => {
  it('picks the daypart and greeting from local time', () => {
    expect(daypart(at('2026-11-09T07:00:00'))).toBe('morning');
    expect(daypart(at('2026-11-09T13:00:00'))).toBe('afternoon');
    expect(daypart(at('2026-11-09T19:00:00'))).toBe('evening');
    expect(daypart(at('2026-11-09T02:00:00'))).toBe('night');
    expect(greetingFor(at('2026-11-09T09:00:00'))).toBe('Good morning');
    expect(greetingFor(at('2026-11-09T20:00:00'))).toBe('Good evening');
  });

  it('moments are config-driven real catalogue queries, with weekend extras', () => {
    const weekday = momentsFor(at('2026-11-10T08:00:00')); // Tuesday morning
    expect(weekday.map((m) => m.id)).toEqual(['breakfast', 'coffee']);
    expect(weekday[0]!.query).toMatchObject({ type: 'restaurant', category: 'south-indian' });
    expect(momentsFor(at('2026-11-14T19:00:00')).map((m) => m.id)).toContain('weekend-shopping'); // Saturday
  });

  it('service photos are local real photographs, never generated', () => {
    expect(servicePhoto('food')!.src).toBe('/media/onboarding/food-640.webp');
    expect(servicePhoto('wallet')).toBeNull();
  });
});

describe('Offers', () => {
  it('splits a value headline from the offer title', () => {
    expect(offerHeadline('20% off up to ₹100')).toEqual({ big: '20% OFF', rest: 'up to ₹100' });
    expect(offerHeadline('Flat ₹30 off momo platters')).toEqual({ big: 'FLAT ₹30 OFF', rest: 'momo platters' });
    expect(offerHeadline('Free delivery all day')).toEqual({ big: 'FREE DELIVERY', rest: 'all day' });
    expect(offerHeadline('Kitchen sale')).toEqual({ big: '', rest: 'Kitchen sale' });
  });

  it('interleaves services and puts open stores first', () => {
    const o = (id: string, storeType: string, isOpen = true) => ({ id, store: { storeType, isOpen } }) as unknown as OfferWithStore;
    const out = interleaveOffers([o('r1', 'retail'), o('r2', 'retail'), o('f1', 'restaurant', false), o('f2', 'restaurant'), o('g1', 'grocery')]);
    expect(out.map((x) => x.id)).toEqual(['f2', 'g1', 'r1', 'f1', 'r2']);
  });
});

describe('Camera scan', () => {
  it('opens Click. links in-app and turns anything else into a search', () => {
    expect(resolveScan('https://click.example/stores/dosa-district?x=1', 'https://click.example')).toBe('/stores/dosa-district?x=1');
    expect(resolveScan('https://evil.example/phish', 'https://click.example')).toBe('/search?q=https%3A%2F%2Fevil.example%2Fphish');
    expect(resolveScan('/movies', 'https://click.example')).toBe('/movies');
    expect(resolveScan('//evil.example', 'https://click.example')).toBe('/search?q=%2F%2Fevil.example');
  });
});

describe('Recent searches', () => {
  it('keeps the newest unique terms on this device', () => {
    clearRecentSearches();
    ['pizza', 'dosa', 'Pizza', ' '].forEach(rememberSearch);
    expect(recentSearches()).toEqual(['Pizza', 'dosa']);
    clearRecentSearches();
    expect(recentSearches()).toEqual([]);
  });
});
