# Stable release 0.6.1

The homeowner approved 0.6.1 as the stable release on September 27, 2026 and
retired stable 0.5.23. 0.6.1 is the first release on the Stable (`main`) /
Beta (`beta`) channel model described in `docs/BETA_CHANNEL.md`, and adds the
`beta_mode` App option.

`source_tree_sha256` covers the `future_homes_tech_app` directory. Source and
mounted archives are local, gitignored artifacts: create them on the
development Mac with `scripts/package_candidate.py` and record their checksums
in `MANIFEST.json` and `STABLE.json`. Newer versions are developed on `beta`
and do not replace this release without explicit homeowner approval.
