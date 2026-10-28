# MTA Accountability Tracker — sitewide audit and revision

## Changes made
- research-methodology.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- index.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- child-safety.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- education-impact.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- Community: removed four duplicate reporting-method sections; linked to their canonical pages.
- community-impact.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- data-dashboard.html: standardized navigation, checked cross-links, added page-specific purpose statement.
- service-accountability.html: standardized navigation, checked cross-links, added page-specific purpose statement.

## Verified issues in supplied repository
- `docs/dashboard.js` was referenced by the dashboard but missing from the uploaded repository. Added a minimal replacement for local browser-only incident reports; static route counts remain unavailable because no GTFS route summary was included.
- The Education page's Research link went to the homepage rather than Research & Methods.
- The homepage's primary research link led to Service Accountability instead of the research page; now its primary action leads to the working Data Dashboard.
- The Education page's Project dashboard link went to the homepage; now it goes to Data Dashboard.
- Seven pages used different navigation menus and page names; all now share one navigation menu.
- Community repeated reporting-gap, research-design, legal-caution, and vehicle-number sections from Service; these were consolidated into links to the canonical sections.
- Research language implied monitoring was still only being developed; now acknowledges active collection without claiming verified reliability rates.

## Deployment
Upload the `docs/*.html` files and `docs/dashboard.js` to their corresponding GitHub paths, preserving other existing files. The full ZIP also contains your current scripts and data for completeness.

## Important limitations
- The repository contains public Supabase publishable configuration. It was preserved unchanged; do not place service-role or secret keys in `docs`.
- This revision was checked against the uploaded repository, not deployed or browser-tested on the live GitHub Pages site.
- Static route totals cannot be restored without a route-summary data file.
- The 7-day GitHub snapshots and Supabase history have different scopes; they are labeled separately.
- This revision does not alter GitHub Actions, the Supabase database, or the collection algorithm.
