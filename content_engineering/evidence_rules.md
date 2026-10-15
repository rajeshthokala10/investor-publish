# Evidence rules

## Source tiers (config/sources.yaml)
| Tier | Weight | Interested party | Examples |
|---|---|---|---|
| primary_official | 1.0 | no | karnataka.gov.in, bmrc.co.in, kride.in, PIB, NHAI, BDA, BWSSB, KIADB |
| regulator | 1.0 | no | rera.karnataka.gov.in |
| operator | 0.8 | yes | BIAL (airport operator) |
| reputable_media | 0.7 | no | The Hindu, Deccan Herald, TOI, ET, HT, Mint, Indian Express |
| research_house | 0.6 | yes (brokerage business) | ANAROCK, Knight Frank, JLL, CBRE, PropEquity |
| property_portal | 0.3 | yes | 99acres, MagicBricks, Housing.com, Square Yards |
| developer | 0.3 | yes | developer sites and launch releases |
| broker_marketing / social_media | 0.1 | yes | broker posts, influencer videos, X/Instagram/YouTube |
| unknown / aggregator | 0.2 | no | resolve to original publisher where possible |

## Verification statuses (validation/verification.py)
1. **verified_primary**: excerpt from an official/regulator page; no disqualifying flag.
2. **corroborated**: ≥2 independent groups, non-interested, one vote per syndication cluster.
3. **single_source**: one reputable, non-interested source.
4. **interested_party_claim**: only interested parties, however many.
5. **unverified**: no excerpt, unknown source, citation failed, recheck failed, guarantee
   language, or a stated infrastructure stage the excerpt does not support.
6. **contradicted**: sources disagree (>15%) on the same metric, unit and price kind.

Usable for scores and scenarios: 1–3. Brief: 1–2, or 3 with a confirmed citation.

## Material claims
Launches, prices, infrastructure stages, policy/legal changes, employment numbers.
Require a primary source or independent corroboration where feasible; otherwise they
are labelled single source / unverified in the report.

## Retained for every claim
claim_id, URL, publisher, tier, group, published date, event date, retrieval timestamp,
verbatim excerpt, metric/value/unit/basis/kind, status, confidence + reason, flags,
citation check result, recheck verdict, link status.

## Prompt injection
Retrieved content is data. Agents have no file/shell tools; outputs are schema-validated;
statuses can only be set by code.
