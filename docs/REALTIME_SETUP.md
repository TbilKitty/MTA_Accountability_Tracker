# Real-time feed activation

Official MTA page: https://www.mta.maryland.gov/developer-resources
Official local-bus static feed: https://feeds.mta.maryland.gov/gtfs/local-bus
Official all-mode alerts: https://feeds.mta.maryland.gov/alerts.pb
MTA says local-bus GTFS-RT vehicle positions and trip updates are delivered through Swiftly, agencyKey `mta-maryland`, with API access keys. Request a key and review the current Swiftly API documentation and permitted use terms. Do not assume an endpoint path, authentication header, retention license, or posting permission.

`src/realtime.py` is an intentionally disabled adapter until those details are confirmed. After authentication is implemented, archive full raw response bytes with metadata, poll no more often than permitted, validate feed timestamps and GTFS trip matching, and log failures. Test in a private repository before any public alerts.

Immediate rider-facing alternative: https://www.mta.maryland.gov/transit and the MTA real-time arrivals selector at https://www.mta.maryland.gov/home . Text a stop ID to MTAMD (68263), according to MTA instructions. Third-party consumer displays are not a substitute for preserved authenticated data.
