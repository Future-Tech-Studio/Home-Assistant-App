# Stable and Beta Channels

The App has two update channels. Every installation installs the App from
`https://github.com/fht-ha/FHT-HA`, which Home Assistant builds from `main`.

| Channel | Branch | Who receives updates |
| ------- | ------ | -------------------- |
| Stable  | `main` | Every installation, through Home Assistant's normal App updates |
| Beta    | `beta` | Only installations with the `beta_mode` option turned on, through the App's own **Beta X Available** button |

## Rules

- All in-development work is committed to `beta` (or a feature branch merged
  into `beta`). Nothing is merged into `main` until the homeowner approves it.
- `main` only changes when a tested Beta build is promoted. That is the only
  time other installations receive an update.
- `stable_releases/STABLE.json` still changes only with explicit homeowner
  approval after live Home Assistant testing.

## Beta Mode option

Everyone installs the App from `https://github.com/fht-ha/FHT-HA` (Stable).
`beta_mode` (Settings → Apps → Future Homes Tech App → Configuration) is off by
default, and an installation with it off only ever runs Stable.

Turning `beta_mode` on switches that one installation to the Beta channel:

1. The App checks the `beta` branch's `config.yaml` about every five minutes.
   When its version is newer than the running version, the header shows
   **Beta X Available**.
2. Selecting it downloads the `beta` branch from GitHub into the App's private
   `/data/beta` storage, checks the build, and restarts only the App (not Home
   Assistant).
3. On start, `run.sh` copies the downloaded Beta files over the Stable files
   (using the Beta `Dockerfile` `COPY` lines) and restarts itself from the Beta
   `run.sh`. The header shows the Beta version and a **BETA** badge.

Returning to Stable: turn `beta_mode` off and restart the App. The container
starts from the Stable image again; the downloaded Beta build stays on disk
but is not used. A Stable version at least as new as the downloaded Beta
also takes over automatically.

Saved settings stay in `/data` for both channels, so a Beta build that changes
the saved data format must keep it readable by Stable.

In code, gate unfinished features with `beta_mode_enabled()` (backend) or
`betaModeEnabled` (interface).

### Beta packages

Every Beta build carries `future_homes_tech_app/RELEASE.json`, written by
`scripts/build_release_manifest.py` (the release gate fails if it is out of
date). It lists every App file with its SHA-256 and size, and what the build
needs from the installed Stable App: configuration options and Alpine
packages. When installing, the App:

1. reads RELEASE.json at the exact commit it offered;
2. refuses the build if Stable lacks a required option or package;
3. reuses every file already installed with the same hash and downloads only
   the rest, each from that commit, checking size and SHA-256.

A typical Beta update downloads a few hundred kilobytes instead of the whole
repository. Builds from before RELEASE.json still install from the branch
archive.

### What a Beta update cannot change

Beta builds replace the App's Python, `run.sh`, and web files. They cannot
change anything Home Assistant reads from the installed Stable version:
`config.yaml` options and schema, ports, permissions, or packages installed by
the `Dockerfile` `RUN` lines. Ship those as a Stable release first.

### Who can get Beta

Any installation whose owner turns `beta_mode` on can receive Beta updates, and
the `beta` branch is readable by anyone who can read the repository. Keep the
option off on installations you do not control.

## Workflow

Develop on Beta and publish a Beta build:

```bash
git checkout beta
# change code, bump config.yaml version, visible version, CLIENT_VERSION, CHANGELOG
./scripts/release_gate.sh
git commit -am "Beta 0.5.x: ..."
git push origin beta
```

Promote an approved Beta build to Stable:

```bash
git fetch origin
git checkout main
git merge --no-ff origin/beta
./scripts/release_gate.sh
git push origin main
```

## Making the repository private

Do this only after a Stable release that includes the `github_token` option
(0.6.30 or later on `main`) is installed, or updates stop.

1. Create a fine-grained GitHub token: Settings → Developer settings →
   Fine-grained tokens → Generate. Repository access: only `fht-ha/FHT-HA`.
   Permissions: Contents → Read-only. Set an expiry and a reminder to renew.
2. In Home Assistant, open the App → Configuration and paste the token into
   **GitHub access token**. Save and restart the App.
3. In Settings → Apps → App Store → ⋮ → Repositories, remove
   `https://github.com/fht-ha/FHT-HA` and add
   `https://<token>@github.com/fht-ha/FHT-HA` so Home Assistant can still
   build Stable updates. (Home Assistant stores this URL as entered.)
4. On GitHub: Settings → General → Danger Zone → Change visibility → Private.
5. Check that the App still offers Stable and Beta updates.

Anyone else installing from the public URL loses access when it goes private.
