# Terms of Sensitive Data Use — Hale & Ostrom LLP

Hale & Ostrom LLP ("the Firm") holds client information subject to the attorney-client privilege, the work-product doctrine, and the Firm's professional duty of confidentiality. This policy governs how privileged and confidential client data is classified, handled, and permitted to leave Firm infrastructure, and it binds all automated and external processing — including planning or analysis performed by a third-party or frontier model.

## Data classification

The following fields carry the sensitivity class shown.

- **parties.name** — client and counterparty legal name. Class: CONFIDENTIAL.
- **parties.tax_id** — client tax identifier (SSN / EIN). Class: RESTRICTED.
- **parties.contact** — client contact email. Class: CONFIDENTIAL.
- **parties.phone** — client telephone number. Class: CONFIDENTIAL.
- **contracts.matter_number** — internal matter identifier. Class: PRIVILEGED.
- **contracts.privilege** — privilege classification of the record. Class: CONTROL.
- **billing_entries.narrative** — timekeeper work description. Class: PRIVILEGED.
- **billing_entries.timekeeper** — attorney or timekeeper name. Class: CONFIDENTIAL.

## Handling rules

- Billing narratives in **billing_entries.narrative** are attorney-client privileged work product and must never leave Firm infrastructure or appear in materials sent to an external model, masked or unmasked.
- Matter identifiers in **contracts.matter_number** must never leave Firm infrastructure; external planning materials must reference a matter only by an opaque handle assigned inside the Firm.
- Client tax identifiers in **parties.tax_id** are restricted and must never be transmitted externally in any form.
- Client and counterparty names in **parties.name** may appear in external planning materials only in pseudonymized form; the mapping to real identity remains inside the Firm.
- Client contact details in **parties.contact** and **parties.phone** must be masked before any external transmission.
- Any record whose **contracts.privilege** classification is "attorney-client" or "work-product" must be excluded from external transmission unless privilege has been expressly waived in writing by the client.
- Timekeeper identities in **billing_entries.timekeeper** must be pseudonymized before external transmission.
- Contract review, renewal-window analysis, and fee-cap auditing may be performed on de-identified extracts only; privileged narrative content is never included in an external brief.
- Privileged and confidential client records must remain resident on Firm-controlled infrastructure and be retained per the Firm's records-retention schedule, then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
