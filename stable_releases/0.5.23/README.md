# Stable release 0.5.23

The homeowner explicitly approved this release as the stable rollback on September 12, 2026. Its original candidate passed `scripts/release_gate.sh` and matched the mounted runtime when packaged. Source archive and contained runtime checksums were verified before promotion. The runtime archive was regenerated from that verified source because the original mounted archive was an unavailable iCloud placeholder.

Restore the runtime archive into the mounted add-on source and rebuild/install using Home Assistant. Keep private Home Assistant settings backups separately; restoring application code is not a database rollback. Newer candidates do not replace this stable release without explicit homeowner approval.
