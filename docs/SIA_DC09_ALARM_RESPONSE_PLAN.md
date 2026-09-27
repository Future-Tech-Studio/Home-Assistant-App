# UniFi Protect SIA DC-09 Alarm Response Plan

Status: planning and interoperability testing only  
Created: 2026-08-01  
Owner: Future Homes Tech

## Decision

Use a two-stage rollout:

1. Build a non-dispatch staging receiver to prove that UniFi Protect can connect,
   send encrypted SIA DC-09 signals, receive the required acknowledgement, and
   populate a Future Homes Tech operator queue.
2. Put production alarm dispatch through a licensed, preferably UL-listed,
   wholesale central station until Future Homes Tech has the licensing,
   facilities, staffing, redundancy, training, insurance, and audited procedures
   required to operate a monitoring station directly.

The staging receiver must never contact public-safety agencies. It is for test
accounts and consenting internal pilot sites only.

## What Protect is asking for

| Protect field | Future Homes Tech supplies | Rule |
| --- | --- | --- |
| Host name / IP | Public SIA receiver address | Use a reserved static public IP. A DNS name may point to it for staging, but confirm the exact compliance requirement with the receiving-station partner. |
| Port | Dedicated inbound SIA listener port | Confirm whether Protect uses TCP or UDP and whether the protocol is selectable before opening a firewall rule. Do not assume this is an HTTPS port. |
| Account number | Unique protected-premises identifier | One account per customer/site. Never recycle an account number. Keep test accounts visibly separate from production accounts. |
| Encryption key | Per-account AES key shared with the receiver | Generate it in a secrets manager, never commit it, never show it in event logs, and rotate it under a documented procedure. Confirm accepted key length and encoding in Protect. |

Before the first test, capture the Protect version, mobile-app version, console
model, field validation rules, transport protocol, supported AES mode/key sizes,
message format, event-code profile, retry timing, supervision behavior, and
restore/cancel behavior. These are interoperability facts to verify, not infer.

## Recommended architecture

```text
UniFi Protect at customer site
        |
        | encrypted SIA DC-09 over IP
        v
Public static IP + restricted listener port
        |
        v
SIA receiver service
  - frame limits and connection limits
  - CRC validation
  - per-account key lookup and decryption
  - replay/duplicate detection
  - durable event write before ACK
  - ACK/NAK/DUH response as required by the standard
        |
        v
Durable alarm event queue
        |
        +--> Future Homes Tech operator console
        |      - site and contact plan
        |      - camera/device mapping
        |      - video verification link/workflow
        |      - acknowledgement and ownership
        |      - escalation timer
        |      - complete audit trail
        |
        +--> health monitoring and after-hours technical alerts
        |
        +--> licensed central station integration (production)
```

The SIA listener should be a small, isolated internet service. Do not expose the
Home Assistant add-on directly to the internet and do not place raw alarm
traffic on the existing add-on's web interface. The add-on can consume a
sanitized internal event API later.

For the protocol engine, evaluate the SIA Intrusion Subcommittee/Swissdotnet
Java DC-09 library first. It covers client, server, parsing, TCP/UDP, and protocol
messages, but commercial use requires a separate license. Do not copy it into a
commercial product without obtaining that license. The current ANSI/SIA
DC-09-2026 standard should be the implementation and test authority.

## Minimum staging build

### Receiver

- One small cloud host with a reserved static IP and a staging-only DNS name.
- An isolated SIA listener port with connection/rate limits.
- Account allowlist containing only synthetic test accounts.
- Per-account encryption keys stored in a managed secret store.
- Durable database table for the original frame fingerprint, normalized event,
  receive time, account, sequence, receiver response, and processing state.
- Append-only audit log with secret redaction.
- Health checks for receiver availability, event-queue age, database writes,
  acknowledgement latency, decrypt failures, bad CRCs, duplicates, and clock
  drift.
- No automated public-safety, fire, medical, or customer dispatch actions.

### Operator console

Each alarm card needs:

- received time and time since receipt;
- account, site, alarm type, source device/zone, and restore/cancel state;
- assigned operator and acknowledgement timer;
- customer verification contacts and passphrase procedure;
- a least-privilege path to the matching Protect site/camera;
- verification classification, notes, actions, and timestamps;
- escalation status and final disposition.

Operators should use named accounts and least-privilege Protect access. Shared
administrator credentials are not acceptable. Video access and every operator
action must be auditable.

## Response team

### Pilot team (no dispatch)

- **Program owner:** owns scope, provider relationships, budget, and launch gate.
- **Protocol/integration engineer:** owns DC-09 interoperability and Protect test
  cases.
- **Application engineer:** owns event storage, queue, console, and integrations.
- **Operator lead:** writes the response playbooks and runs simulations.
- **Compliance/licensing owner:** confirms state licensing, contracts, privacy,
  retention, insurance, and local false-alarm rules with counsel.
- **Technical on-call:** responds to receiver outage, queue delay, key failure,
  and clock/failover alerts.

Run pilot exercises with a primary operator and a separate backup observer. The
exercise ends at documented verification/escalation; it does not contact public
safety.

### Production response

For the first production launch, contract with a licensed wholesale central
station that can receive Protect's DC-09 profile and provide an API or automation
feed back to Future Homes Tech. The central station owns continuous signal
handling and authorized dispatch; the Future Homes Tech console can add Protect
video verification, customer context, technician workflows, and reporting.

Do not build an in-house 24/7 dispatch operation until the licensing and central
station requirements are signed off. In Arizona, an alarm business includes a
business providing alarm monitoring services, and the State Board of Technical
Registration licenses alarm businesses and alarm agents. This plan is not legal
advice; confirm the intended operating model with the Board, counsel, insurer,
and each relevant authority having jurisdiction.

## First interoperability test

1. Create a synthetic account, for example `T900001`, in the staging receiver.
2. Generate a unique staging AES key in the secret store and load it into the
   receiver without putting it in source control or screenshots.
3. Configure the staging host/IP, port, account, and matching key in Protect.
4. Trigger Protect's built-in test if available. Otherwise create a harmless,
   scheduled test alarm on one internal camera or sensor.
5. Confirm, in order:
   - connection reached the correct listener;
   - frame size and CRC were valid;
   - account selected the correct key;
   - encrypted content decrypted and parsed;
   - event was durably stored before acknowledgement;
   - Protect accepted the acknowledgement and stopped retrying;
   - exactly one operator event appeared with the correct site, trigger, source,
     and time;
   - operator acknowledgement and closure were captured in the audit trail.
6. Save a redacted interoperability fixture and the observed Protect behavior as
   a regression test. Never save a real encryption key or unredacted customer
   data in the fixture.

## Required test matrix

| Test | Expected result |
| --- | --- |
| Valid encrypted alarm | One durable event, valid ACK, one operator notification |
| Restore/cancel | Linked to the original incident; never silently replaces it |
| Duplicate/retry | ACK is safe and event is not double-dispatched |
| Wrong key | No plaintext guessed; controlled protocol response and technical alert |
| Unknown account | Rejected/quarantined without revealing valid account IDs |
| Invalid CRC/truncated/oversized frame | Rejected safely; listener remains healthy |
| Old/future timestamp and replay | Flagged or rejected per policy; no duplicate response |
| Burst of alarms | Queue remains ordered and acknowledgement latency stays within the tested limit |
| Database unavailable | No success ACK before durable storage; alert and recover cleanly |
| Receiver restart | No event loss and deduplication still works |
| WAN/DNS failure | Protect retry/failure behavior is documented and alerted |
| Supervision/heartbeat loss | Communications trouble appears within the agreed service window |
| Operator does not acknowledge | Escalates to backup operator within the playbook timer |

## Launch gates

### Gate A — lab ready

- Protect 7.1.60 or later and compatible mobile app confirmed.
- Protocol transport and encryption details captured from the actual UI.
- Standard/library licensing resolved for development use.
- Static IP, isolated port, test account, and test key ready.
- No-dispatch safeguard reviewed.

### Gate B — internal pilot ready

- Full test matrix passes repeatedly.
- Operator console and audit trail are usable.
- Written playbooks cover burglary/intrusion, panic/duress, environmental events,
  video unavailable, communications failure, false alarm, and cancellation.
- Tabletop drills completed with primary and backup operators.
- Retention, privacy, access review, incident response, and key rotation approved.

### Gate C — production ready

- Licensed monitoring model and contracts approved.
- Wholesale central station has passed Protect interoperability testing.
- Customer agreement, contact list, verification rules, and local permits are
  complete for every site.
- 24/7 coverage, backup facilities/services, power/network redundancy, disaster
  recovery, cyber monitoring, and service-level objectives are proven.
- Public-safety dispatch remains controlled by the authorized monitoring
  workflow, with false-alarm and cancellation procedures tested.

## Decisions needed to start

1. Approve the **wholesale-central-station-first** production model.
2. Select a small cloud host/provider for the isolated staging receiver.
3. Obtain the current DC-09 standard and decide whether to license the
   Swissdotnet library or purchase a supported commercial receiver.
4. Identify one internal UniFi Protect site and one harmless test trigger.
5. Appoint the six pilot roles above; one person may hold multiple engineering
   roles, but the operator and backup observer should be separate during drills.
6. Ask candidate central stations these interoperability questions:
   - Do you accept ANSI/SIA DC-09 from UniFi Protect 7.1.60+?
   - TCP, UDP, or both? Which port and source-IP restrictions?
   - Which AES key lengths/encoding and SIA payload profile are supported?
   - How are test, alarm, restore, cancel, supervision, and communication-failure
     events represented?
   - Can each site use a unique key and account?
   - What API/webhook feed can populate our operator console?
   - Are managed video monitoring and UniFi Protect video verification supported?
   - What licensing, UL listing category, redundancy, training, retention,
     insurance, and service levels apply?

## Primary references

- Ubiquiti, UniFi Protect 7.1.60 release:
  https://community.ui.com/releases/470e3f55-27fe-4437-918f-1983562f459a
- Ubiquiti, Alarm Manager overview:
  https://help.ui.com/hc/en-us/articles/27721287753239
- Security Industry Association, ANSI/SIA DC-09-2026:
  https://www.securityindustry.org/industry-standards/dc-09-2026/
- SIA Intrusion Subcommittee DC-09 library:
  https://github.com/SIA-Intrusion-Subcommittee/sia-dc-09-library
- UL central station service certification:
  https://www.ul.com/services/central-station-service-certification
- Arizona Board of Technical Registration alarm business application:
  https://btr.az.gov/applicants/alarm-industry-applicants/alarm-business-application

