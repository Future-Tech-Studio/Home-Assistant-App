import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";


const source = readFileSync(new URL("../future_homes_tech_app/web/index.html", import.meta.url), "utf8");
function functionSource(name) {
  const match = new RegExp(`^      (?:async )?function ${name}\\(`, "m").exec(source);
  assert.ok(match, name);
  const end = source.indexOf("\n      }", match.index) + "\n      }".length;
  return source.slice(match.index, end);
}
function contextFor(names, globals) {
  const context = vm.createContext(globals);
  vm.runInContext(names.map(functionSource).join("\n"), context);
  return context;
}

const controlTitles = contextFor(["compactControlAreaName", "stripControlAreaPrefix", "controlDeviceParts"], {});
const roomNames = contextFor(["roomNameOrder"], {});
const sortedRoomNames = ["Pantry", "Bedroom 10", "Bathroom 2", "Kitchen", "Bedroom 2", "Master Bedroom Bathroom", "Bathroom 1"]
  .map(name => ({name}))
  .sort((left, right) => roomNames.roomNameOrder(left) - roomNames.roomNameOrder(right) || left.name.localeCompare(right.name, undefined, {numeric: true}));
assert.deepEqual(sortedRoomNames.map(room => room.name), ["Bedroom 2", "Bedroom 10", "Bathroom 1", "Bathroom 2", "Master Bedroom Bathroom", "Kitchen", "Pantry"]);
const doorTitles = contextFor(["compactControlAreaName", "stripControlAreaPrefix", "doorActionLabel"], {});
for (const [name, room, display, expected] of [
  ["Room Closet 1", "Bedroom 1", "Master Bedroom", "Closet Door"],
  ["Bedroom 6 Closet Door Sensor Opening", "Bedroom 6", "Chloe's Bedroom", "Closet Door"],
  ["Bedroom Door", "Bedroom 5", "Playroom", "Playroom Door"],
  ["Bedroom 3 Door Sensor", "Bedroom 3", "Maverick's Bedroom", "Maverick's Door"],
  ["Bedroom 3 Door", "Bedroom 3", "Maverick’s Bedroom", "Maverick’s Door"],
  ["Patio Window", "Kitchen", "Kitchen", "Patio Window"],
]) assert.equal(doorTitles.doorActionLabel({friendly_name: name}, room, display), expected);
for (const owner of ["Bailey's", "Boy's", "Chloe's"]) {
  for (const deviceName of [`${owner} Switch`, `${owner} Bedroom Switch`, "Bedroom 6 Switch"]) {
    const parts = controlTitles.controlDeviceParts({area: `${owner} Bedroom`, device_name: deviceName, original_name: "Switch 2", entity_id: "switch.bedroom_6_switch_2"}, "Bedroom 6");
    assert.equal(parts.deviceName, `${owner} Bedroom Switch`);
    assert.equal(parts.channelLabel, "Button 2");
  }
}

const bedroomTargets = contextFor(["bedroomActionCatalog"], {
  normalizedActionRoomName: value => String(value || "").toLowerCase(),
  actionTargetBelongsToRoom: () => false,
});
const targetCatalog = Object.fromEntries(["light_groups", "entity_targets", "individual_lights", "room_modes", "wake_overrides"].map(key => [key, [
  {area: "Bedroom 2", entity_id: "local"},
  {area: "Bailey's Bedroom", entity_id: "alias"},
  {area: "Kitchen", entity_id: "remote"},
]]));
const bedroomFiltered = bedroomTargets.bedroomActionCatalog({room: "Bedroom 2", display_name: "Bailey's Bedroom", action_catalog: targetCatalog});
for (const values of Object.values(bedroomFiltered)) assert.equal(values.map(value => value.entity_id).join(","), "local,alias");
const commonFiltered = bedroomTargets.bedroomActionCatalog({room: "Kitchen", action_catalog: targetCatalog});
assert.equal(commonFiltered.light_groups.map(value => value.entity_id).join(","), "remote");
for (const key of ["entity_targets", "individual_lights", "room_modes", "wake_overrides"]) assert.equal(commonFiltered[key], targetCatalog[key]);
assert.equal(targetCatalog.light_groups.length, 3);
const commonSwitchFiltered = bedroomTargets.bedroomActionCatalog({room: "Kitchen", switchActionPicker: true, action_catalog: targetCatalog});
assert.equal(commonSwitchFiltered.individual_lights.length, 0);
assert.equal(commonSwitchFiltered.room_modes.length, 0);
assert.equal(commonSwitchFiltered.entity_targets, targetCatalog.entity_targets);
const bedroomSwitchFiltered = bedroomTargets.bedroomActionCatalog({room: "Bedroom 2", display_name: "Bailey's Bedroom", switchActionPicker: true, action_catalog: targetCatalog});
assert.equal(bedroomSwitchFiltered.individual_lights.length, 0);
assert.equal(bedroomSwitchFiltered.room_modes.length, 2);
const bathroomCatalog = Object.fromEntries(Object.keys(targetCatalog).map(key => [key, [
  {area: "Bathroom 1", entity_id: "bath-local"},
  {area: "Master Bathroom", original_area: "Bathroom 1", entity_id: "bath-alias"},
  {area: "Bathroom 2", entity_id: "bath-other"},
  {area: "Kitchen", entity_id: "kitchen"},
]]));
const bathroomFiltered = bedroomTargets.bedroomActionCatalog({room: "Bathroom 1", display_name: "Master Bathroom", switchActionPicker: true, action_catalog: bathroomCatalog});
for (const [key, values] of Object.entries(bathroomFiltered)) assert.equal(values.map(value => value.entity_id).join(","), key === "individual_lights" ? "" : "bath-local,bath-alias");
const bathroomLabels = contextFor(["actionCatalogOptionMarkup"], {
  targetEntityId: entity => entity.entity_id,
  actionTargetBelongsToRoom: () => true,
  localActionTargetName: (entity, payload, name) => name,
  lightTargetName: entity => entity.friendly_name || "Exhaust Fan",
  normalizedActionRoomName: value => String(value).toLowerCase(),
  actionCatalogSelectionAttributes: () => "",
  escapeHtml: value => value,
});
const fanOption = bathroomLabels.actionCatalogOptionMarkup({entity_id: "fan.exhaust", area: "Downstairs Bathroom"}, "entity_target:fan.exhaust", new Set(), new Map([["fan.exhaust", "Exhaust Fan — Downstairs Bathroom"]]), {room: "Downstairs Bathroom", switchActionPicker: true});
assert(fanOption.includes(">Exhaust Fan</option>"));
assert(!fanOption.includes("Downstairs Bathroom"));
for (const room of ["Dining Room", "Downstairs Bathroom"]) {
  const option = bathroomLabels.actionCatalogOptionMarkup({entity_id: "light.room_all_lights", friendly_name: "All Lights", area: room}, "light_group:light.room_all_lights", new Set(), new Map([["light.room_all_lights", "All Lights"]]), {room, switchActionPicker: true});
  assert(option.includes(`>All ${room} Lights</option>`));
  assert(option.includes('data-action-name="All Lights"'));
}
assert.equal(bathroomCatalog.individual_lights.length, 4);

const fanPlugTargets = contextFor(["isFanOrPlugTarget"], {});
const fanDedup = contextFor(["uniqueFanPlugTargets"], {});
const linkedFans = [{entity_id: "switch.fan", domain: "switch", wired_load_ids: ["fan.floor"]}, {entity_id: "fan.floor", domain: "fan"}, {entity_id: "fan.other", domain: "fan"}];
const uniqueFans = fanDedup.uniqueFanPlugTargets(linkedFans);
assert.equal(uniqueFans.length, 2);
assert.equal(uniqueFans[0].action_aliases.join(","), "switch.fan");
assert.equal(linkedFans.length, 3);
assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "fan"}), true);
assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "switch", device_class: "outlet", device_name: "Smart Switch", friendly_name: "Office Speaker"}), true);
for (const friendly_name of ["Downstairs Bathroom Switch Switch 1", "Downstairs Bathroom Switch Switch 2", "Bathroom Button 1", "Switch One"]) {
  assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "switch", device_class: "outlet", device_name: "Wall Outlet Switch", friendly_name}), false);
}
assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "switch", device_class: "outlet", friendly_name: "Desk Plug Switch 1"}), true);
assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "switch", device_name: "Bedroom Plug"}), true);
assert.equal(fanPlugTargets.isFanOrPlugTarget({domain: "switch", device_name: "Bedroom Switch", friendly_name: "Switch 2"}), false);

const wiredSummary = contextFor(["actionMultiSelectSummary"], {});
const wiredPicker = contextFor(["wiredLoadDisplayName", "renderActionCatalogSelect"], {escapeHtml: value => value, renderActionCatalogOptions: () => ""});
const renamedBathroom = {room: "Bathroom 1", display_name: "Master Bathroom"};
assert.equal(wiredPicker.wiredLoadDisplayName("Bathroom 1 Toilet Exhaust Fan", renamedBathroom), "Master Bathroom Toilet Exhaust Fan");
assert.equal(wiredPicker.wiredLoadDisplayName("Bathroom 10 Exhaust Fan", renamedBathroom), "Bathroom 10 Exhaust Fan");
assert.equal(wiredPicker.wiredLoadDisplayName("Master Bathroom Toilet Exhaust Fan", renamedBathroom), "Master Bathroom Toilet Exhaust Fan");
const wiredMarkup = wiredPicker.renderActionCatalogSelect({entities: [{entity_id: "switch.closet", wired_load_ids: ["light.closet"], wired_load_names: {"light.closet": "Master Bedroom Closet Light"}}], action_catalog: {}}, "switch.closet", "", "switch.closet");
assert(wiredMarkup.includes("Master Bedroom Closet Light"), "Wired load remains visible without an action catalog entry");
const wiredSelect = {dataset: {wiredLoadNames: '["Closet Light"]'}, selectedOptions: []};
assert.equal(wiredSummary.actionMultiSelectSummary(wiredSelect), "Closet Light");
wiredSelect.selectedOptions = [{value: "light_group:light.vanity", textContent: "Vanity Light"}];
assert.equal(wiredSummary.actionMultiSelectSummary(wiredSelect), "Closet Light, Vanity Light");
wiredSelect.selectedOptions = [];
assert.equal(wiredSummary.actionMultiSelectSummary(wiredSelect), "Closet Light");

const compactSummary = { textContent: "" };
const compactId = { textContent: "" };
const compactPicker = {
  querySelectorAll: () => [],
  querySelector: selector => selector === ".action-multi-summary-text" ? compactSummary : selector === ".action-multi-summary-id" ? compactId : null,
};
let onSwitchesPage = true;
const compactSelect = {
  selectedOptions: [{ value: "light_group:light.bedroom_fan" }],
  classList: { contains: () => false },
  closest: selector => selector === ".action-multi-picker" ? compactPicker : onSwitchesPage,
};
const compactActions = contextFor(["syncActionMultiPicker"], {
  actionMultiSelectSummary: () => "Bailey's Bedroom Fan Lights",
  actionMultiSelectIds: () => "light_group:light.bedroom_fan",
});
compactActions.syncActionMultiPicker(compactSelect);
assert.equal(compactSummary.textContent, "Bailey's Bedroom Fan Lights");
assert.equal(compactId.textContent, "");
assert.equal(compactSelect.selectedOptions[0].value, "light_group:light.bedroom_fan");
onSwitchesPage = false;
compactActions.syncActionMultiPicker(compactSelect);
assert.equal(compactId.textContent, "light_group:light.bedroom_fan");

const hostEvents = new Map();
const attributes = new Map([["style", "width: 300px"]]);
let visiblePopover = false;
const frame = {
  getAttribute: name => attributes.get(name) ?? null,
  setAttribute: (name, value) => attributes.set(name, value),
  removeAttribute: name => attributes.delete(name),
  style: {setProperty: () => {}},
  showPopover: () => { visiblePopover = true; },
  hidePopover: () => { visiblePopover = false; },
};
let pushedPath;
const host = {
  document: {querySelector: name => name === "home-assistant" ? {} : null},
  location: {pathname: "/local_future_homes_tech_app"},
  history: {pushState: (_state, _title, path) => {pushedPath = path;}},
  CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
  dispatchEvent: event => {assert.equal(event.type, "location-changed");},
  addEventListener: (type, callback) => hostEvents.set(type, callback),
  removeEventListener: type => hostEvents.delete(type),
};
const embeddedWindow = {self:{}, top:host, frameElement:frame, addEventListener: () => {}};
const navigation = contextFor(["enterKioskMode", "exitToHomeAssistantSettings"], {
  window:embeddedWindow, HOME_ASSISTANT_SETTINGS_PATH:"/config",
});
assert.equal(navigation.enterKioskMode(), false);
assert.equal(visiblePopover, true);
navigation.exitToHomeAssistantSettings();
assert.equal(pushedPath, "/config");
assert.equal(visiblePopover, false);
assert.equal(attributes.get("style"), "width: 300px");
assert.equal(attributes.has("popover"), false);
assert.equal(hostEvents.size, 0);
navigation.enterKioskMode();
host.location.pathname = "/config";
hostEvents.get("popstate")();
assert.equal(visiblePopover, false);
assert.equal(hostEvents.size, 0);
frame.showPopover = undefined;
navigation.enterKioskMode();
navigation.exitToHomeAssistantSettings("/config/updates");
assert.equal(pushedPath, "/config/updates");
assert(/updateAppButton\.addEventListener\("click", \(\) => \{\s+if \(betaUpdateVersion\) \{\s+runSafely\(installBetaUpdate, "Beta update"\);\s+return;\s+\}\s+exitToHomeAssistantSettings\("\/config\/updates"\);/.test(source));

let resolveRead;
let reads = 0;
const gateway = contextFor(["requestJson"], {
  apiReadPromises: new Map(),
  performJsonRequest: () => { reads += 1; return new Promise(resolve => { resolveRead = resolve; }); },
});
const first = gateway.requestJson("api/security/status");
const second = gateway.requestJson("api/security/status");
assert.equal(reads, 1);
resolveRead({ok:true});
await Promise.all([first, second]);
assert.equal(gateway.apiReadPromises.size, 0);
gateway.performJsonRequest = async () => { reads += 1; return {ok:true}; };
await Promise.all([gateway.requestJson("api/save", {method:"POST"}), gateway.requestJson("api/save", {method:"POST"})]);
assert.equal(reads, 3);

const timers = [];
const idleTasks = [];
let loaderRuns = 0;
const idle = contextFor(["runWhenIdle"], {
  window: { setTimeout: (callback, delay) => timers.push({callback, delay}), requestIdleCallback: callback => idleTasks.push(callback) },
  runSafely: loader => loader(),
});
idle.runWhenIdle(() => { loaderRuns += 1; }, "background", 4200);
assert.equal(loaderRuns, 0);
assert.equal(idleTasks.length, 0);
assert.equal(timers[0].delay, 4200);
timers[0].callback();
idleTasks[0]();
assert.equal(loaderRuns, 1);

const view = contextFor(["loaderForView"], {loadRoomConfigurator: force => force});
assert.equal(await view.loaderForView("rooms", true)(), true);
assert.equal(await view.loaderForView("rooms", false)(), false);

const updates = [];
const live = contextFor(["watchLiveStateRevisions"], {
  liveStateFeedRunning: false, liveRevision: 900,
  requestJson: async () => { live.liveStateFeedRunning = false; return {changed:true,resync:true,revision:2,channels:[],areas:[]}; },
  scheduleLiveStateRefresh: (...args) => updates.push(args),
});
await live.watchLiveStateRevisions();
assert.equal(live.liveRevision, 2);
assert.equal(updates.length, 1);

for (const [name, stateName, loader, activeView] of [
  ["refreshLightingWhileVisible", "lightingRefreshInFlight", "loadLighting", "lighting"],
  ["refreshSecurityWhileVisible", "securityRefreshInFlight", "loadSecurity", "security"],
]) {
  const fallback = contextFor([name], {activeView, document:{hidden:false}, [stateName]:false, [loader]:async () => {throw new Error("offline");}});
  await assert.rejects(fallback[name](), /offline/);
  assert.equal(fallback[stateName], false);
}

const temperature = contextFor(["loadBrandTemperature"], {requestJson:async () => ({temperature:null}), brandTemperature:{textContent:""}});
await temperature.loadBrandTemperature();
assert.equal(temperature.brandTemperature.textContent, "—");

const targetControl = {disabled:false, value:"button.chime_play_chime", checked:true};
const inactiveAlarmControls = [{disabled:true, checked:false}, {disabled:true, value:"5"}];
const inactiveAlarmRow = {dataset:{}, querySelectorAll: () => inactiveAlarmControls};
const alarmRowSync = contextFor(["syncFridgeAlarmRow"], {});
alarmRowSync.syncFridgeAlarmRow(inactiveAlarmRow);
assert.ok(inactiveAlarmControls.every(control => !control.disabled));
assert.equal(inactiveAlarmControls[0].checked, false);
inactiveAlarmRow.dataset.saving = "true";
alarmRowSync.syncFridgeAlarmRow(inactiveAlarmRow);
assert.ok(inactiveAlarmControls.every(control => control.disabled));
let completeSave;
let outputDisabled = false;
const fields = new Map([
  ['[data-fridge-field="enabled"]', {checked:true}],
  ['[data-fridge-field="delay_minutes"]', {value:"3"}],
  ['[data-fridge-field="alert_targets"]', targetControl],
  ['[data-fridge-field="alert_behavior"]', {value:"once"}],
]);
const row = {dataset:{entityId:"binary_sensor.fridge_door",kind:"door"}, querySelector: selector => fields.get(selector), querySelectorAll: () => [targetControl], closest: () => null};
const alarm = contextFor(["saveFridgeAlarm"], {
  selectedMultiValues: () => ["button.chime_play_chime"],
  setActionMultiSelectDisabled: (_target, disabled) => {outputDisabled = disabled;},
  saveJson: () => new Promise(resolve => { completeSave = resolve; }),
  roomConfiguratorPayloads: new Map(),
  settingsApiPayloads: new Map(),
  syncFridgeAlarmRow: () => {targetControl.disabled = false;},
});
const saving = alarm.saveFridgeAlarm(row);
assert.equal(targetControl.disabled, true);
assert.equal(row.dataset.saving, "true");
completeSave({settings:{}});
await saving;
assert.equal(targetControl.disabled, false);
assert.equal(row.dataset.saving, undefined);
const sectionRenders = [];
const roomEditors = contextFor(["isActualSwitchControl", "isInovelliEventControl", "roomControlPageRooms"], {});
const renamedRooms = {
  aliases: {"Bedroom 6": "Chloe's Bedroom", "Bedroom 1": "Master Bedroom"},
  entities: [
    {domain: "switch", device_name: "Bedroom 6 Switch", area: "Chloe's Bedroom", original_area: "Bedroom 6"},
    {domain: "event", device_name: "Bedroom 6 Switch", area: "Chloe's Bedroom", original_area: "Bedroom 6"},
    {domain: "switch", device_name: "Bedroom 1 Switch", area: "Master Bedroom", original_area: "Bedroom 1"},
    {domain: "switch", device_name: "Living Room Switch", area: "Living Room", original_area: "Living Room"},
    {domain: "switch", device_name: "Floor Fan", area: "Office", original_area: "Office"},
    {domain: "switch", device_name: "Unassigned Switch", area: ""},
  ],
};
assert.deepEqual(JSON.parse(JSON.stringify(roomEditors.roomControlPageRooms(renamedRooms, "switches"))), [
  {room: "Bedroom 6", displayName: "Chloe's Bedroom"},
  {room: "Living Room", displayName: "Living Room"},
  {room: "Bedroom 1", displayName: "Master Bedroom"},
  {room: "", displayName: "Unassigned"},
]);
const renamedDoorRooms = {...renamedRooms, entities: [{domain: "binary_sensor", area: "Chloe's Bedroom", original_area: "Bedroom 6"}]};
assert.equal(roomEditors.roomControlPageRooms(renamedDoorRooms, "doors")[0].room, "Bedroom 6");
const orderedDoors = roomEditors.roomControlPageRooms({
  aliases: {"Bedroom 6": "Chloe's Room"},
  entities: ["Pantry", "Upstairs Bathroom", "Bedroom 6", "Kitchen", "Master Bedroom Bathroom", "Bailey's Bedroom"].map(area => ({area})),
}, "doors");
assert.deepEqual(Array.from(orderedDoors, room => room.displayName), ["Bailey's Bedroom", "Chloe's Room", "Master Bedroom Bathroom", "Upstairs Bathroom", "Kitchen", "Pantry"]);
const presenceRooms = contextFor(["roomControlPageRooms"], {isPresenceSensor: () => true});
const orderedPresence = presenceRooms.roomControlPageRooms({
  aliases: {"Bedroom 6": "Chloe's Room"},
  entities: ["Pantry", "Upstairs Bathroom", "Bedroom 6", "Kitchen", "Master Bedroom Bathroom", "Bailey's Bedroom"].map(area => ({area})),
}, "presence");
assert.deepEqual(Array.from(orderedPresence, room => room.displayName), Array.from(orderedDoors, room => room.displayName));
const lazyContext = contextFor(["buildRoomConfiguratorBody", "hydrateRoomSection"], {
  roomSectionBuilders: new Map(), wakeRoutineCatalogs: new Map(),
  isFridgeAlarmRoom: () => false,
  isActualSwitchControl: entity => entity.domain === "switch",
  isInovelliEventControl: () => false, isPresenceSensor: () => true,
  escapeHtml: value => value, attachEditorCatalog: async () => {},
  ...Object.fromEntries(["renderRoomButtonsSection", "renderRoomDoorActionsSection", "renderRoomPresenceSection", "renderRoomModeSection", "renderRoomSwitchesSection", "renderWakeRoutinePanel"].map(name => [name, () => {sectionRenders.push(name); return "rendered";}])),
  document: {createElement: () => ({content: {firstElementChild: {attributes: [], innerHTML: "saved editor"}}})},
});
const lazyPayload = {room: "Bedroom", mode_type: "bedroom", entities: [{domain: "switch", device_id: "switch"}], buttons: [{}], door_sensors: [{}]};
const headers = lazyContext.buildRoomConfiguratorBody(lazyPayload);
assert.ok(!headers.includes("Room Modes"));
assert.equal(sectionRenders.length, 0);
assert.ok(!headers.includes("data-lazy-section"));
assert.ok(!headers.includes("Wake Up Routine"));
lazyContext.roomSectionBuilders.set("Bedroom", {payload: lazyPayload, sections: [["Test", true, () => {sectionRenders.push("test"); return "rendered";}]]});
const lazySection = {open: true, isConnected: true, dataset: {lazySection: "0"},
  closest: () => ({dataset: {room: "Bedroom"}}), setAttribute: () => {}};
await lazyContext.hydrateRoomSection(lazySection);
assert.deepEqual(sectionRenders, ["test"]);
lazySection.innerHTML = "unsaved draft";
await lazyContext.hydrateRoomSection(lazySection);
assert.equal(lazySection.innerHTML, "unsaved draft");
assert.equal(sectionRenders.length, 1);

let catalogRequests = 0;
const catalogContext = contextFor(["attachEditorCatalog"], {
  sharedEditorCatalog: null, sharedEditorCatalogPromise: null,
  requestJson: async () => { catalogRequests += 1; return {revision: "one", action_catalog: {lights: []}}; },
});
const firstRoom = {catalog_revision: "one"};
const secondRoom = {catalog_revision: "one"};
await Promise.all([catalogContext.attachEditorCatalog(firstRoom), catalogContext.attachEditorCatalog(secondRoom)]);
assert.equal(catalogRequests, 1);
await catalogContext.attachEditorCatalog({catalog_revision: "one"});
assert.equal(catalogRequests, 1);
assert.equal(firstRoom.action_catalog, secondRoom.action_catalog);
await catalogContext.attachEditorCatalog({catalog_revision: "two"});
assert.equal(catalogRequests, 2);
const staleRoom = {catalog_revision: "outdated"};
await catalogContext.attachEditorCatalog(staleRoom);
assert.equal(staleRoom.catalog_revision, "one");
assert.equal(catalogRequests, 3);
await catalogContext.attachEditorCatalog(staleRoom);
assert.equal(catalogRequests, 3);
const modeRequests = [];
const modePayloads = new Map([["api/room-modes", {rooms: [{name: "Bedroom 2"}], catalog: {bedroom: [{id: "sleep", label: "Sleep"}]}, settings: {}}], ["api/room-scenes", {scenes: ["stale"]}]]);
const modeCheckbox = {checked: true, dataset: {roomMode: "sleep"}};
const modeSaveButton = {};
const modeFeedback = {};
const modeErrorText = {};
const modeErrorBox = {hidden: true, querySelector: () => modeErrorText};
const modeAttributes = new Map();
const modeCard = {dataset: {area: "Bedroom 2"}, setAttribute: (name, value) => modeAttributes.set(name, value), querySelectorAll: () => [modeCheckbox], querySelector: selector => selector === ".room-mode-save" ? modeSaveButton : selector === ".room-mode-save-error" ? modeErrorBox : modeFeedback};
const modeContext = contextFor(["saveRoomModes", "invalidateRoomModeDependents"], {
  settingsApiPayloads: modePayloads,
  roomModeSettingsRevision: 0,
  activeView: "room-modes", activeSceneSubpage: "room-scenes",
  invalidateApiPayload: path => modePayloads.delete(path),
  sharedEditorCatalog: {}, roomConfiguratorIndex: {}, roomConfiguratorPayloads: new Map([["Bedroom 2", {}]]),
  loadedViews: new Set(["scenes", "rooms"]), roomModeState: {},
  saveJson: async (path, payload) => {modeRequests.push({path, payload}); return {settings: {"Bedroom 2": ["sleep"]}};},
  saveErrorMessage: error => error.message,
});
await modeContext.saveRoomModes(modeCard);
assert.equal(modeRequests.length, 1);
assert.equal(modeRequests[0].path, "api/room-modes");
assert.equal(modeRequests[0].payload.enabled_modes[0], "sleep");
assert.equal(modeRequests[0].payload.mode_scope, "room");
assert.equal(modeCheckbox.disabled, false);
assert.ok(modePayloads.get("api/room-modes").rooms);
assert.equal(modePayloads.has("api/room-scenes"), false);
assert.equal(modeContext.loadedViews.has("scenes"), false);
assert.equal(modeContext.sharedEditorCatalog, null);
assert.equal(modeContext.roomModeSettingsRevision, 1);
assert.equal(modeErrorBox.hidden, true);
assert.equal(modeFeedback.textContent, "Room modes saved.");
assert.equal(modeAttributes.get("aria-busy"), "false");
modeContext.saveJson = async () => {throw new Error("Connection failed");};
await modeContext.saveRoomModes(modeCard);
assert.equal(modeErrorBox.hidden, false);
assert.equal(modeErrorText.textContent, "Connection failed");
assert.equal(modeCheckbox.checked, true);
assert.equal(modeCheckbox.disabled, false);
assert.equal(modeSaveButton.disabled, false);
modeContext.saveJson = async () => ({settings: {"Bedroom 2": ["sleep"]}});
await modeContext.saveRoomModes(modeCard);
assert.equal(modeErrorBox.hidden, true);

let sceneResponse;
let sceneLoads = 0;
const sceneLoadContext = contextFor(["loadRoomScenes"], {
  roomSceneDefinitions: new Map(), roomSceneCatalog: {},
  roomModeSettingsRevision: 0, activeSceneSubpage: "room-scenes", sceneCount: {},
  roomSceneState: {classList: {remove: () => {}, add: () => {}}}, roomSceneList: {children: []},
  loadApiPayload: async () => {
    sceneLoads += 1;
    if (sceneLoads === 1) return new Promise(resolve => {sceneResponse = resolve;});
    return {scenes: [{display_name: "New Room", label: "Sleep"}]};
  },
  attachEditorCatalog: async () => {}, invalidateApiPayload: () => {}, beginPageLoad: () => () => {},
  renderRoomSceneCard: scene => scene.display_name, enhanceActionMultiSelects: () => {},
});
const pendingScenes = sceneLoadContext.loadRoomScenes();
sceneLoadContext.roomModeSettingsRevision += 1;
sceneResponse({scenes: [{display_name: "Stale Room", label: "Sleep"}]});
await pendingScenes;
assert.equal(sceneLoads, 2);
assert.equal(sceneLoadContext.roomSceneList.innerHTML, "New Room");

const alarmOptions = [{id: "armed_away", label: "Armed Away"}, {id: "armed_stay_kids", label: "Armed Stay Kids"}, {id: "armed_stay_adult", label: "Armed Stay Adult"}, {id: "disarmed", label: "Disarmed"}];
const renderContext = contextFor(["alarmDoorState", "renderRoomModeCard", "renderRoomSceneCard", "renderRoomSceneEditor", "rgbHex", "lightColorLabel"], {
  alarmModes: alarmOptions, alarmModeIds: new Set(alarmOptions.map(mode => mode.id)),
  escapeHtml: value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;"),
  roomSceneTargetOptions: () => '<option value="light.one" selected>Bedroom Light</option>',
});
const modeMarkup = renderContext.renderRoomModeCard({name: "Bedroom 2", display_name: "Bailey's Bedroom", mode_type: "bedroom"}, {bedroom: [{id: "sleep", label: "Sleep"}, {id: "movie", label: "Movie"}]}, {"Bedroom 2": ["sleep"]});
assert.ok(modeMarkup.includes('data-room-mode="sleep" checked'));
assert.ok(!modeMarkup.includes('data-room-mode="movie" checked'));
assert.ok(modeMarkup.includes("Bailey's Bedroom"));
const separatedMarkup = renderContext.renderRoomModeCard({name: "Bedroom 2", mode_type: "bedroom"}, {bedroom: [...alarmOptions, {id: "sleep", label: "Sleep"}]}, {"Bedroom 2": ["armed_away", "sleep"]});
assert.ok(!separatedMarkup.includes('data-room-mode="armed_away"'));
assert.ok(!separatedMarkup.includes("room-mode-card-footer"));
assert.ok(!separatedMarkup.includes("enabled"));
assert.ok(separatedMarkup.includes('class="room-mode-save-error" role="alert" hidden'));
assert.ok(separatedMarkup.includes('aria-live="polite"'));
assert.equal(renderContext.alarmDoorState("off").className, "is-closed");
assert.equal(renderContext.alarmDoorState("on").label, "Open");
assert.equal(renderContext.alarmDoorState("unknown").label, "Unavailable");

const lightingLabelContext = contextFor(["lightingGroupLabel"], {});
assert.equal(lightingLabelContext.lightingGroupLabel({friendly_name: "Dining Room Lights"}, "Dining Room"), "Dining Room Lights");
assert.equal(lightingLabelContext.lightingGroupLabel({friendly_name: "Dining Room All Lights"}, "Dining Room"), "All Lights");
assert.equal(lightingLabelContext.lightingGroupLabel({friendly_name: "Bedroom 4 Fan Lights"}, "Bedroom 4"), "Fan Lights");
const lightingOrderContext = contextFor(["lightingAreaSortRank", "compareLightingAreas"], {});
const lightingRooms = ["Master Bathroom", "Chloe's Bedroom", "Outside Perimeter", "Closet 10", "Kitchen", "Closet 2", "Bailey's Bedoom", "Dining Room", "Patio"];
assert.deepEqual(lightingRooms.sort(lightingOrderContext.compareLightingAreas), ["Dining Room", "Kitchen", "Closet 2", "Closet 10", "Outside Perimeter", "Patio", "Bailey's Bedoom", "Chloe's Bedroom", "Master Bathroom"]);
const masonryCards = [80, 290, 150].map(height => ({height, style: {}, getBoundingClientRect() {return {height: this.height};}}));
const masonryClasses = new Set();
const masonryGrid = {clientWidth: 1000, children: masonryCards, classList: {add: value => masonryClasses.add(value)}};
let lightingFrames = 0;
const masonryContext = contextFor(["layoutLightingCards", "scheduleLightingLayout"], {
  lightingAreaGrid: masonryGrid, lightingLayoutFrame: 0,
  getComputedStyle: () => ({rowGap: "10px"}), requestAnimationFrame: () => ++lightingFrames,
});
masonryContext.scheduleLightingLayout();
masonryContext.scheduleLightingLayout();
assert.equal(lightingFrames, 1);
masonryContext.layoutLightingCards();
assert.equal(masonryCards[0].style.gridRowEnd, "span 9");
assert.equal(masonryCards[1].style.gridRowEnd, "span 28");
assert.ok(masonryClasses.has("is-masonry"));
masonryCards[0].height = 130;
masonryContext.layoutLightingCards();
assert.equal(masonryCards[0].style.gridRowEnd, "span 13");
masonryGrid.clientWidth = 0;
masonryCards[0].height = 0;
masonryContext.layoutLightingCards();
assert.equal(masonryCards[0].style.gridRowEnd, "span 13");
const sceneMarkup = renderContext.renderRoomSceneCard({area: "Bedroom 2", display_name: "<Bedroom>", mode: "sleep", label: "Sleep", configured: true, settings: {brightness_pct: 0, color_mode: "rgb", color_rgb: [1, 2, 3]}}, {});
assert.ok(sceneMarkup.includes("&lt;Bedroom>"));
assert.ok(!sceneMarkup.includes("room-scene-target-select"));
const sceneEditor = renderContext.renderRoomSceneEditor({area: "Bedroom 2", display_name: "Bailey's Bedroom", mode: "sleep", label: "Sleep", configured: true, settings: {brightness_pct: 0, color_mode: "rgb", color_rgb: [1, 2, 3]}}, {});
assert.ok(sceneEditor.includes('data-schedule-field="brightness" value="0"'));
assert.ok(sceneEditor.includes('value="#010203"'));
assert.ok(sceneEditor.includes("room-scene-save"));
assert.ok(sceneEditor.includes("room-scene-target-select"));
let sceneEditorRenders = 0;
const lazySceneContext = contextFor(["hydrateRoomSceneCard"], {
  roomSceneDefinitions: new Map([[JSON.stringify(["Bedroom 2", "sleep"]), {}]]), roomSceneCatalog: {},
  renderRoomSceneEditor: () => {sceneEditorRenders += 1; return "editor";}, enhanceActionMultiSelects: () => {},
});
const sceneBody = {};
const lazySceneCard = {open: false, dataset: {area: "Bedroom 2", mode: "sleep"}, querySelector: () => sceneBody};
lazySceneContext.hydrateRoomSceneCard(lazySceneCard);
assert.equal(sceneEditorRenders, 0);
lazySceneCard.open = true;
lazySceneContext.hydrateRoomSceneCard(lazySceneCard);
assert.equal(sceneEditorRenders, 1);
sceneBody.innerHTML = "unsaved changes";
lazySceneCard.open = false;
lazySceneContext.hydrateRoomSceneCard(lazySceneCard);
lazySceneCard.open = true;
lazySceneContext.hydrateRoomSceneCard(lazySceneCard);
assert.equal(sceneBody.innerHTML, "unsaved changes");
assert.equal(sceneEditorRenders, 1);
console.log("Browser behavior regressions passed, including lazy rooms, catalog reuse, mode autosave, scene invalidation and scene controls.");
