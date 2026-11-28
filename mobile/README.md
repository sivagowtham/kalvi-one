# KalviOne Android app

A thin [Capacitor](https://capacitorjs.com) shell around each college's KalviOne address (decision D33).
Every screen comes from the web app, so new web pages appear in the app with no work here.

## How it behaves

- **First launch:** the user types their college code (for example `demo`). The app checks
  `https://<code>.kalvione.in/manifest.webmanifest`, shows the college's name to confirm, remembers it
  and opens that college's address.
- **Later launches:** the app opens the remembered college straight away.
- **Switch college:** inside the app, every KalviOne page shows a "Switch college" link, which opens the
  picker again. (The app adds `KalviOneApp` to its user agent so the page knows.)
- The app only navigates within `*.kalvione.in`. Other links open outside the app.
- Backups are off (`allowBackup="false"`), so the sign-in cookie is never copied off the phone.

## Getting a test APK

GitHub Actions builds one on every pull request that touches `mobile/`. Open the "Android app"
workflow run, download the `kalvione-debug-apk` artifact, unzip it and install `app-debug.apk` on an
Android phone (allow "install unknown apps" when asked). It needs a live server at `*.kalvione.in`.

## Building locally

Needs Node 22, JDK 21 and the Android SDK (or Android Studio).

```sh
cd mobile
npm ci
npm test                    # college code checks
npx cap sync android        # copy www/ into the Android project
cd android && ./gradlew assembleDebug
```

## Still to do

- Release signing and a Play Store listing (needs a Google Play developer account).
- Push notifications (needs a Firebase project), camera document scanning and fingerprint unlock.
- A real app icon in place of the placeholder "K1".
