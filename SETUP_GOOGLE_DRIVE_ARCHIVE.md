# Setting up the Google Drive archive

The tracker saves every raw MTA feed file it downloads into your Google Drive, in
a folder called **MTA Tracker Archive**, with a SHA-256 fingerprint for each file.
This takes about 30 minutes, once, on your Mac.

**What the tracker can touch in your Drive:** only files it created itself
(Google's `drive.file` permission). It can't see, open, change or delete anything
else, including your photography files.

---

## Part 1: Google Cloud (web browser)

1. Go to **console.cloud.google.com** and sign in with the Google account that
   has your 5 TB of Drive storage.
2. In the project picker at the top left, select your project (or create one
   named `MTA Tracker Archive`).
3. Search the top bar for **Google Drive API**, open it, and click **Enable**.
4. Search for **Google Auth Platform** (some accounts call it **OAuth consent
   screen**) and click **Get started**:
   - App name: `MTA Tracker Archive`
   - User support email: your email
   - Audience: **External**
   - Contact email: your email
   - Agree, then click **Create**.
5. **Branding page:** fill in only the required fields (app name, support email,
   developer contact email). **Don't upload a logo**, because that triggers a
   Google review. Leave the app domain, privacy policy and authorized domains
   blank. Click **Save**.
6. **Publish the app:** in the left menu, open **Audience**, click **Publish
   app** and confirm. It should say **In production**.
   *If you skip this, Google cuts the connection every 7 days and uploads stop
   without anyone noticing.*
7. In the left menu, open **Clients**, click **Create client**, choose **Desktop
   app**, name it `rclone`, and click **Create**. Copy the **Client ID** and
   **Client secret** into a note on your Mac. Treat them like a password.

## Part 2: rclone on your Mac (Terminal)

1. Install rclone. With Homebrew: `brew install rclone`. Without it, download the
   macOS zip from **rclone.org/downloads**, unzip it, open Terminal in that
   folder, run `xattr -d com.apple.quarantine rclone`, and type `./rclone`
   instead of `rclone` in the steps below.
2. Run `rclone config` and answer:

   | rclone asks | You answer |
   |---|---|
   | New remote / quit? | `n` |
   | name | `gdrive` (exactly this; the tracker looks for it) |
   | Storage | `drive` (Google Drive) |
   | client_id | paste your Client ID |
   | client_secret | paste your Client secret |
   | scope | the option for **drive.file** ("files created by rclone only") |
   | service_account_file | press Enter |
   | Edit advanced config? | `n` |
   | Use web browser to automatically authenticate? | `y` |

   A browser opens. Sign in with the same Google account and click **Allow**. If
   Google says the app isn't verified, click **Advanced**, then **Go to MTA
   Tracker Archive**. That's expected for an app only you use.

   | rclone asks | You answer |
   |---|---|
   | Configure this as a Shared Drive? | `n` |
   | Keep this "gdrive" remote? | `y` |
   | (menu) | `q` |

3. Quick check: `rclone mkdir "gdrive:MTA Tracker Archive"` then
   `rclone lsd gdrive:`. You should see `MTA Tracker Archive`, and it appears in
   Drive in your browser. rclone can only see folders it made, so it won't use a
   folder you created by hand. You can delete that one.
4. Run `rclone config show gdrive` and copy **everything** it prints, starting
   with the `[gdrive]` line.

## Part 3: GitHub

1. In this repo, open **Settings → Secrets and variables → Actions → New
   repository secret**. Name: `RCLONE_CONF`. Secret: paste what you copied.
   Click **Add secret**.
2. Open **Actions → School commute service watch → Run workflow**, check **Only
   test the Google Drive connection**, and click **Run workflow**. A green check
   plus `MTA Tracker Archive/_connection-test/connection-test.txt` in your Drive
   means everything works.

---

## What lands in Drive

```
MTA Tracker Archive/
  2026/11/2026-11-05-am.tar.gz        every raw feed file from that commute window,
                                       plus the MTA schedule used
  2026/11/2026-11-05-am.manifest.csv  each file's capture time and SHA-256 fingerprint
  realtime/2026/11/05/...             the 15-minute monitor's raw snapshots and a
                                       sha256 list for each run
```

**Chain of custody:** each commute bundle's own fingerprint is also published in
that window's results (`docs/data/school-commute/<date>-<am|pm>.json`, under
`coverage.raw_archive`). Git history then independently proves when the bundle
existed. Anyone can recheck a bundle with `shasum -a 256 2026-11-05-am.tar.gz`.

**Backups:** each commute bundle is also kept as a GitHub Actions artifact for
90 days, and realtime snapshots for 30 days, in case Drive is ever unreachable.

**If uploads stop:** the run shows a red X in Actions and GitHub emails you. The
usual cause is the app still being in "Testing" (Part 1, step 6). Re-run Part 2
and update the secret.
