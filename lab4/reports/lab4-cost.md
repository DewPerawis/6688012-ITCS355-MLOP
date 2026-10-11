# Lab 4 cloud cost evidence — execution recorded; billing pending

The student deployed the serving endpoint and ran dedicated monitoring compute in Central India.
Teardown verified removal of the endpoint, schedule and monitor compute at
2026-10-11T23:01:17.708420Z. Partial retail references are reported below;
no final Lab 4 billed total is claimed.
Use current Azure prices and Cost Management to reconcile actual charges.

Serving: Standard_DS2_v2, one instance. Deployment started at 2026-10-11T21:20:50.101031Z;
completed at 21:30:47.243587Z. Using verified teardown time as the interval end gives
100.460123 minutes from deployment start, or 90.507747 minutes from deployment completion.
These are elapsed-time proxies, not exact metered VM runtime: allocation and deletion occur
within the deployment/cleanup operations. Monitoring: Standard_DS1_v2, min 0/max 1;
successful and failed jobs both may incur charges. Do not count only successful job durations.

| Item | Evidence to capture | Current state |
|---|---|---|
| Serving instance and count | staging-04aedd4/lab4-deployment.json | Standard_DS2_v2; one instance |
| Serving active interval | Deployment/create and verified delete UTC timestamps | Measured elapsed-time proxies above; exact metered runtime pending |
| Monitoring instance | monitor-compute.json and actual job records | Standard_DS1_v2; min 0/max 1; billing runtime pending |
| Schedule lifetime | drift-schedule.json and schedule-disabled.json | Latest schedule enabled 22:36:38Z, disabled 22:47:48Z; actual scheduled runs captured |
| Price basis | Current SKU, region, currency, retrieved-at time and source | retail-prices.json; collected after execution |
| Estimated compute cost | Verified active hours × current unit price; include assumptions | Not measured |
| Logs/storage/registry | Actual consumption and billing contribution | Not measured |
| Actual billed cost | Azure Cost Management export or screenshot and billing date | Shared-resource snapshot captured; recent compute charges not posted |
| Difference | Estimate versus billed amount; discuss billing lag and omitted services | Not available yet |

Credit consumption counts as cost for the course budget. Keep the total semester below
the handout's 800 THB limit and preserve the resources needed by later labs.

## Current public price references

Retrieved from the [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
on 12 October 2026, Thailand time. Region: Central India; Linux, regular Consumption,
unit: 1 Hour. The complete source response and query URLs are in `retail-prices.json`.

| SKU | Public retail USD/hour | Evidence status |
|---|---:|---|
| Standard_DS2_v2 | 0.169 | One matching non-Windows, non-Spot Consumption price |
| Standard_DS1_v2 | 0.084 | One matching non-Windows, non-Spot Consumption price |

Applying the serving price to the elapsed-time proxies gives approximately USD 0.255
from deployment completion, or USD 0.283 from deployment start. These are VM retail
references, not lower/upper billing bounds. Monitor billable VM hours were not measured,
so a total compute amount is not claimed. See `cost-estimate.json` for exact arithmetic.
These price references were collected after execution, not committed before running.

## Posted billing observation

The read-only [Cost Management query](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01)
for this resource group and UTC usage dates 11–12 October 2026 returned three rows:

| Resource | Posted pretax USD |
|---|---:|
| Shared ACR itcs3556688012 | 0.1110675552 |
| Shared Key Vault itcs3556keyvault63d2a327 | 0.000003 |
| Shared Storage itcs3556688012 | 0.00000044 |
| Resource-group posted total | 0.1110709952 |

There were no endpoint or monitor compute charge rows in this snapshot. This is not
evidence that compute was free: the group includes earlier-lab shared resources and the
recent compute usage may not be posted yet. Final Lab 4 billing, THB conversion and
estimate-to-actual reconciliation remain pending. Do not label the group total as the
Lab 4 bill or claim the semester budget has been proven from this snapshot.
