# Releasing COMPAS

Cutting a release is one `git tag` push. Everything after that —  building on
both platforms, signing and notarizing the Mac app, creating the GitHub
Release, attaching the downloads — is [.github/workflows/release.yml](.github/workflows/release.yml).

- [Cutting a release](#cutting-a-release)
- [macOS signing and notarization](#macos-signing-and-notarization) ← the long one
- [Signing a build on your own Mac](#signing-a-build-on-your-own-mac)
- [Windows signing](#windows-signing)
- [Troubleshooting](#troubleshooting)

---

## Cutting a release

1. Bump the version in [pyproject.toml](pyproject.toml) (`version = "0.2.0"`),
   commit, push.
2. Tag and push the tag:

   ```bash
   git tag -a v0.2.0 -m "COMPAS 0.2.0"
   git push origin v0.2.0
   ```

3. Watch it: `gh run watch` (or the Actions tab). Roughly 10–20 minutes —
   notarization is most of the tail.
4. The release appears at `https://github.com/sericson0/compas/releases/tag/v0.2.0`
   with two assets:

   ```
   COMPAS-0.2.0-windows-x64.zip
   COMPAS-0.2.0-macos-arm64.zip
   ```

The tag drives the version — the workflow strips the leading `v` and passes it
to PyInstaller as `COMPAS_VERSION`, which lands in the Mac app's Info.plist and
in both asset filenames.

### Rebuilding a release

Actions → **Release** → **Run workflow** → type the tag (`v0.2.0`). It rebuilds
and replaces that release's assets in place, keeping the same URL. Use this
after adding the signing secrets below, or when a build failed on one platform.

Leaving the tag box blank does a dry run: it builds both platforms and uploads
Actions artifacts, without creating or touching any release.

---

## macOS signing and notarization

### Why it's necessary

A Mac app you build yourself runs fine on the Mac that built it. Send it to
anyone else and macOS refuses: any file arriving via browser, email, or
AirDrop gets a `com.apple.quarantine` attribute, and Gatekeeper checks
quarantined apps before allowing the first launch.

Three tiers of outcome:

| Signing | What the user sees |
| --- | --- |
| None / ad-hoc | *"COMPAS is damaged and can't be opened"* — misleading; it just isn't signed. Needs right-click → Open, or `xattr -dr`. |
| Developer ID, not notarized | *"cannot be opened because Apple cannot check it for malicious software"*. Still needs right-click → Open. |
| Developer ID + notarized + stapled | Opens on double-click. No warning. |

Only the third is a real distribution. It needs the paid Apple Developer
Program membership ($99/yr) — there is no free path to a clean launch.

Note that these are *distribution* requirements. Anyone who builds COMPAS
themselves from [BUILDING.md](BUILDING.md) never encounters them.

### What you need to produce

Five GitHub repository secrets. The rest of this section is how to get each.

| Secret | What it is |
| --- | --- |
| `MACOS_CERTIFICATE_P12` | Your Developer ID Application certificate + private key, exported as `.p12` and base64-encoded |
| `MACOS_CERTIFICATE_PASSWORD` | The password you set when exporting that `.p12` |
| `MACOS_SIGNING_IDENTITY` | The identity string, e.g. `Developer ID Application: Sean Ericson (AB12CD34EF)` |
| `APPLE_ID` | The Apple ID email on the developer account |
| `APPLE_APP_PASSWORD` | An app-specific password for that Apple ID (not your real password) |
| `APPLE_TEAM_ID` | The 10-character Team ID, e.g. `AB12CD34EF` |

All of this needs a Mac. Steps 1–3 cannot be done from Windows.

### Step 1 — Create the Developer ID Application certificate

There are two flavors of distribution certificate and picking the wrong one
wastes a cycle: **Developer ID Application** is for apps shipped outside the
Mac App Store, which is what this is. *Apple Distribution* / *Mac App
Distribution* are App Store only and cannot be notarized for direct download.

Easiest route, on your Mac with Xcode installed:

1. Xcode → **Settings** → **Accounts**
2. Sign in with the Apple ID on the developer account, select the team
3. **Manage Certificates…** → **+** → **Developer ID Application**

It's created and installed into your login keychain in one step. If you don't
have Xcode, do it through [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates):
generate a Certificate Signing Request in Keychain Access
(**Keychain Access → Certificate Assistant → Request a Certificate From a
Certificate Authority**, "Saved to disk"), upload it, download the resulting
`.cer`, and double-click it to install.

Confirm it's there and note the exact string:

```bash
security find-identity -v -p codesigning
```

```
1) A1B2C3...  "Developer ID Application: Sean Ericson (AB12CD34EF)"
```

The quoted string is `MACOS_SIGNING_IDENTITY`. The 10 characters in
parentheses are `APPLE_TEAM_ID`. Copy them exactly, parentheses included for
the identity.

> If nothing is listed, or you see the certificate but signing later fails with
> *"no identity found"*, the private key is missing — a certificate downloaded
> onto a different Mac than the one that made the CSR has no usable key.
> Re-create it on this Mac.

### Step 2 — Export the certificate as .p12

Signing happens on a GitHub runner, so both the certificate **and its private
key** have to travel there.

1. Open **Keychain Access** → **login** keychain → **My Certificates**
2. Find *Developer ID Application: …*, and click the disclosure triangle. You
   should see a private key nested under it — if not, stop; see the note above.
3. Right-click the **certificate** row (not the key) → **Export "Developer ID
   Application: …"**
4. Format: **Personal Information Exchange (.p12)**. Save as `compas-cert.p12`.
5. It asks for a password to protect the file — invent a strong one. This is
   `MACOS_CERTIFICATE_PASSWORD`. Then it asks for your **login password** to
   release the key from the keychain; that one is not a secret you store.

Base64-encode it, because GitHub secrets hold text, not binary:

```bash
base64 -i compas-cert.p12 | pbcopy
```

That's `MACOS_CERTIFICATE_P12`, now on your clipboard.

Delete the `.p12` afterwards — it's your signing identity in a single file:

```bash
rm compas-cert.p12
```

### Step 3 — Create an app-specific password

Notarization uploads to Apple and authenticates as you. Never put your real
Apple ID password in CI; use a scoped one that you can revoke on its own.

1. [appleid.apple.com](https://appleid.apple.com) → sign in
2. **Sign-In and Security** → **App-Specific Passwords** → **+**
3. Name it `COMPAS notarization`
4. Copy the generated `xxxx-xxxx-xxxx-xxxx` — it is shown once

That's `APPLE_APP_PASSWORD`. `APPLE_ID` is the email you just signed in with.

> Requires two-factor authentication on the Apple ID. It's mandatory for
> developer accounts anyway, so it should already be on.

### Step 4 — Add the secrets to GitHub

```bash
gh secret set MACOS_CERTIFICATE_P12       # paste the base64, then Ctrl-D
gh secret set MACOS_CERTIFICATE_PASSWORD
gh secret set MACOS_SIGNING_IDENTITY
gh secret set APPLE_ID
gh secret set APPLE_APP_PASSWORD
gh secret set APPLE_TEAM_ID
```

Or in the browser: **Settings → Secrets and variables → Actions → New
repository secret**.

Check all six landed:

```bash
gh secret list
```

### Step 5 — Rebuild the release

Actions → **Release** → **Run workflow** → enter the tag → Run.

The workflow keys off `MACOS_CERTIFICATE_P12`: present, it signs and
notarizes; absent, it logs a warning and ships an unsigned build rather than
failing. So a missing or misnamed secret shows up as a *warning* in the run
summary, not an error — check for it.

What the signed run does, in order:

1. Imports the `.p12` into a throwaway keychain on the runner
2. Builds with `COMPAS_CODESIGN_IDENTITY` set, so PyInstaller signs every
   nested `.so`/`.dylib`/framework and then the bundle, with the hardened
   runtime and [packaging/entitlements.plist](packaging/entitlements.plist)
3. `codesign --verify --deep --strict` — catches a bad signature before
   spending 5 minutes at Apple
4. `ditto` the `.app` into a zip, `xcrun notarytool submit --wait`
5. `xcrun stapler staple` the returned ticket into the bundle, then re-zip

Step 5 is the one that's easy to skip and quietly regret: without a stapled
ticket, Gatekeeper has to phone Apple on first launch, so anyone opening the
app offline gets the warning anyway.

Verify the published asset yourself — download it from the release page (so it
carries real quarantine), unzip, and:

```bash
spctl --assess --type exec --verbose=4 /Applications/COMPAS.app
```

```
/Applications/COMPAS.app: accepted
source=Notarized Developer ID
```

Anything else means users will see a warning.

---

## Signing a build on your own Mac

For a one-off build you hand to someone directly, without going through CI.

Store the notarization credentials once, in your keychain:

```bash
xcrun notarytool store-credentials compas-notary \
  --apple-id "you@example.com" \
  --team-id "AB12CD34EF" \
  --password "xxxx-xxxx-xxxx-xxxx"
```

Then per build:

```bash
export COMPAS_CODESIGN_IDENTITY="Developer ID Application: Sean Ericson (AB12CD34EF)"
bash packaging/build_macos.sh

ditto -c -k --sequesterRsrc --keepParent dist/COMPAS.app COMPAS.zip
xcrun notarytool submit COMPAS.zip --keychain-profile compas-notary --wait

xcrun stapler staple dist/COMPAS.app
rm COMPAS.zip && ditto -c -k --sequesterRsrc --keepParent dist/COMPAS.app COMPAS.zip
```

`COMPAS.zip` is now the file to send. Unset `COMPAS_CODESIGN_IDENTITY` and the
same script builds unsigned, which is what you want for local testing.

---

## Windows signing

Not set up, and largely not worth it. Windows builds are unsigned, so
SmartScreen shows *"Windows protected your PC"* on first run until enough
people click through — the release notes tell users to click **More info → Run
anyway**.

An Authenticode certificate (~$200–400/yr from a CA, and an OV cert still
accrues SmartScreen reputation slowly) mostly buys a cleaner first-run for
Windows users. If it becomes worth it: EV certificates skip the reputation
wait, and [Azure Trusted Signing](https://azure.microsoft.com/products/trusted-signing)
is the cheapest current route at roughly $10/month. The hook would go in
[release.yml](.github/workflows/release.yml) between the build and archive
steps.

---

## Troubleshooting

**`errSecInternalComponent` during codesign, or the job hangs at signing.**
The keychain wasn't unlocked, or `security set-key-partition-list` didn't run,
so codesign is waiting on a GUI prompt nobody can click. The workflow does
both; if you adapt it, keep them.

**Notarization: "The signature does not include a secure timestamp."**
Signing ran without network access to Apple's timestamp server. Re-run.

**Notarization: "The executable does not have the hardened runtime enabled."**
`COMPAS_CODESIGN_IDENTITY` was empty, so the spec skipped the entitlements
file — the hardened runtime is only applied when a real identity is set. Check
the run log for the *"No MACOS_CERTIFICATE_P12 secret"* warning.

**Notarization succeeds, but the app still warns on first launch.**
The ticket wasn't stapled, or was stapled after the zip was made. The zip has
to be created *after* `stapler staple`.

**App launches, then crashes on the first analysis.**
Almost always numba/llvmlite hitting the hardened runtime. Both
`com.apple.security.cs.allow-jit` and
`com.apple.security.cs.allow-unsigned-executable-memory` are required — one
without the other isn't enough. Confirm they survived into the shipped build:

```bash
codesign --display --entitlements - /Applications/COMPAS.app
```

**Get the real reason for a rejection.** The summary never names the offending
binary; the log does.

```bash
xcrun notarytool log <submission-id> --keychain-profile compas-notary
```

Submission IDs: `xcrun notarytool history --keychain-profile compas-notary`.
