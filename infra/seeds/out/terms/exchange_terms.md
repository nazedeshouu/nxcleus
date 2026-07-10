# Ashford Mercantile Exchange — Terms of Sensitive Data Use

Ashford Mercantile Exchange ("Ashford", "the Exchange") operates a regulated multi-asset trading venue. This document sets out the mandatory controls governing sensitive data held in the Exchange's account and surveillance systems. Its purpose is to protect **account-owner identity** and the confidentiality of pre-trade and in-flight **order flow**, and to ensure that no material non-public information (MNPI) or personally identifying account data is disclosed outside Exchange-controlled infrastructure without the masking and authorization that market-abuse regulation requires.

The Exchange is subject to market-abuse and market-conduct obligations (MAR-equivalent and CFTC/Dodd-Frank supervisory regimes). Account-owner identifiers, contact details, settlement instructions, and un-anonymized order and execution flow are all regulated sensitive data. Any external processing — including automated planning, drafting, or model-assisted analysis — must operate on masked or pseudonymized inputs unless a documented, residency-bound exception applies.

## Data classification

The following fields are classified sensitive and are subject to the handling rules below.

- **accounts.owner_name** — Legal name of the account owner. Class: Confidential — personal identifier.
- **accounts.owner_tax_id** — National tax / identification number of the beneficial owner. Class: Restricted — national identifier.
- **accounts.contact_email** — Owner contact email. Class: Confidential — personal contact.
- **accounts.contact_phone** — Owner contact telephone number. Class: Confidential — personal contact.
- **accounts.settlement_iban** — Settlement account number (IBAN) for the trading account. Class: Restricted — financial account number.
- **accounts.firm** — Clearing / introducing firm affiliation. Class: Internal — commercially sensitive.
- **orders.account_id** — Links order flow to an identified account owner. Class: Restricted when joined to owner identity — MNPI / order-flow confidentiality.
- **orders.price**, **orders.qty**, **orders.ts** — Terms and timing of a working order. Class: Confidential — order-flow / MNPI while the order is live.

## Handling rules

- Account-owner national identifiers in **accounts.owner_tax_id** must never leave Exchange infrastructure, in whole or in part, and must not appear in any external planning brief, prompt, or model context.
- Settlement account numbers in **accounts.settlement_iban** must be masked to the last four characters before any external transmission; the full IBAN may be processed only inside Exchange-controlled systems.
- Owner contact details in **accounts.contact_email** and **accounts.contact_phone** must be redacted from any material shared with an external processor; where a contact reference is unavoidable it must be pseudonymized.
- Account-owner names in **accounts.owner_name** may appear in external surveillance or planning materials only in pseudonymized form (for example a stable owner token), never as the cleartext legal name.
- Order-flow terms in **orders.price**, **orders.qty** and **orders.ts** for any working or unexecuted order constitute material non-public information and must not be transmitted outside the Exchange until the order is filled, cancelled, or otherwise public.
- Any linkage of **orders.account_id** to account-owner identity is MNPI and must be broken — owner fields dropped or tokenized — before order or execution data is sent to an external model.
- All sensitive fields in the **accounts** table must remain resident on Exchange-controlled infrastructure within the venue's home jurisdiction; cross-border replication of owner identity or settlement data is prohibited without a documented residency exception.
- Sensitive account-owner and order-flow records must be retained only for the statutory market-abuse record-keeping period and then securely destroyed; no external copy may be retained beyond the life of the specific authorized task.
- Surveillance findings derived from sensitive data (spoofing, wash-trade, marking-the-close and position-limit results) must reference accounts by pseudonymized owner token, not by **accounts.owner_name** or **accounts.owner_tax_id**, when shared outside the surveillance team.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
