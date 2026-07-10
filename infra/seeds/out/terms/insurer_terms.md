# Cascadia Mutual — Terms of Sensitive Data Use

Cascadia Mutual is a policyholder-owned property and casualty carrier writing auto, home, and
commercial lines across Washington and Oregon. As a mutual, our first duty runs to our members. This
document states how policyholder and claimant information held in our claims and policy systems is
classified and handled whenever any part of it is prepared for processing outside Cascadia Mutual
infrastructure. It gives effect to our obligations under the state insurance codes (RCW Title 48 and
the parallel Oregon Insurance Code), the NAIC Insurance Data Security Model Law, the Gramm-Leach-Bliley
Act safeguards for nonpublic personal financial information, and the health-adjacent protections that
attach to bodily-injury data in a claims file. **Sensitive fields must never cross the external
boundary in a form that identifies, or helps re-identify, a member or claimant.**

## Data classification

- **policies.holder_name** — Policyholder identity. Nonpublic personal information (**Confidential**).
- **policies.policyholder_national_id** — Member national identifier / SSN. Government identifier (**Restricted**).
- **policies.policyholder_email** — Member contact email. Nonpublic personal information (**Confidential**).
- **policies.policyholder_address** — Member residential address. Nonpublic personal information (**Confidential**).
- **policies.premium_bank_account** — Premium-draft bank account number. Financial account data under GLBA (**Restricted**).
- **claims.claimant_phone** — Claimant contact telephone. Nonpublic personal information (**Confidential**).
- **claims.injury_code** — Bodily-injury diagnosis code on the claim. Health-adjacent data (**Restricted**).
- **adjusters.name** — Adjuster identity. Internal personnel data (**Internal**).
- **repair_shops.phone** — Repair-shop business contact. Business contact data (**Internal**).

## Handling rules

- Member national identifiers in **policies.policyholder_national_id** must never leave Cascadia Mutual infrastructure, in whole or in part, under any circumstance.
- Bank account numbers in **policies.premium_bank_account** must be masked to their last four digits before any external transmission; the full number is never exported.
- Bodily-injury codes in **claims.injury_code** are health-adjacent and may appear in external planning materials only in pseudonymized form, generalized to injury category rather than the specific diagnosis code.
- Claimant telephone numbers in **claims.claimant_phone** must be masked before external transmission; at most the area code may be retained for staged-ring pattern analysis.
- Policyholder email addresses in **policies.policyholder_email** may appear externally as the domain portion only, never the full mailbox.
- Policyholder residential addresses in **policies.policyholder_address** may be generalized to city and state for external planning; street lines must be dropped.
- Policyholder names in **policies.holder_name** and adjuster names in **adjusters.name** may appear in external planning briefs only in pseudonymized form.
- All records containing the fields above must remain resident on infrastructure located within the United States; no sensitive claims or policy data may be stored or processed in another jurisdiction.
- Claim files carrying **claims.injury_code** and **claims.claimant_phone** are retained no longer than seven years after claim closure, after which the sensitive fields are irreversibly purged.
- No combination of masked or generalized fields may be transmitted externally if, taken together, they would re-identify a member or claimant.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
