# Navigation and status follow-up — 0.4.100

## Confirmed causes

- The installed 0.4.99 app replaces the top-level Home Assistant page with the ingress URL when opened from the sidebar. Exit then assigns `/config/updates`, forcing a complete Home Assistant frontend boot. Caching the app assets does not prevent this host reload.
- Live app logs show Protect arm-mode requests returning 502. A credential-free TLS check from Home Assistant's Terminal app resolves the configured console hostname to the local gateway but fails certificate hostname verification. The certificate identifies `unifi.local`, not the configured `unifi.fht.internal`. A second check using the certificate hostname against the same address fails self-signed-certificate trust. No verification bypass or credential change was performed.
- The live Security dashboard reports Front Door closed, Garage Door unavailable, and Patio Door unavailable. Exterior must not show all-closed while those sensors are unavailable. Other unavailable sensors also exist, but are outside this entry-status change.
- An observed entry-status request took about 2 seconds. The security projection redundantly reopened registry data and copied the whole inventory after the shared snapshot already supplied enriched entities.

## Changes

Keep Home Assistant loaded and present the ingress iframe in the browser's top layer using a manual popover. Restore its original attributes/styles when leaving, refreshing, or navigating Back. Browsers without the popover API retain ordinary embedded rendering instead of performing a top-level redirect. Standalone ingress bookmarks still need a full navigation on exit because no Home Assistant host exists behind them.

Exit uses the same history plus `location-changed` mechanism used by [Home Assistant navigation](https://github.com/home-assistant/frontend/blob/dev/src/common/navigate.ts). No authentication/session data is read or stored by this bridge.

Reuse enriched security inventory, expose safe actionable Protect connection errors, and allow inspection of unavailable/closed exterior sensors instead of making the gray bubble inert. Stale states cannot produce an all-closed green bubble.

## Validation

- Release gate: 197 tests, Python and JavaScript checks, release metadata checks.
- Local fake-data browser verification: fullscreen app rendered within the retained host; Exit displayed the mock Updates view through client navigation without reloading the host document.
- Regression coverage includes iframe delivery, restoring host styles/listeners, browser Back, fallback without popover support, safe TLS/DNS diagnostics, cached security projection, and unavailable exterior display.

## Remaining installation-specific work

Protect needs a trusted certificate valid for the configured console hostname. Adding a CA alone does not fix a hostname mismatch. Do not turn off verification to hide this error. Repair the console certificate/DNS configuration with the homeowner's approval and then verify a live Protect response.

Garage and Patio door availability needs device/integration diagnosis; no sensors were removed, re-paired, or marked closed. Their last-known unavailable state is not proof of a particular radio/network fault.

Stable remains 0.4.80 until explicitly promoted by the user. Candidate archives preserve the previous releases.
