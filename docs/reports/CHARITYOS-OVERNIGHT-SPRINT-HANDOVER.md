# CharityOS overnight sprint: handover (28 Nov 2026)

## Morning checklist (about 1 hour)

1. **Back up the Android signing key** now: copy `~/.config/charityos-keys/android/charityos-android.jks` and `keystore-password.txt` into your password manager. Losing them means a future APK cannot update this one.
2. **Create the free accounts** and deploy, following `docs/operations/cloudflare-deployment.md` section 7 (Neon, then Vercel, then the Worker). New this time: generate VAPID keys and a cron secret, set `CHARITYOS_SIGNUP_MODE=invite`, run `grant_beta_admin` for yourself, create the `REMINDERS_KV` namespace.
3. On your phone, open `https://charityos.charity-jk.workers.dev` in Chrome, sign in, **⋮ → Install app**.
4. **Me → Reminders and calendar → Turn on notifications → Send a test**. Close the app and set a reminder 2 minutes ahead; confirm it arrives, tap it, try **Snooze**.
5. Optional: install the APK (`~/charityos-qa-evidence/20261128_overnight-sprint/android/charityos-1.0.0.apk`) and check there is no address bar.
6. **Me → Beta admin → Invite a friend**, send the link privately. Share the demo video if you like.

## 1. What CharityOS now does (verified in a real browser)

| Area | Status |
|---|---|
| **My Vision**: vision statement, aspirations, manifestations, "who I am becoming"; themes, horizons, image links; revisions kept; realised only with evidence or explicit confirmation; archive/restore | Done |
| **Goals and milestones**: measurable or milestone-based; check-ins; overdue/at-risk; linked tasks, roadmaps, projects; history; complete / pause / let go / reopen; archive; year-end carry-forward | Done |
| **Roadmaps**: create blank or from the **AI Engineering template** (16 editable stages, criteria, practice and build items, suggested official resources, nothing marked complete); purpose, dates, goal, notes; add stages, items, resources; pause/resume/complete/archive | Done |
| **Projects**: separate workspaces; status board; milestones; notes; activity | Done |
| **Tasks**: links to project/goal/milestone; checklists; "Remind me" (plus the existing backlog, due dates, defer, archive/restore) | Done |
| **Challenges**: 30 / 90 / 96 / 365 / custom; start, pause, resume, complete, make primary, archive | Done |
| **My Journey**: calendar-year chapters; permanent dated timeline from snapshots (later edits never rewrite it); journal entries (decisions, challenges overcome, lessons); deliberate year-end carry-forward | Done |
| **Insights**: new *Direction* view (goals/roadmaps/projects movement, what keeps slipping) and a 6-month period, plus the existing week and trends | Done |
| **Phone reminders**: server-sent Web Push while the app is closed; once/daily/weekly; activity-start, planning and review reminders; Snooze; Google Calendar `.ics` link | Done, **real Android phone not yet tested** |
| **Private beta**: invite-only sign-up, reset links (no email needed), feedback, privacy notice, change password | Done |
| **Accountability partners** (optional): consent, choose exactly what to share, read-only, cheers, pause, stop | Done |
| **Android**: installable PWA; signed TWA APK | APK built and signature-verified; **not installed on a device yet** |
| **Fixed**: TD-1 (a finished task's workstream is now fixed at completion time) | Done |

## 2. Test results (all run tonight, locally)

| Suite | Command | Result |
|---|---|---|
| Backend | `pytest` (PostgreSQL 16, checkout's own test DB) | **647 passed** (602 before the sprint) |
| Backend deploy checks | `manage.py check --deploy` (production settings, dummy secrets) | no issues |
| Frontend | `vitest run` / `tsc -b` / `eslint .` / `vite build` | **116 passed** / clean / clean / OK |
| Cloudflare Worker | `npm test` / `wrangler deploy --dry-run` | **24 passed** / OK |
| Browser: original acceptance (`acceptance.mjs`) | production build | **16/16** |
| Browser: Life OS journey (`life-os.mjs`) | production build at 360, 390, 430, 820, 1280 px | **16/16 each**, 0 px horizontal overflow |
| Browser: private beta, two sessions (`beta.mjs`) | production build | **11/11** |
| Browser: real Web Push via Google FCM (`push.mjs`) | Chrome headless | passed 6 of 8 runs (see defects) |

GitHub Actions still refuses every job ("account is locked due to a billing issue"; 0 steps run), so all evidence is local. Screenshots and video: `~/charityos-qa-evidence/20261128_overnight-sprint/`.

## 3. Known limitations and defects

- **Not deployed.** No live URL yet: it needs your Neon and Vercel accounts and `wrangler login` (step 2 above). I did not create accounts or spend anything.
- **No real Android phone tested**: PWA install, APK, notifications with the app closed, back button. Checklist in `docs/android-app.md` §4.
- **Push registration can stall** the first time a fresh Chrome profile registers with Google's push service (2 of 8 headless runs). The app now shows a clear "try again" message after 30 s instead of waiting silently. Watch for it on the phone.
- **Notifications are not alarms.** Android may delay them in battery saver; exact ringing alarms would need a native component.
- **No email service**: forgotten passwords go through a reset link you send.
- **Not built** (deliberately or for time): group/shared challenges and an activity feed (only partner cheers); image upload for the vision board (image links only); two-way Google Calendar sync (read-only `.ics` only); a dedicated monthly/quarterly review wizard (use Journey "review" entries and Insights periods); evidence attached directly to goals (it attaches to tasks, focus sessions, roadmap items, achievements; goals get a completion note and vision items an evidence link).
- The demo video has captions but no voice-over.

## 4. Git

| PR | Content | State |
|---|---|---|
| #7 | Vision, goals, milestones, projects, roadmap templates, challenges, My Journey, TD-1 | merged |
| #8 | Web Push reminders, snooze, Cloudflare cron, calendar feed | merged |
| #9 | Private beta and accountability partners | merged |
| #10 | Insights direction, 6-month period, Android asset links, docs | merged |
| #11 | Release verification: acceptance scripts, push timeout, reminder copy fix, this handover | merged |

`main` was `1f73c9a` before the sprint and `f691b9b` before #11; the final `main` is the merge of #11. No force-push, no history rewritten. Untouched: the main checkout `~/Progress_tracker` (still on `feature/mobile-scheduler` with its untracked `.cloudflare/`), the parked `feature/project-domain` worktree, and every protected database (`charityos`, `test_charityos`, `charityos_gate`, `charityos_p2`, `test_charityos_p2`, `charityos_acceptance`). Work happened in `~/Progress_tracker-sprint` with a throwaway database `charityos_sprint` (safe to drop).

## 5. Deployment ($0)

Cloudflare Worker (Free) serves the PWA, proxies `/api`, serves `assetlinks.json` and runs the reminder cron → Django on Vercel Hobby (Frankfurt) → Neon Free PostgreSQL (Frankfurt). Django cannot run inside Workers Free (measured earlier: 110–250 ms CPU per request against a 10 ms limit), so Vercel is the free backend; Vercel's own cron is daily-only, which is why Cloudflare's cron sends reminders. Limits and costs: `docs/operations/cloudflare-deployment.md` §4 and `docs/reminders-and-notifications.md`.

## 6. Android

- PWA: Chrome → Install app (docs/android-app.md §1).
- APK: `~/charityos-qa-evidence/20261128_overnight-sprint/android/charityos-1.0.0.apk` (package `dev.workers.charity_jk.charityos.twa`, minSdk 24, signed, v2+v3 verified). It opens the deployed site, so install it after deploying.

## 7. Demonstration

`~/charityos-qa-evidence/20261128_overnight-sprint/demo/charityos-demo.mp4` (2 minutes, phone size, "DEMO DATA" badge, sample data only; WebM too). Scenes: Today, Plan, Vision, goal and milestones, AI Engineering roadmap, project and task, focus session with outcome and evidence, My Journey, Insights, reminders, accountability.

## 8. Private beta in one paragraph

You become beta admin with `manage.py grant_beta_admin --email YOU`. **Me → Beta admin → Invite a friend** makes a one-use, 14-day link; your friend opens it, creates an account and accepts the privacy notice. Everyone's records are private to them. Friends send feedback from **Me → Beta feedback**; you read it in Beta admin. A forgotten password: **Beta admin → People → Reset link**. Accountability is optional: **Me → Accountability → Invite** a partner by email; they accept from their own account, and you choose exactly which goals, summaries and reviews they see. Details: `docs/private-beta.md`.
