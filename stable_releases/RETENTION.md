# Release retention — October 4, 2026

## Current policy

The homeowner approved **0.8.7** as stable, replacing 0.8.4 (Stable for
part of the day, with no separate record). The 0.8.1 and 0.7.0 records are
kept as history. New work continues on `beta`; the next Beta is 0.8.13 or
later.

## Earlier on October 4, 2026

The homeowner approved **0.8.1** as stable, replacing 0.7.0.

## September 27, 2026 record

The homeowner approved **0.7.0** as stable, replacing 0.6.1. The 0.6.1 record
is kept as history.

## Earlier on September 27, 2026

The homeowner retired stable **0.5.23** and approved **0.6.1** as stable. The
0.5.23 release record was removed from the repository; its gitignored local
archives on the development Mac may be deleted once 0.6.1 archives exist. New
work ships on the `beta` branch; the next Beta version is 0.6.2. Keep 0.6.1
until the homeowner approves a replacement.

## September 12, 2026 record

The homeowner now explicitly approves **0.5.23** as stable and authorizes removing the previous stable app archives. Its original source archive and contained runtime tree were checksum-verified before promotion. A standalone runtime archive was repacked from that verified source. Only the two 0.5.3 application archives and the unavailable duplicate 0.5.23 runtime placeholder are removed; historical notes and private live-settings backups remain. The next candidate is 0.5.24. Keep 0.5.23 until the homeowner approves a replacement.

## Earlier retention record

The homeowner designated **0.5.3** stable and authorized trimming older app archives. The source and mounted-runtime archives in `stable_releases/0.5.3` were copied and checksum-verified before removing older archives.

Removed 49 redundant or superseded `.tar.gz` files from versioned candidate/stable release directories, reclaiming 292,828,734 bytes (about 293 MB). This includes the duplicate candidate copies of 0.5.3; its verified stable copies remain. Small historical manifests and release notes remain as packaging records, but their old archive paths no longer imply those archives are retained.

Kept the 0.5.3 private Home Assistant settings backups and reference-repair archive untouched. No active app files, Home Assistant configuration, devices, source control history, or unrelated project archives were deleted.

The next candidate is 0.5.4. It does not become stable automatically.
