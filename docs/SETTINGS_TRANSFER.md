# Moving From the Local App to the Repository App

Home Assistant gives each App install its own private `/data`, so a new
repository install starts without the local install's saved settings. From
0.6.3 the App moves them automatically through the shared Home Assistant
configuration directory.

1. **Update the local App to 0.6.3 or later.** Copy the `main` branch's
   `future_homes_tech_app` directory into `/addons`, then Rebuild and Start the
   local App. On every start, a local install exports its saved settings and
   its Configuration options to
   `/homeassistant/.future_homes_tech_transfer/app-data.tar.gz` (owner-only
   permissions). The log shows `Exported N saved settings items`.
2. **Stop the local App.** Do not uninstall it yet.
3. **Install the repository App.** Add `https://github.com/fht-ha/FHT-HA` under
   Settings → Apps → App Store → ⋮ → Repositories, install **Future Homes Tech
   App**, and start it. Do not start it before step 1.
4. On its first start the repository App imports the saved settings, applies
   the Configuration options, restarts itself once, and deletes the transfer
   file. The log shows `Imported saved settings from the local install`.
5. Check that rooms, doors, switches, and Users & Access look right, then
   uninstall the local App.

Safety rules:

- An install that already has saved settings never imports, so an existing
  install is not overwritten. If the repository App was started before step 1,
  uninstall it and install it again.
- Supervisor's `options.json` and downloaded Beta builds are not transferred.
- The transfer file contains secrets (webhook IDs, the Protect API key, access
  data). It is deleted after import; it is also in any full backup taken while
  it exists.
