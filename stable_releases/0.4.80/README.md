# Stable rollback: 0.4.80

This directory preserves Future Homes Tech App version 0.4.80 as the user-designated stable rollback point.

- `future-homes-tech-app-source-0.4.80.tar.gz` contains the complete local source checkout, excluding Git metadata, this stable-release directory, Python caches, and AppleDouble files.
- `future_homes_tech_app-mounted-0.4.80.tar.gz` contains the mounted Home Assistant add-on source from `/Volumes/addons/future_homes_tech_app`.
- The source and mounted copies of `server.py`, `web/index.html`, and `config.yaml` matched before these archives were created.
- `STABLE.json` at the parent level is the authoritative stable pointer. It must not be advanced until the user explicitly approves a newer version as stable.

These archives preserve app code and repository files. They do not contain the add-on's private `/data` volume or Home Assistant's live `/config` contents.
