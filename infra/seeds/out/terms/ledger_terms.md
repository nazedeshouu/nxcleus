# Aldgate Holdings plc — Terms of Sensitive Data Use

## Purpose

Aldgate Holdings plc operates the group general ledger and consolidation systems for its twenty
subsidiaries. As a dual-listed group, Aldgate is subject to Sarbanes-Oxley section 302 and 404
attestation, market-abuse controls over material non-public financial information, and counterparty
data-protection obligations. These Terms govern how the sensitive fields held in the group ledger
may be processed, and in particular what may be distilled into any brief transmitted to an external
planning model outside Aldgate infrastructure.

## Data classification

The following fields carry a sensitivity class. External-transmission rules in the next section are
keyed to these classes.

- **counterparties.tax_id** — Restricted. Counterparty national tax identifier.
- **counterparties.iban** — Restricted. Counterparty settlement bank account number.
- **counterparties.vat_no** — Confidential. Counterparty VAT registration number.
- **counterparties.contact_email** — Confidential. Counterparty finance-contact personal email.
- **counterparties.lei** — Public. ISO 17442 Legal Entity Identifier.
- **counterparties.name**, **counterparties.country** — Internal. Counterparty master reference.
- **entities.officer_name**, **entities.officer_email** — Confidential. Subsidiary attestation signatory identity.
- **entities.name**, **entities.country**, **entities.currency** — Internal. Subsidiary reference data.
- **gl_entries.memo** — Confidential. Journal narrative that may embed counterparty identifiers.
- **gl_entries.amount** — Restricted before filing. Material non-public financial data.
- **chart_of_accounts.code**, **chart_of_accounts.class** — Internal. Ledger structure.

## Handling rules

- Counterparty national tax identifiers (**counterparties.tax_id**) must never leave Aldgate
  infrastructure and must be fully masked before any brief is sent to an external planning model.
- Counterparty bank account numbers (**counterparties.iban**) must be masked to the last four
  characters before any external transmission.
- Counterparty VAT registration numbers (**counterparties.vat_no**) may not appear in materials
  transmitted outside the group finance perimeter.
- Counterparty finance-contact email addresses (**counterparties.contact_email**) must be redacted
  before external transmission and must never be paired externally with the counterparty legal name.
- Subsidiary attestation officer identities (**entities.officer_name**, **entities.officer_email**)
  may appear in external planning materials only in pseudonymized form.
- Journal narrative memos (**gl_entries.memo**) frequently embed counterparty names, invoice numbers
  and account details; any such identifier in a memo must be masked before external transmission.
- Pre-close ledger amounts (**gl_entries.amount**) aggregated by subsidiary (**gl_entries.entity_id**)
  constitute material non-public information and must not be transmitted outside Aldgate infrastructure
  before the corresponding results are publicly filed.
- Legal Entity Identifiers (**counterparties.lei**) are public reference data and may be transmitted,
  but must never be transmitted alongside the same counterparty's **counterparties.tax_id** or
  **counterparties.iban**.
- Records for subsidiaries domiciled in the European Union (**entities.country** of DE or FR) and their
  related counterparty data must be processed only within EU/EEA infrastructure.
- Counterparty identifiers (**counterparties.tax_id**, **counterparties.iban**, **counterparties.vat_no**)
  are retained no longer than seven years after the last related entry in **gl_entries**, then destroyed.

## Closing note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation
boundary.
