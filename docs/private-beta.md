# Running the private beta

## Accounts

- **You (the owner).** Create your account once, on the production database, with `manage.py bootstrap_charityos` (see `docs/operations/cloudflare-deployment.md`, step C). Then make yourself the beta admin:

  ```bash
  ../.venv/bin/python manage.py grant_beta_admin --email YOUR-EMAIL
  ```

  This sets `is_staff`. It gives no Django-admin permissions; it only unlocks **Me → Beta admin** in the app.

- **Friends.** Sign-up is invite-only (`CHARITYOS_SIGNUP_MODE=invite`, the default; `closed` turns it off). In the app: **Me → Beta admin → Invite a friend → Create invite → Copy link**, then send the link privately (WhatsApp, Signal…). The link opens the sign-up page with the code filled in. Each invite works once, for 14 days, and can be limited to one email. The code is shown once; only its hash is stored.

  From a terminal instead: `manage.py create_beta_invite --by YOUR-EMAIL --note "Amina"`.

- Every account is separate. Every API query and change is limited to the signed-in account; tests check that one account cannot read, change or link another's records.

## Forgotten passwords (no email service yet)

1. Your friend tells you they forgot their password.
2. **Me → Beta admin → People → Reset link**, or `manage.py issue_password_reset --email THEIR-EMAIL`.
3. Send them the link privately. It works once, for one day, and lets them choose a new password.

Signed-in users can change their password under **Me → Account and privacy**. Sign-in is still protected by django-axes (5 failures per email and address, then 15 minutes' lockout).

## Feedback and bugs

Friends use **Me → Beta feedback** (bug, idea, question, praise; optionally their browser and screen size). You read it under **Me → Beta admin → Feedback** and mark items resolved.

## Accountability partners (optional)

1. A person opens **Me → Accountability → Invite** and enters the partner's email. Nothing is shared yet.
2. The partner signs in with that email and accepts under **Me → Accountability**. (No account yet? They need a beta invite first.)
3. The person chooses what to share: specific goals (title, progress, milestones; never notes or "why"), a weekly summary (numbers only), completed achievements (titles, last 30 days) and specific weekly reviews (wins and next week; never lessons).
4. The partner sees it read-only and can send a cheer, encouragement or a check-in question. They can never edit anything.
5. Either side can stop at any time; the person sharing can also pause. Sharing is one-directional: to share both ways, each invites the other.

Never shared: journal entries, reflections, notes, evidence, tasks, projects, unshared goals, the person's email.

## Erasing an account

`manage.py erase_user EMAIL` (dry run) then `--confirm EMAIL`. It removes the account and all its records. Accountability partnerships belong to both people, so erasing either person removes the partnership and its cheers, and nothing else of the other person's.

## What to tell friends

- It is a private beta: expect bugs and changes; keep anything critical elsewhere too.
- Their records are private to them. You, as admin, see their name, email, sign-up date, last sign-in and feedback, not their records.
- Install: on Android, open the link in Chrome → menu → **Install app**. Then **Me → Reminders and calendar → Turn on notifications**.
- The privacy notice is in the app (**Me → Account and privacy**, or the sign-in page).
