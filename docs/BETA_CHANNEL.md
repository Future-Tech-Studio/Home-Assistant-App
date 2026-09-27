# Stable and Beta Channels

The App has two update channels. Home Assistant only offers an update when the
`version` in `future_homes_tech_app/config.yaml` changes on the branch an
installation follows, so the branch decides who receives an update.

| Channel | Branch | Repository URL added in Home Assistant | Who receives updates |
| ------- | ------ | -------------------------------------- | -------------------- |
| Stable  | `main` | `https://github.com/fht-ha/FHT-HA` | Every normal installation |
| Beta    | `beta` | `https://github.com/fht-ha/FHT-HA#beta` | Only installations that add the `#beta` URL (or mount the `beta` branch locally) |

## Rules

- All in-development work is committed to `beta` (or a feature branch merged
  into `beta`). Nothing is merged into `main` until the homeowner approves it.
- `main` only changes when a tested Beta build is promoted. That is the only
  time other installations receive an update.
- `stable_releases/STABLE.json` still changes only with explicit homeowner
  approval after live Home Assistant testing.

## Beta Mode option

`beta_mode` (Settings → Apps → Future Homes Tech App → Configuration) is off by
default. When it is on:

- the startup log warns that Beta mode is active;
- the interface shows a **BETA** badge beside the version;
- `/api/app-info` reports `"beta_mode": true`, and the interface sets
  `data-beta-mode` on the page root;
- backend code can gate unfinished features with `beta_mode_enabled()`, and
  interface code with `betaModeEnabled`.

Unfinished features should be gated behind Beta mode even on the `beta`
branch, so a promoted build stays safe for installations that leave it off.

## Getting Beta updates on your Home Assistant

Either:

1. Keep the existing local workflow: mount the `beta` branch's
   `future_homes_tech_app` directory into `/addons`, rebuild the local App, and
   enable `beta_mode`; or
2. In Settings → Apps → App Store → ⋮ → Repositories, add
   `https://github.com/fht-ha/FHT-HA#beta`, install **Future Homes Tech App**
   from that repository, and enable `beta_mode`.

Home Assistant treats each repository or local install as a separate App with
its own private `/data`. Do not run a Stable and a Beta install at the same
time on one Home Assistant: both write the same generated configuration.
Stop one before starting the other.

Anyone who knows the `#beta` URL and can read the repository could add it. To
keep Beta updates limited to you, do not share that URL; keeping the
repository private is the only hard restriction.

## Workflow

Start the Beta branch once (from `main`):

```bash
git fetch origin main
git checkout -b beta origin/main
git push -u origin beta
```

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
