# Northgate Freight — Terms of Sensitive Data Use

**Northgate Freight Ltd.** operates as a licensed freight forwarder and customs broker. In the course
of arranging carriage and clearing goods, we hold commercially sensitive and personal data belonging
to shippers, consignees and their authorised representatives. This document governs how that data is
classified, masked, transmitted and retained, and in particular what may cross Northgate's
infrastructure boundary into any external planning, analytics or model-assisted workflow. It is
issued under our obligations as a registered economic operator under the Union Customs Code and under
applicable data-protection and export-control law.

## Purpose

These terms exist so that trade-compliance analysis, exception review and lane reporting can be
performed on our shipment records without exposing the identifying details of the parties to a
transaction. The controlling principle is data minimisation: a party's identity, fiscal identifiers
and contact details are handled on a strict need-to-know basis and are masked or withheld before any
record leaves company-controlled systems.

## Data classification

The following fields carry elevated sensitivity and are subject to the handling rules below.

- **customs_declarations.consignee_name** — party identity on the customs entry; restricted.
- **customs_declarations.consignee_eori** — customs registration identifier (EORI); restricted, regulated identifier.
- **customs_declarations.consignee_tax_id** — national VAT / tax registration; restricted, regulated identifier.
- **customs_declarations.consignee_email** — consignee contact; personal data.
- **customs_declarations.consignee_phone** — consignee contact; personal data.
- **shipments.consignee_name** — party identity on the movement record; restricted.
- **purchase_orders.shipper_contact** — named individual acting for the shipper; personal data.
- **purchase_orders.shipper_email** — shipper contact; personal data.
- **purchase_orders.shipper_phone** — shipper contact; personal data.
- **purchase_orders.remit_iban** — supplier settlement account number; confidential financial data.

## Handling rules

- Customs and fiscal identifiers in **customs_declarations.consignee_eori** and **customs_declarations.consignee_tax_id** are regulated identifiers and must never leave Northgate infrastructure; they may not appear in any external planning brief.
- Party names in **customs_declarations.consignee_name** and **shipments.consignee_name** may appear in external planning materials only in pseudonymised form; the underlying name must be withheld or replaced with a stable reference token.
- Settlement account numbers in **purchase_orders.remit_iban** must be masked to the last four characters before any external transmission; the full account number is never disclosed outside the finance function.
- Contact details in **customs_declarations.consignee_email**, **customs_declarations.consignee_phone**, **purchase_orders.shipper_email** and **purchase_orders.shipper_phone** are personal data and must be redacted from any dataset shared with an external processor unless a lawful basis and a data-processing agreement are in place.
- Named shipper representatives in **purchase_orders.shipper_contact** must be minimised: external planning references a role or reference token, never the individual's name.
- Denied-party and sanctions screening against **customs_declarations.consignee_name** must be carried out inside Northgate's environment; consignee identity may be sent to an external screening provider only under contract and only for that purpose.
- The personal and fiscal data described above must be processed and stored within the EU/EEA; onward transfer to a third country requires an approved transfer mechanism.
- Records carrying the identifiers and contact details above are retained no longer than required for customs and audit obligations and are then deleted or irreversibly anonymised.
- Any external analytics or model-assisted review must operate only on records from which the restricted identifiers have been removed or masked in accordance with the rules above.

## Note

This corpus is fully synthetic demo data; these terms exercise the platform's policy-distillation boundary.
