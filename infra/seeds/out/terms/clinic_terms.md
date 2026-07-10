# Terms of Sensitive Data Use — Aurora Clinic

Aurora Clinic ("Aurora", "the Clinic") is a covered entity under the Health Insurance Portability and Accountability Act (HIPAA). This policy governs how protected health information (PHI) held in the Clinic's systems is classified, handled, and permitted to leave Clinic infrastructure. It binds all automated and external processing of Clinic data — including planning or analysis performed by a third-party or frontier model — to the HIPAA Privacy and Security Rules and the minimum-necessary standard.

## Data classification

The following fields are designated protected health information and carry the sensitivity class shown.

- **patients.name** — patient full name. Class: PHI (direct identifier).
- **patients.mrn** — medical record number. Class: PHI (direct identifier).
- **patients.dob** — patient date of birth. Class: PHI.
- **patients.phone** — patient telephone number. Class: PHI (direct identifier).
- **patients.address** — patient home address. Class: PHI (direct identifier).
- **encounters.icd10** — encounter diagnosis code. Class: PHI (clinical).
- **encounters.provider** — treating provider name. Class: CONFIDENTIAL.
- **prescriptions.drug** — prescribed medication. Class: PHI (clinical).

## Handling rules

- Medical record numbers in **patients.mrn** are direct identifiers and must never leave Clinic infrastructure in any form.
- Patient names in **patients.name** may appear in external planning materials only in pseudonymized form; the re-identification key remains inside the Clinic.
- Patient contact identifiers in **patients.phone** and **patients.address** must be removed before any external transmission and must never be sent to an external model.
- Patient dates of birth in **patients.dob** must be generalized to year of birth before external transmission; full dates must not leave the Clinic.
- Diagnosis codes in **encounters.icd10** and medications in **prescriptions.drug** may be included in external planning materials only after removal of all direct patient identifiers, consistent with the minimum-necessary standard.
- Any external analysis — duplicate-billing review or data-quality checks on vitals — must operate on a de-identified data set; re-association with patient identity occurs only inside Clinic systems.
- PHI must remain resident on Clinic-controlled infrastructure within the United States; transfer of identifiable PHI outside that boundary is prohibited absent a Business Associate Agreement.
- PHI must be retained for at least six years as required by HIPAA and then securely destroyed.

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
