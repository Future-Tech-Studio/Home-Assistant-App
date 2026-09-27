# Audit items 3–6: release 0.5.2

## Implemented

3. A shared Home Configurator catalog endpoint caches the action, wake, toddler and alarm-output catalogs for the inventory/settings revision. Browsers coalesce concurrent catalog reads and reuse one response across rooms. Per-room assignment maps no longer include unrelated rooms. Other legacy editor endpoints remain compatible.
4. Room expansion produces applicable headers and the room-name field. Opening a subsection builds that editor, not all the closed editors. Closing/reopening preserves its DOM and unsaved selections. Existing background-refresh draft protections remain in place. Device Alarms remains a non-collapsing panel as requested previously.
5. Button discovery starts independently at backend startup. Cache reads do not wait behind discovery I/O, and concurrent discovery shares one worker. An expired result remains available during warmup; failed warmups back off for 30 seconds. Initial discovery waits only when the Buttons subsection itself is opened; saved ZHA assignments are fetched along with late discovery.
6. Registry events within a 500 ms batch cause one metadata refresh, off the state-event reader. A later event during refresh queues another batch. State changes received during a snapshot are replayed onto the fresh metadata before the refresh finishes.

## Boundaries and acceptance

- These changes do not replace Home Assistant's ingress/session handling or promise a specific end-to-end opening time.
- Room-specific data still arrives with the room request; this release defers construction of closed subsection editors, not each small saved setting to a separate API call.
- The shared catalog is rebuilt when the inventory revision changes, including state events. A later metadata-only catalog revision could narrow invalidation further.
- Test after installation: open a floor/room, expand Switches, edit a selection without saving, close/reopen it and confirm it remains. Open a second room and verify catalog reuse when its revision is unchanged. Open Buttons during cold startup and verify labels and saved selections arrive without blocking other rooms.
- Confirm ordinary sensor updates still appear after a rename/adoption burst. Do not activate physical sirens or alarms just to test the interface.
- The 0.5.1 candidate archives and retired 0.4.80 recovery archives remain preserved. 0.5.2 is not designated stable without homeowner acceptance.
