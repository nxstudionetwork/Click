import { Link } from 'react-router-dom';
import { MoneyHead } from '../features/money/parts';

type Doc = 'about' | 'terms' | 'privacy';
const TITLE: Record<Doc, string> = { about: 'About Click.', terms: 'Terms of use', privacy: 'Privacy policy' };

/**
 * About / Terms / Privacy. These are plain-language summaries of how the app actually works today. They are not the
 * final legal documents, and say so; the legally reviewed versions should replace these texts when published.
 */
export function LegalPage({ doc }: { doc: Doc }) {
  return (
    <div className="mn-page">
      <MoneyHead title={TITLE[doc]} />
      <article className="mn-article">
        {doc === 'about' && (
          <>
            <h2>One app. Many needs. One trusted experience.</h2>
            <p>Click. is a technology platform that connects you with independent partners — restaurants, stores, drivers, delivery partners,
              professionals, hotels, venues, pharmacies and other providers. Partners provide the products and services; Click. provides discovery,
              booking, payments, tracking, support and rewards.</p>
            <p>Every order or booking shows who provides it. Prices are set by partners; any Click. fee is shown separately at checkout.</p>
            <p>Click. is a venture of IFX Group. Contact: click.startup2026@gmail.com</p>
          </>
        )}
        {doc === 'terms' && (
          <>
            <p className="mn-banner mn-banner--warn small">Summary of how Click. works. The full legal terms are being finalised and will replace this page.</p>
            <h3>The service</h3><p>Click. lists partners and lets you order, book or request from them. The partner is responsible for what they supply;
              Click. handles the platform, payments it processes and support.</p>
            <h3>Prices and payments</h3><p>The total you see before you confirm is what you pay. Payments are confirmed by the payment provider or by
              Click. Wallet; Click. never stores card numbers, CVVs or UPI PINs.</p>
            <h3>Cancellations and refunds</h3><p>Each order or booking shows its cancellation and refund policy before you confirm. Refunds go back to
              where you paid, as shown on the order.</p>
            <h3>Your account</h3><p>One Click. account works across every service. Keep your phone number secure; you can sign out other devices in
              Safety Center and delete your account from Profile → Security.</p>
            <h3>Reviews and content</h3><p>Reviews must be about real experiences. Click. can hide content that is abusive, misleading or shares
              personal information.</p>
          </>
        )}
        {doc === 'privacy' && (
          <>
            <p className="mn-banner mn-banner--warn small">Summary of what the app does with your data. The full privacy policy is being finalised.</p>
            <h3>What we keep</h3><p>Your name, phone (verified by a one-time code), email, saved addresses, profile photo if you add one, and the orders,
              bookings, payments, reviews and support requests you make.</p>
            <h3>What we don’t keep</h3><p>Card numbers, CVVs, UPI PINs or one-time codes in readable form. Prescriptions are visible only to you and the
              pharmacy you chose.</p>
            <h3>Personalisation</h3><p>If “Personalise my Click.” is on, your orders and searches tailor recommendations and recent searches. You can turn
              it off in <Link to="/settings">Settings</Link>, which also clears saved searches. Sponsored placements never use your orders or searches.</p>
            <h3>Sharing</h3><p>Partners see what they need to fulfil your order or booking (for example your delivery address and name).</p>
            <h3>Your choices</h3><p>Notification preferences, sign-in management and account deletion are in the app. Questions:
              click.startup2026@gmail.com</p>
          </>
        )}
      </article>
    </div>
  );
}
