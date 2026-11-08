"""
==========================================================================
 DEVELOPMENT MOCK DATA: never load into production.
==========================================================================
Seed data for local development and UI/flow testing, loaded with:

    python manage.py seed_dev_data

* Writes through the real Django models and, for customer activity, the real
  domain services (cart -> order placement -> status transitions -> payments,
  wallet, rewards, notifications), so relationships match production exactly.
* Repeatable: catalogue rows are upserted by natural keys; customer history is
  only created once per section. It never deletes anything.
* All people, phones, emails, addresses, brands and venues are fictional.
  Test accounts use the reserved `click.local` email domain.
"""

MARKER = "DEVELOPMENT MOCK DATA"
