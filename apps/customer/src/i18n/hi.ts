import type { Key } from './en';

/** हिन्दी — keys missing here fall back to English. */
export const hi: Partial<Record<Key, string>> = {
  'nav.home': 'होम', 'nav.ride': 'राइड', 'nav.food': 'खाना', 'nav.shop': 'शॉप', 'nav.explore': 'एक्सप्लोर',
  'common.retry': 'फिर से कोशिश करें', 'common.loading': 'लोड हो रहा है…', 'common.back': 'वापस', 'common.save': 'सेव करें', 'common.cancel': 'रद्द करें',
  'common.offline': 'आप ऑफ़लाइन हैं। पिछली बार लोड हुई जानकारी दिख रही है; दोबारा जुड़ने पर काम फिर से होंगे।',
  'common.backOnline': 'आप फिर से ऑनलाइन हैं',
  'explore.title': 'एक्सप्लोर', 'explore.subtitle': 'Click. आपके लिए जो कुछ कर सकता है', 'explore.quick': 'जल्दी के काम',
  'explore.features': 'Click. सुविधाएँ', 'explore.yours': 'आपका Click.', 'explore.account': 'अकाउंट',
  'quick.offers': 'ऑफ़र', 'quick.orders': 'ऑर्डर', 'quick.rides': 'राइड्स', 'quick.bookings': 'बुकिंग', 'quick.parcels': 'पार्सल',
  'quick.wishlist': 'विशलिस्ट', 'quick.rewards': 'रिवॉर्ड्स', 'quick.buzz': 'Click Buzz', 'quick.help': 'मदद और सहायता', 'quick.refer': 'दोस्त को बुलाएँ',
  'account.profile': 'प्रोफ़ाइल', 'account.addresses': 'सेव की गई जगहें', 'account.payments': 'भुगतान', 'account.notifications': 'सूचनाएँ',
  'account.settings': 'सेटिंग्स और प्राइवेसी', 'account.security': 'सुरक्षा', 'account.about': 'Click. के बारे में', 'account.terms': 'उपयोग की शर्तें',
  'account.privacy': 'प्राइवेसी नीति', 'account.logout': 'लॉग आउट',
  'settings.title': 'सेटिंग्स', 'settings.language': 'भाषा', 'settings.languageHint': 'और भारतीय भाषाएँ जोड़ी जा रही हैं।',
  'settings.personalised': 'मेरा Click. पर्सनलाइज़ करें',
  'refer.title': 'दोस्त को बुलाएँ', 'refer.share': 'इनवाइट शेयर करें', 'refer.copy': 'कोड कॉपी करें', 'refer.copied': 'कोड कॉपी हो गया', 'refer.how': 'यह कैसे काम करता है',
};
