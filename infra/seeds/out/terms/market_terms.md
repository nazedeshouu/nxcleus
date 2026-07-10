# Terms of Sensitive Data Use

## Solano Marketplace, Inc.

Solano Marketplace operates a consumer e-commerce platform on which independent sellers list goods
and buyers place orders, pay, and leave reviews. In the course of that activity Solano collects
personal contact details, shipping locations, and payment instruments belonging to natural persons.
This document defines how that sensitive data may be used, and — critically — the limits that apply
whenever any of it would be transmitted to a system, model, or partner outside Solano-controlled
infrastructure. It exists to keep the platform aligned with consumer-privacy law (CCPA/CPRA and, for
EU/UK residents, the GDPR) and with the Payment Card Industry Data Security Standard (PCI DSS) as it
applies to cardholder data.

## Data classification

The following fields are classified as sensitive and are governed by the rules in this document.

- **buyers.name** — Personal data (identity). A buyer's real name.
- **buyers.email** — Personal data (contact). Direct electronic identifier of a natural person.
- **buyers.phone** — Personal data (contact). Direct telephone identifier of a natural person.
- **orders.ship_address** — Personal data (precise geolocation). Cleartext residential or delivery
  address tied to a specific order and buyer.
- **orders.ship_address_hash** — Pseudonymized data (linkage key). Salted digest of the shipping
  address; permits cross-order linkage without revealing the address itself.
- **orders.card_last4** — Cardholder data (PCI). The final four digits of the payment card used on
  an order. Solano stores no primary account number (PAN); only the last four are retained.
- **orders.card_network** — Cardholder data (PCI). The card scheme (for example Visa or Mastercard)
  associated with an order's payment.
- **sellers.country** — Business location data. Used to determine the residency rules that apply to a
  seller's payouts and records.

## Handling rules

- **Buyer contact identifiers must never leave Solano infrastructure in cleartext.** The values in
  buyers.email and buyers.phone must be masked before any external transmission — for example an
  email rendered as its local-part initial plus domain, and a phone reduced to its last two digits.
- **Buyer names may appear in external planning materials only in pseudonymized form.** No process
  that sends data to an external model may include buyers.name in plaintext; substitute a stable
  pseudonym or the buyer id.
- **Shipping addresses must never be transmitted externally.** orders.ship_address is precise
  geolocation data and may not appear in any brief, prompt, or export leaving Solano infrastructure;
  only the pseudonymized orders.ship_address_hash may be used to express cross-order linkage in
  external analysis.
- **Payment card data is handled strictly under PCI DSS.** Solano never stores a full PAN. Card
  numbers must always be masked to orders.card_last4 before any external transmission, and
  orders.card_last4 must never be combined with buyers.name or buyers.email in material sent outside
  Solano infrastructure.
- **Card network is reportable but not identifying alone.** orders.card_network may be shared in
  aggregate for fraud and settlement analysis, but never joined to an individual buyer's contact
  identifiers in external materials.
- **Data residency follows the buyer and seller.** Personal data of EU/UK residents must be
  processed and retained on infrastructure located in the EU/UK; seller records are governed by
  sellers.country, and payout and tax data for a seller must remain within that seller's jurisdiction.
- **Retention is bounded.** Order, review, and refund records are retained for seven years for
  financial-compliance purposes; buyers.email and buyers.phone are purged within thirty days of a
  verified account-closure request, subject only to open dispute or chargeback holds.
- **External planning is minimized by default.** Any brief prepared for an external frontier model
  must carry the smallest set of fields needed for the task, and must exclude every field in the Data
  classification section above unless this document expressly permits its masked form.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation
boundary.
