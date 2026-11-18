/** English — the complete source dictionary. Keys are stable ids; add new UI strings here first. */
export const en = {
  'nav.home': 'Home', 'nav.ride': 'Ride', 'nav.food': 'Food', 'nav.shop': 'Shop', 'nav.explore': 'Explore', 'nav.primary': 'Primary',
  'common.retry': 'Try again', 'common.loading': 'Loading…', 'common.back': 'Back', 'common.save': 'Save', 'common.cancel': 'Cancel',
  'common.offline': 'You’re offline. Showing what was last loaded; actions will work again when you reconnect.',
  'common.backOnline': 'Back online',
  'explore.title': 'Explore', 'explore.subtitle': 'Everything Click. can do for you', 'explore.quick': 'Quick actions',
  'explore.features': 'Click. Features', 'explore.yours': 'Your Click.', 'explore.account': 'Account',
  'quick.offers': 'Offers', 'quick.orders': 'Orders', 'quick.rides': 'Rides', 'quick.bookings': 'Bookings', 'quick.parcels': 'Parcels',
  'quick.wishlist': 'Wishlist', 'quick.rewards': 'Rewards', 'quick.buzz': 'Click Buzz', 'quick.help': 'Help & Support', 'quick.refer': 'Refer a friend',
  'account.profile': 'Profile', 'account.profileHint': 'Your Click. ID and details', 'account.addresses': 'Saved locations', 'account.addressesHint': 'Home, work and other places',
  'account.payments': 'Payments', 'account.paymentsHint': 'Methods and history', 'account.notifications': 'Notifications', 'account.notificationsHint': 'Updates and preferences',
  'account.settings': 'Settings & privacy', 'account.settingsHint': 'Language, personalisation, appearance', 'account.security': 'Security & safety',
  'account.securityHint': 'Sign-ins, reports and emergency help', 'account.about': 'About Click.', 'account.terms': 'Terms of use', 'account.privacy': 'Privacy policy',
  'account.logout': 'Log out',
  'settings.title': 'Settings', 'settings.language': 'Language', 'settings.languageHint': 'More Indian languages are being added.',
  'settings.personalised': 'Personalise my Click.', 'settings.personalisedHint': 'Use my orders and searches for recommendations and recent searches. Turning it off also clears saved searches.',
  'refer.title': 'Refer a friend', 'refer.lead': 'Invite friends to Click.', 'refer.share': 'Share invite', 'refer.copy': 'Copy code', 'refer.copied': 'Code copied',
  'refer.how': 'How it works', 'refer.yours': 'Your invites', 'refer.none': 'No one has joined with your code yet.',
  'refer.reward': 'You get {referrer} points and your friend gets {referee} points when their first order is delivered.',
} as const;

export type Key = keyof typeof en;
