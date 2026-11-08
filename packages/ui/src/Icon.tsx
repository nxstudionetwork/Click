const PATHS = {
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm9 16-4.35-4.35',
  bag: 'M6 7h12l-1 13H7L6 7Zm3 0a3 3 0 0 1 6 0',
  home: 'M4 11 12 4l8 7v9h-5v-6H9v6H4v-9Z',
  food: 'M7 3v8m-3-8v5a3 3 0 0 0 6 0V3M7 11v10m10-18c-2 2-3 5-3 8h3v10',
  receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6m-6 4h6',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0',
  star: 'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z',
  clock: 'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  pin: 'M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Zm0-9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  grocery: 'M3 4h2l2.4 11h10.2L20 7H6.2M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm8 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  shop: 'M4 9h16l-1-5H5L4 9Zm0 0v11h16V9M9 20v-6h6v6',
  ride: 'M5 16h14l-1.5-6h-11L5 16Zm0 0v3m14-3v3M7.5 13h.01M16.5 13h.01M8 10l1-3h6l1 3',
  parcel: 'M3 7l9-4 9 4-9 4-9-4Zm0 0v10l9 4 9-4V7m-9 4v10',
  ticket: 'M3 8a2 2 0 0 0 0 4v4h18v-4a2 2 0 0 1 0-4V4H3v4Zm10-4v12',
  back: 'M15 5l-7 7 7 7',
  alert: 'M12 8v5m0 3h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  close: 'M6 6l12 12M18 6 6 18',
  check: 'M5 12l5 5L20 7',
  tag: 'M3 12V4h8l10 10-8 8L3 12Zm5-4h.01',
  bell: 'M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2Zm4 4a2 2 0 0 0 4 0',
  sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Zm7 12 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z',
  heart: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z',
  gift: 'M4 11h16v9H4v-9Zm-1-4h18v4H3V7Zm9 0v13M12 7S10.5 3 8 4s0 3 4 3Zm0 0s1.5-4 4-3 0 3-4 3Z',
  compass: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm3.5-12.5-2 5-5 2 2-5 5-2Z',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-2.5-11.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7m0 3h.01',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1c.6.5 1.3.9 2 1.2l.4 2.6h5l.4-2.6c.7-.3 1.4-.7 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z',
  card: 'M3 6h18v12H3V6Zm0 4h18M7 15h3',
  chevron: 'M6 9l6 6 6-6',
  right: 'M9 5l7 7-7 7',
  wrench: 'M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4 2.5-2.5Z',
  send: 'M4 12l16-8-6 16-2-6-8-2Z',
  // Partner app
  car: 'M5 17h14v-4l-2-5H7l-2 5v4Zm0 0v2m14-2v2M5 13h14M8 15.5h.01M16 15.5h.01',
  auto: 'M4 17V9a4 4 0 0 1 4-4h6l5 6v6H4Zm0 0h15M8 17a1.5 1.5 0 1 0 0 .01M16 17a1.5 1.5 0 1 0 0 .01M12 5v6h7',
  bike: 'M5.5 18a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm13 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM5.5 15l4-6h5l4 6M9 6h3l2.5 3',
  fleet: 'M3 15h9v-4l-1.5-3H5l-2 3v4Zm9-2h4l2-3h-6m-9 5v2m9-2v2m4-4h5v4h-5',
  key: 'M14 10a4 4 0 1 0-3.9 4H11v2h2v2h2v2h3v-3l-4.1-4.1A4 4 0 0 0 14 10Zm-4-1h.01',
  bus: 'M5 4h14v13H5V4Zm0 8h14M8 20v-3m8 3v-3M8 15h.01M16 15h.01',
  coffee: 'M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9Zm12 1h1.5a2.5 2.5 0 0 1 0 5H16M8 3v3m4-3v3',
  cake: 'M4 21h16v-8H4v8Zm0-4c2 0 2-1.5 4-1.5s2 1.5 4 1.5 2-1.5 4-1.5 2 1.5 4 1.5M12 13V9m0-3.5c.8 0 1.5-.7 1.5-1.5S12 2 12 2s-1.5 1.2-1.5 2 .7 1.5 1.5 1.5Z',
  device: 'M7 3h10v18H7V3Zm4 15h2',
  shirt: 'M8 4 4 6l1.5 4L8 9v11h8V9l2.5 1L20 6l-4-2a4 4 0 0 1-8 0Z',
  warehouse: 'M3 20V9l9-5 9 5v11M7 20v-8h10v8M7 16h10',
  team: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-6 9a6 6 0 0 1 12 0m1-9a3 3 0 1 0-1.5-5.6M21 20a6 6 0 0 0-4-5.7',
  briefcase: 'M4 8h16v11H4V8Zm5 0V5h6v3M4 13h16',
  film: 'M4 4h16v16H4V4Zm4 0v16M16 4v16M4 8h4m-4 4h4m-4 4h4m8-8h4m-4 4h4m-4 4h4',
  hotel: 'M4 20V4h11v16M15 9h5v11M8 8h3m-3 4h3m-3 4h3M2 20h20',
  ball: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-18v18M3 12h18M5.6 5.6c3.5 3.5 3.5 9.3 0 12.8M18.4 5.6c-3.5 3.5-3.5 9.3 0 12.8',
  store: 'M3 9l1.5-5h15L21 9M3 9v1a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0V9M3 9h18M5 13v7h14v-7M10 20v-4h4v4',
  plus: 'M12 5v14M5 12h14',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11',
  phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z',
  shield: 'M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3Zm-3 9 2 2 4-4',
  share: 'M12 15V3m0 0L8 7m4-4 4 4M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7',
  download: 'M12 3v12m0 0-4-4m4 4 4-4M5 19h14',
  locate: 'M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm0-4a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0-13v3m0 14v3M2 12h3m14 0h3',
  edit: 'M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4',
  chart: 'M4 20V4m0 16h16M8 16v-4m4 4V8m4 8v-6',
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 22, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
