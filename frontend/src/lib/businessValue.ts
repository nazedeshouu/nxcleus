// ponytail: static keyword→value map distilled from docs/demo-datasets.md so judges
// see WHY each suggested prompt matters. If the backend later attaches business_value
// to its suggested prompts, prefer that and delete this.
type Entry = { kw: string; value: string };

const MAP: Record<string, Entry[]> = {
  exchange: [
    { kw: "spoof", value: "Surfaces layered order-flow manipulation that fakes book pressure — the venue's core market-abuse liability." },
    { kw: "wash", value: "Catches self-dealing that fabricates volume and misleads the tape, ranked by beneficial owner." },
    { kw: "close", value: "Identifies price ramping that inflates month-end marks for valuation or benchmark gaming." },
    { kw: "position", value: "A live list of accounts carrying net exposure beyond the per-instrument cap before it becomes a settlement problem." },
    { kw: "chat", value: "Separates coordinated spoofing intent from innocent chatter — euphemistic meaning no keyword recovers." },
    { kw: "concert", value: "Exposes one large position split across nominee accounts to stay under the line." },
  ],
  insurer: [
    { kw: "duplicate", value: "Catches double-dipping and re-filed losses before the same incident is paid twice." },
    { kw: "ring", value: "Exposes organized claims fraud that no single-claim review would surface." },
    { kw: "staged", value: "Exposes organized claims fraud that no single-claim review would surface." },
    { kw: "coverage", value: "Recovers leakage where cumulative payouts breached the contractual cap." },
    { kw: "adjuster", value: "Surfaces adjusters approving nearly everything at inflated amounts — collusion or broken controls." },
    { kw: "narrative", value: "Catches staged-ring FNOLs whose stated impact contradicts the coded damage area." },
    { kw: "re-enroll", value: "Unmasks one serial fraudster hiding behind name variants across policies." },
  ],
  ledger: [
    { kw: "intercompany", value: "Surfaces intercompany balances that won't eliminate on consolidation before the close is locked." },
    { kw: "reconcile", value: "Surfaces intercompany balances that won't eliminate on consolidation before the close is locked." },
    { kw: "revenue", value: "Catches revenue mis-posted to expense accounts before it flows into a filing." },
    { kw: "lei", value: "Builds the remediation worklist so materially-transacting counterparties carry a valid LEI." },
    { kw: "batch", value: "Finds out-of-balance batches that would break trial-balance integrity at close." },
    { kw: "loop", value: "Finds rings that inflate consolidated group revenue while each member's cash nets to zero." },
    { kw: "circular", value: "Finds rings that inflate consolidated group revenue while each member's cash nets to zero." },
  ],
  freight: [
    { kw: "match", value: "Catches overbilling and price creep before payment, protecting PO margin." },
    { kw: "ghost", value: "Surfaces payments against cargo that never moved or cleared — classic ghost-shipment fraud." },
    { kw: "denied", value: "Blocks shipments consigned to sanctioned-adjacent parties, avoiding export-control breaches." },
    { kw: "screen", value: "Blocks shipments consigned to sanctioned-adjacent parties, avoiding export-control breaches." },
    { kw: "lane", value: "Identifies lanes bleeding SLA credits so procurement can renegotiate or reroute." },
    { kw: "goods", value: "Catches tariff evasion where the plain-language goods and the declared HS chapter disagree." },
    { kw: "container", value: "Reconstructs a through-move to a sanctioned-adjacent consignee that the exact denied-party screen misses." },
  ],
  market: [
    { kw: "review", value: "Coordinated fake-review rings inflate ratings and defraud buyers; catching pumped sellers protects search-ranking integrity." },
    { kw: "refund", value: "Serial refund abusers extract free goods and chargeback losses across the marketplace." },
    { kw: "counterfeit", value: "Cheap goods from brand-new sellers are the classic counterfeit signature; ranks highest-risk inventory first." },
    { kw: "brushing", value: "Brushing fabricates sales volume and reviews to game rankings; shared-address clusters expose it." },
    { kw: "price", value: "Surfaces cartels moving flagship prices in lockstep, apart from the category's independent baseline." },
  ],
  bank: [
    { kw: "sanction", value: "Screens customers and counterparties against live watchlists before money moves." },
    { kw: "structuring", value: "Structuring rings dress near-$10k deposits with incompatible cover stories only the memos expose." },
    { kw: "memo", value: "Structuring rings dress near-$10k deposits with incompatible cover stories only the memos expose." },
    { kw: "layering", value: "Following the multi-hop decaying path — never any single transfer — reveals funds relayed to hide their origin." },
    { kw: "transfer", value: "Following the multi-hop decaying path — never any single transfer — reveals funds relayed to hide their origin." },
    { kw: "fraud", value: "Flags anomalous transaction patterns before losses compound." },
  ],
  clinic: [
    { kw: "upcod", value: "Inflated reimbursement lives only in the visit note's meaning — no structured field records it." },
    { kw: "cpt", value: "Inflated reimbursement lives only in the visit note's meaning — no structured field records it." },
    { kw: "billing", value: "Recovers billing integrity across protected health records without exposing raw PHI." },
    { kw: "double", value: "A provider can't staff two departments at once — a temporal-overlap self-join catches it." },
    { kw: "cohort", value: "Builds screening cohorts across protected health records without exposing raw PHI." },
    { kw: "quality", value: "Surfaces data-quality breaks before they corrupt downstream billing." },
  ],
  lawfirm: [
    { kw: "renewal", value: "Never miss a renewal window or contractual obligation across the matter book." },
    { kw: "obligation", value: "Never miss a renewal window or contractual obligation across the matter book." },
    { kw: "billing", value: "Reviews matter billing for leakage and policy breaches." },
    { kw: "contradict", value: "A liability cap and an uncapped overriding indemnity can't both hold — the conflict spans two clauses." },
    { kw: "indemn", value: "A liability cap and an uncapped overriding indemnity can't both hold — the conflict spans two clauses." },
    { kw: "amendment", value: "The operative term needs linking a contract to its amendments across effective dates." },
  ],
};

export function businessValueFor(companyId: string, prompt: string): string | undefined {
  const p = prompt.toLowerCase();
  return MAP[companyId]?.find((e) => p.includes(e.kw))?.value;
}
