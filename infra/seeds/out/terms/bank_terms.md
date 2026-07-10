# Terms of Sensitive Data Use — Meridian Bank

Meridian Bank, N.A. ("Meridian", "the Bank") maintains this policy to govern how customer nonpublic personal information and Bank Secrecy Act records are classified, handled, and permitted to leave Bank infrastructure. It gives effect to the Bank's obligations under the Gramm-Leach-Bliley Act (GLBA) Safeguards Rule, the Bank Secrecy Act, and its anti-money-laundering (BSA/AML) program. Any automated or external processing of Bank data — including planning or analysis performed by a third-party or frontier model — is bound by these terms.

## Data classification

The following fields in the Bank's customer and account systems are designated sensitive and carry the sensitivity class shown.

- **customers.national_id** — customer government identifier (SSN / national ID). Class: RESTRICTED.
- **customers.name** — customer legal name. Class: CONFIDENTIAL.
- **customers.dob** — customer date of birth. Class: CONFIDENTIAL.
- **customers.email** — customer contact email. Class: CONFIDENTIAL.
- **customers.phone** — customer contact telephone number. Class: CONFIDENTIAL.
- **accounts.account_number** — deposit account number. Class: RESTRICTED.
- **accounts.iban** — international bank account number. Class: RESTRICTED.
- **accounts.balance_usd** — account balance. Class: CONFIDENTIAL.
- **transactions.counterparty** — transaction counterparty name. Class: CONFIDENTIAL.

## Handling rules

- Customer national identifiers in **customers.national_id** must never leave Meridian infrastructure in any form, masked or unmasked, and must never appear in materials sent to an external model.
- Deposit account numbers in **accounts.account_number** and **accounts.iban** must be masked to the last four digits before any external transmission.
- Customer names in **customers.name** may appear in external planning materials only in pseudonymized form; the mapping from pseudonym to real identity remains inside the Bank.
- Customer contact details in **customers.email** and **customers.phone** must be masked before external transmission; an email domain may be retained but its local-part must not.
- Account balances in **accounts.balance_usd** must be banded or aggregated before inclusion in any external planning brief; individual balances must not be transmitted.
- Counterparty names in **transactions.counterparty** must be pseudonymized before external transmission, except where a name is screened against a lawful sanctions list.
- All records governed by the Bank Secrecy Act, including customer identity and transaction detail, must remain resident on Bank-controlled infrastructure within the United States; cross-border transfer of BSA records is prohibited.
- Suspicious-activity analysis — structuring and dormant-account reactivation review — must run on de-identified data only; customer identity is re-associated exclusively inside Bank systems.
- Sensitive customer and account records must be retained for at least five years per BSA recordkeeping requirements and then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
