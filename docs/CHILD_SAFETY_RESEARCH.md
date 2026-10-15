[CHILD_SAFETY_RESEARCH.md](https://github.com/user-attachments/files/33508357/CHILD_SAFETY_RESEARCH.md)
# Child safety and transit exposure research protocol

## Research question
Does unreliable scheduled bus service increase the time minors spend waiting or traveling by an unplanned route, and are any independently documented victimization incidents causally associated with particular transit disruptions?

## Evidence tiers
1. **Observed transit disruption:** timestamped official GTFS/GTFS-RT snapshots or corroborated stop-level observations. Missing GPS is not proof of no-show.
2. **Reported child exposure:** voluntary, confidential guardian report of additional wait or walking time; distinguish reported from independently corroborated.
3. **Official victimization data:** published agency statistics or deidentified incidents, retaining exact reporting definition, reporting period, geography and source version.
4. **Case-specific causal finding:** only after documented evidence of the route/stop, scheduled service failure, victim circumstances, temporal relationship, and plausible counterfactual; legal review required.

## Critical distinctions
- Missing-child reports are not equivalent to stranger abductions; trafficking is not equivalent to kidnapping. Runaways and repeated reports can appear in missing-person data.
- A crime occurring near a bus stop does not establish that the victim was waiting for a bus, was a child, or that MTA caused the incident.
- Public datasets may lack victim age, incident time, trip purpose, or precise location; leave unknowns blank. Never impute.
- Do not publish minors' names, precise routines, school-to-home trajectories, exact stop-level child incident details, or personally identifying narratives.
- Public charts should aggregate to broad geography and time bins and suppress small counts (suggested <5). Restricted case data must be encrypted, access-controlled, and separately stored.
- No automated public allegation of kidnapping, trafficking, or preventability based on a time/location match.

## Analytical design
Calculate excess waiting minutes from verified stop-level observations. Compare time windows (e.g. 6–9 AM, 2–6 PM), service days, routes, and neighborhood areas. Report denominators: scheduled trips, observed trips, reported children affected, and missing-data rates. For victimization, analyze separate offense categories, source-specific age criteria, counts and rates; use multi-year trends and sensitivity analyses. Correlation cannot demonstrate causation. A counterfactual claim requires individual case evidence and examination of other causes.

## Public records research
Request deidentified Baltimore City child missing-person/abduction incidents by incident date, hour, general geography, age band, offense classification, and case disposition; ask explicitly whether circumstances involved waiting at transit stops or walking from school. Expect suppression or denial of protected juvenile records. Request school-transportation complaints, MTA missed-trip reports, and stop pass-by complaints separately. Preserve agency response, request text, and any disclosure limitations.

## Sources to evaluate
- Baltimore Police open data (NIBRS Group A crime data, from 2022; changed reporting standards 2025): https://www.baltimorepolice.org/crime-stats/open-data
- Maryland State Police Missing Children Clearinghouse statutory reporting: https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gfl&section=9-403
- Maryland Department of Human Services child sex trafficking reports: https://msa.maryland.gov/msa/mdmanual/18dhr/html/dhrr.html
- Governor's Office of Crime Prevention and Policy publications: https://gocpp.maryland.gov/reports-and-publications/
- National Center for Missing & Exploited Children research: https://us.missingkids.org/ourwork/ncmecdata

No source currently establishes a citywide count of children kidnapped *while walking home because a bus failed to arrive*. Treat this as an unanswered research question, not a measured statistic.
