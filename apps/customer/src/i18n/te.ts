import type { Key } from './en';

/** తెలుగు — keys missing here fall back to English. */
export const te: Partial<Record<Key, string>> = {
  'nav.home': 'హోమ్', 'nav.ride': 'రైడ్', 'nav.food': 'ఫుడ్', 'nav.shop': 'షాప్', 'nav.explore': 'ఎక్స్‌ప్లోర్',
  'common.retry': 'మళ్ళీ ప్రయత్నించండి', 'common.loading': 'లోడ్ అవుతోంది…', 'common.back': 'వెనక్కి', 'common.save': 'సేవ్ చేయండి', 'common.cancel': 'రద్దు చేయండి',
  'common.offline': 'మీరు ఆఫ్‌లైన్‌లో ఉన్నారు. చివరిసారి లోడ్ అయిన సమాచారం చూపిస్తున్నాం; మళ్ళీ కనెక్ట్ అయ్యాక పనులు జరుగుతాయి.',
  'common.backOnline': 'మళ్ళీ ఆన్‌లైన్‌లో ఉన్నారు',
  'explore.title': 'ఎక్స్‌ప్లోర్', 'explore.subtitle': 'Click. మీ కోసం చేయగలిగినవన్నీ', 'explore.quick': 'త్వరిత చర్యలు',
  'explore.features': 'Click. ఫీచర్లు', 'explore.yours': 'మీ Click.', 'explore.account': 'ఖాతా',
  'quick.offers': 'ఆఫర్లు', 'quick.orders': 'ఆర్డర్లు', 'quick.rides': 'రైడ్లు', 'quick.bookings': 'బుకింగ్‌లు', 'quick.parcels': 'పార్సెల్స్',
  'quick.wishlist': 'విష్‌లిస్ట్', 'quick.rewards': 'రివార్డ్స్', 'quick.buzz': 'Click Buzz', 'quick.help': 'సహాయం & మద్దతు', 'quick.refer': 'స్నేహితుడిని ఆహ్వానించండి',
  'account.profile': 'ప్రొఫైల్', 'account.addresses': 'సేవ్ చేసిన ప్రదేశాలు', 'account.payments': 'చెల్లింపులు', 'account.notifications': 'నోటిఫికేషన్లు',
  'account.settings': 'సెట్టింగ్స్ & గోప్యత', 'account.security': 'భద్రత', 'account.about': 'Click. గురించి', 'account.terms': 'ఉపయోగ నిబంధనలు',
  'account.privacy': 'గోప్యతా విధానం', 'account.logout': 'లాగ్ అవుట్',
  'settings.title': 'సెట్టింగ్స్', 'settings.language': 'భాష', 'settings.languageHint': 'మరిన్ని భారతీయ భాషలు జోడిస్తున్నాం.',
  'settings.personalised': 'నా Click.‌ని వ్యక్తిగతీకరించు',
  'refer.title': 'స్నేహితుడిని ఆహ్వానించండి', 'refer.share': 'ఆహ్వానం షేర్ చేయండి', 'refer.copy': 'కోడ్ కాపీ చేయండి', 'refer.copied': 'కోడ్ కాపీ అయింది', 'refer.how': 'ఇది ఎలా పనిచేస్తుంది',
};
