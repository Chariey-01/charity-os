# CharityOS on Android

There are two ways to put CharityOS on an Android phone. Both run the same web app from `https://charityos.charity-jk.workers.dev`; neither is a rewrite.

| | Installable PWA (recommended first) | Signed APK (Trusted Web Activity) |
|---|---|---|
| How | Chrome → ⋮ → **Install app** | Install `charityos-1.0.0.apk` (sideload) |
| Needs | the deployed HTTPS site | the deployed site **and** `/.well-known/assetlinks.json` (served by the Worker) |
| Updates | automatic (service worker) | web content updates automatically; the APK shell rarely changes |
| Notifications | Web Push (Chrome) | Web Push, delegated to Chrome by the TWA |
| Play Store | no | possible later (an `.aab` is built too) |

## 1. Install the PWA (no APK needed)

1. Open `https://charityos.charity-jk.workers.dev` in **Chrome** on the phone and sign in.
2. ⋮ menu → **Install app** (or **Add to Home screen** → Install).
3. Open CharityOS from the home screen. It runs full-screen and opens offline (the app shell is cached).
4. **Me → Reminders and calendar → Turn on notifications**, allow, then **Send a test**.

## 2. The signed APK

Built and signature-verified (APK Signature Scheme v2 and v3) on 28 Nov 2026 with Bubblewrap 1.28.0 (Google's Trusted Web Activity tool), JDK 17 (Temurin 17.0.21.1) and Android build-tools 36.1.0.

| Item | Value |
|---|---|
| Package | `dev.workers.charity_jk.charityos.twa` |
| Opens | `https://charityos.charity-jk.workers.dev/#/today` |
| Version | 1.0.0 (code 1), minSdk 24 (Android 7.0+), targetSdk 36 |
| Signing certificate SHA-256 | `EA:17:55:77:32:CC:A0:4B:15:DD:0A:AC:FF:AE:C9:EA:F7:DD:61:0F:F9:0F:3B:0D:FD:76:54:3D:73:D6:AD:0C` |
| APK and AAB | `~/charityos-qa-evidence/20261128_overnight-sprint/android/charityos-1.0.0.apk` (SHA-256 `b46f410d…67a6`) and `charityos-1.0.0.aab`; build output in `~/charityos-android/twa/` |
| Project | `~/charityos-android/twa` (generated; not in the repo) |

### Installing it on the phone

1. Deploy the site first (`docs/operations/cloudflare-deployment.md`). Check `https://charityos.charity-jk.workers.dev/.well-known/assetlinks.json` shows the package and fingerprint above.
2. Copy the APK to the phone (USB, Google Drive, or `adb install app-release-signed.apk`).
3. Open it; Android asks to allow installs from that source once. Install.
4. Open **CharityOS**. If asset links verify, there is **no address bar**. If you see an address bar at the top, the site and the APK do not match yet (wrong fingerprint, site not deployed, or the Worker not redeployed after editing `wrangler.jsonc`); the app still works, it just looks like a Custom Tab.

### Signing key: keep it safe

- Keystore: `~/.config/charityos-keys/android/charityos-android.jks` (alias `charityos`); password: `~/.config/charityos-keys/android/keystore-password.txt`. Both mode 600, **never in git**.
- Back both up now to your password manager or an encrypted drive. Without them you cannot publish an update that installs over the current app; people would have to uninstall and reinstall.
- If you later publish on Google Play, enrol in Play App Signing; this key becomes your *upload* key and Google holds the app signing key. Add Google's signing fingerprint to `ANDROID_CERT_SHA256` (comma-separated) in `cloudflare/wrangler.jsonc`.

### Rebuilding

```bash
cd ~/charityos-android/twa
export BUBBLEWRAP_KEYSTORE_PASSWORD="$(cat ~/.config/charityos-keys/android/keystore-password.txt)"
export BUBBLEWRAP_KEY_PASSWORD="$BUBBLEWRAP_KEYSTORE_PASSWORD"
# bump appVersionCode and appVersionName in twa-manifest.json first
npx bubblewrap update --skipVersionUpgrade && npx bubblewrap build --skipPwaValidation
```

Bubblewrap needs JDK 17 (`~/charityos-android/jdk17`) and the Android SDK (`~/charityos-android/sdk`), configured in `~/.bubblewrap/config.json`. Building accepted the Android SDK licence on this machine.

## 3. Alarms versus notifications

A web app, installed or wrapped, cannot schedule an exact alarm on Android. CharityOS reminders are server-sent push notifications: reliable enough for "start your study block", but Android may delay them in battery saver or Doze, and they do not ring like an alarm. Exact, ringing alarms would need a small native Android component (`AlarmManager` with the `SCHEDULE_EXACT_ALARM` permission), which is out of scope for this release. For anything you must not miss, also set an alarm in the Clock app.

## 4. Still to verify on a real phone (not possible overnight)

- [ ] PWA installs from Chrome and opens full-screen.
- [ ] APK installs; no address bar after the site is deployed (asset links verified).
- [ ] Turning notifications on works in the installed app; a test notification arrives with the app closed; tapping it opens the right screen; **Snooze 10 min** brings it back.
- [ ] Back button and the Android share/recents behave normally.
- [ ] Offline launch shows the app shell; it reconnects by itself.
