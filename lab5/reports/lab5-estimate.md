# Lab 5 — Pre-run estimate (review before committing)

Prepared: 2026-10-23T06:21:21.782007+00:00. Student: 6688012. Azure region: centralindia.
This is a proposed short demonstration plan, not measured runtime or actual billing.
No Lab 5 pipeline has been submitted by these preparation tools.

## Price evidence and assumptions

- Source: https://prices.azure.com/api/retail/prices?currencyCode=%27THB%27&%24filter=serviceName+eq+%27Virtual+Machines%27+and+armRegionName+eq+%27centralindia%27+and+armSkuName+eq+%27Standard_DS2_v2%27+and+priceType+eq+%27Consumption%27
- Retrieved: 2026-10-23T06:14:48.151568+00:00; meter ID: `8ff981a1-40b8-4292-aa18-c1af57836008`.
- Linux on-demand `Standard_DS2_v2`: **5.6784 THB/hour**.
- Retail VM reference only; ML service overhead, disks and invoice discounts can differ.
- Dedicated compute is the conservative estimate. Discounted compute must be checked against
  quota/eligibility before use; no discount or Spot availability is assumed here.
- Training cluster: proposed min=0/max=1; at most one active staging instance.
- Planned billable envelope: training 0.5 instance-hour, validation/evaluation/pipeline
  startup/idle allowance 0.5 instance-hour, staging 1 instance-hour. These are planning
  assumptions covering the demonstration attempts, not measurements or enforced timeouts.
- A schedule must be disabled promptly after evidence capture. Additional runs, longer
  provisioning or another VM size require a revised estimate before starting.

## Breakdown

| Component | Planning basis | Estimate / allowance (THB) |
|---|---|---:|
| Training | 0.5 h × 5.6784 | 2.8392 |
| Pipeline / validation / idle | 0.5 h × 5.6784; compute allocation, not a separate pipeline tariff | 2.8392 |
| Serving | 1 h × 5.6784 | 5.6784 |
| Storage | provisional allowance, no verified usage/tariff calculation yet | 2.0000 |
| Monitoring | provisional allowance for short demonstration | 2.0000 |
| Shared registry/other | provisional allocation; avoid counting the entire shared bill twice | 2.0000 |
| Part A subtotal | compute 11.3568 + provisional noncompute 6 | 17.3568 |
| LLM | provisional budget reserve; model/rates/access not yet selected | 10.0000 |
| Second provider | provisional budget reserve; account/service not yet available | 10.0000 |
| Contingency | 20% of the preceding planning subtotal | 7.4714 |
| Proposed Lab 5 planning envelope | not a billing cap or a forecast accuracy guarantee | **44.8282** |

The three noncompute allowances and two future-service reserves are explicit proposals,
not provider quotations or evidence those tasks can be completed at these amounts.
Review/reprice them before using the relevant services. Earlier-lab/shared costs still
consume the course's <800 THB term budget; available headroom has not yet been verified.
The baseline Part A subtotal and reserves must remain separate during reconciliation;
report deviations honestly rather than selecting a subtotal to force a 20% match.

## Pre-run ordering

The user must review and commit this estimate before Task 1. Record that commit SHA in
the later managed-job submission evidence. This preparation step never commits or pushes.
If the scope or assumptions change, preserve the original and commit a dated revision
before executing the changed scope.
