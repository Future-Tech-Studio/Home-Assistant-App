const sections = { people: "People", reservations: "Reservations", groups: "Access Groups", panels: "Wall Panels", activity: "Activity" };
const labels = { active: "Active", disabled: "Disabled", archived: "Archived", scheduled: "Scheduled", expired: "Expired", revoked: "Revoked", deleted: "Deleted", planned: "Setup needed", confirmed: "Confirmed", draft: "Draft", cancelled: "Cancelled", upcoming: "Upcoming", completed: "Completed", "in stay": "In stay" };

export function localDateTime(value, zone) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value));
  const fields = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${fields.year}-${fields.month}-${fields.day}T${fields.hour}:${fields.minute}`;
}

export function createUsersPage(container) {
  let catalog;
  let collection = "people";
  let nextOffset = null;
  let generation = 0;
  let active = false;
  let dialog;
  let secretTimer;
  const toolbar = document.createElement("nav");
  toolbar.id = "users-access-toolbar";
  toolbar.className = "scene-toolbar-nav";
  toolbar.setAttribute("aria-label", "Users sections");
  const content = element("div", "access-page");
  const status = element("p", "access-status");
  status.setAttribute("role", "status");
  const list = element("div", "access-list");
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search people";
  search.setAttribute("aria-label", "Search Users records");
  const add = button("Add person", () => edit());
  const find = button("Search", () => load());
  const more = button("Load more", () => load(true));
  const controls = element("div", "access-list-tools");
  controls.append(search, find, add);
  const notice = element("p", "access-note", "Private access profiles—not Home Assistant logins. Locks and wall-panel activation remain disconnected until hardware testing.");
  content.append(notice, controls, status, list, more);
  container.replaceChildren(content);
  toolbar.append(element("h1", "scene-toolbar-heading", "Users"), element("span", "scene-toolbar-divider", "|"));
  for (const [key, title] of Object.entries(sections)) {
    const tab = button(title, () => { collection = key; search.value = ""; closeDialog(); load(); });
    tab.className = "scene-toolbar-tab";
    tab.dataset.accessSection = key;
    toolbar.append(tab);
  }
  document.querySelector(".page-actions-primary").prepend(toolbar);
  search.addEventListener("keydown", event => { if (event.key === "Enter") load(); });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(text, handler, danger = false) {
    const node = element("button", danger ? "access-button danger" : "access-button", text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function roomNames(identifiers = []) {
    return identifiers.map(identifier => catalog?.rooms.find(room => room.id === identifier)?.name || "Unavailable room").join(", ");
  }

  function badge(value) {
    const node = element("span", "access-badge", labels[value] || value);
    node.dataset.state = value;
    return node;
  }

  function timeLabel(value) {
    return value ? new Intl.DateTimeFormat(undefined, { timeZone: catalog.timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "No time limit";
  }

  async function api(resource, payload) {
    let headers = { Accept: "application/json" };
    if (payload !== undefined) {
      const session = await api("session");
      headers = { ...headers, "Content-Type": "application/json", "X-FHT-Access-CSRF": session.csrf };
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 35000);
    try {
      const response = await fetch(`api/access/${resource}`, { method: payload === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", headers, body: payload === undefined ? undefined : JSON.stringify(payload), signal: controller.signal });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Users request failed.");
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The request timed out. Reload this record before retrying a change; it may have saved.");
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function report(error, node = status) {
    node.textContent = error.message || "Unable to complete the change.";
    node.classList.add("error");
  }

  async function load(append = false) {
    const ticket = ++generation;
    toolbar.querySelectorAll("[data-access-section]").forEach(tab => tab.setAttribute("aria-pressed", String(tab.dataset.accessSection === collection)));
    search.hidden = find.hidden = collection === "activity";
    search.placeholder = `Search ${sections[collection].toLowerCase()}`;
    add.hidden = collection === "activity";
    add.textContent = ({ people: "Add person", reservations: "Add reservation", groups: "Add access group", panels: "Plan wall panel" })[collection] || "";
    status.textContent = "Loading…";
    status.classList.remove("error");
    more.hidden = true;
    if (!append) list.replaceChildren();
    try {
      if (!catalog) catalog = await api("catalog");
      const result = await api(`${collection}?search=${encodeURIComponent(search.value)}&offset=${append ? nextOffset || 0 : 0}`);
      if (ticket !== generation || !active) return;
      result.items.forEach(record => list.append(recordCard(record)));
      nextOffset = result.next_offset;
      more.hidden = nextOffset === null;
      status.textContent = result.total ? "" : collection === "activity" ? "Changes will appear here. PIN values are never recorded." : `No ${sections[collection].toLowerCase()} yet.`;
    } catch (error) { if (ticket === generation) report(error); }
  }

  function recordCard(record) {
    const card = element("article", "access-card");
    const heading = element("div", "access-card-heading");
    const description = element("div", "access-card-description");
    if (collection === "activity") {
      const title = record.action.replaceAll("_", " ").replaceAll(".", " · ");
      heading.append(element("h2", "", title));
      description.textContent = `${record.subject_name || ""} · ${record.actor_name} · ${timeLabel(record.created)}${record.detail ? ` · ${record.detail}` : ""}`;
      card.append(heading, description);
      return card;
    }
    heading.append(element("h2", "", record.name));
    if (record.status) heading.append(badge(record.display_status || record.status));
    heading.append(button("Manage", () => edit(record.id)));
    if (collection === "people") description.textContent = `${catalog.roles[record.role]}${record.rooms.length ? ` · ${roomNames(record.rooms)}` : " · No bedroom assigned"}`;
    if (collection === "reservations") description.textContent = `${record.guest_name} · ${roomNames(record.rooms)} · ${timeLabel(record.start_at)} → ${timeLabel(record.end_at)}`;
    if (collection === "groups") description.textContent = `${record.resources.length} selected door / lock references · ${record.permissions.length} permissions · Not provisioned to hardware`;
    if (collection === "panels") description.textContent = `${record.model || "Model not chosen"} · ${roomNames(record.rooms) || "Room not assigned"} · Not enrolled`;
    card.append(heading, description);
    return card;
  }

  function closeDialog() {
    window.clearTimeout(secretTimer);
    if (!dialog) return;
    dialog.querySelectorAll("input").forEach(input => { if (input.type === "password" || input.dataset.secret) input.value = ""; });
    dialog.close();
    dialog.remove();
    dialog = null;
  }

  function openDialog(title) {
    closeDialog();
    const node = element("dialog", "access-dialog");
    const heading = element("div", "access-dialog-heading");
    const caption = element("h2", "", title);
    caption.id = "access-dialog-title";
    node.setAttribute("aria-labelledby", caption.id);
    heading.append(caption, button("Close", closeDialog));
    const body = element("div", "access-dialog-body");
    const feedback = element("p", "access-status");
    feedback.setAttribute("role", "status");
    node.append(heading, feedback, body);
    document.body.append(node);
    node.addEventListener("cancel", event => { event.preventDefault(); closeDialog(); });
    dialog = node;
    node.showModal();
    return { node, body, feedback };
  }

  function field(parent, title, value = "", type = "text", required = false) {
    const label = element("label", "access-field");
    label.append(element("span", "", title));
    const input = document.createElement(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") input.type = type;
    input.value = value ?? "";
    input.required = required;
    input.maxLength = type === "textarea" ? 1000 : 160;
    if (type === "datetime-local") input.step = "60";
    label.append(input);
    parent.append(label);
    return input;
  }

  function select(parent, title, options, value) {
    const label = element("label", "access-field");
    label.append(element("span", "", title));
    const input = document.createElement("select");
    for (const [key, name] of Object.entries(options)) {
      const option = element("option", "", name);
      option.value = key;
      input.append(option);
    }
    if (value !== undefined) input.value = value;
    label.append(input);
    parent.append(label);
    return input;
  }

  function checks(parent, title, options, selected = []) {
    const box = element("fieldset", "access-checks");
    box.append(element("legend", "", title));
    const inputs = [];
    for (const [key, text] of Object.entries(options)) {
      const label = element("label", "access-check");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = key;
      input.checked = selected.includes(key);
      label.append(input, element("span", "", text));
      box.append(label);
      inputs.push(input);
    }
    if (!inputs.length) box.append(element("p", "access-note", "None available yet."));
    parent.append(box);
    return { value: () => inputs.filter(input => input.checked).map(input => input.value), set: values => inputs.forEach(input => { input.checked = values.includes(input.value); }) };
  }

  async function allOptions(type) {
    let offset = 0;
    const items = [];
    do {
      const result = await api(`${type}?offset=${offset}`);
      items.push(...result.items);
      offset = result.next_offset;
    } while (offset !== null);
    return items;
  }

  async function busy(view, action) {
    const controls = [...view.node.querySelectorAll("button,input,select,textarea")];
    controls.forEach(control => { control.disabled = true; });
    view.feedback.classList.remove("error");
    view.feedback.textContent = "Saving…";
    try { await action(); }
    catch (error) { report(error, view.feedback); }
    finally { controls.forEach(control => { control.disabled = false; }); }
  }

  async function edit(identifier, initial = {}) {
    const type = collection;
    const view = openDialog(identifier ? `Manage ${type === "people" ? "person" : sections[type].toLowerCase()}` : add.textContent);
    view.feedback.textContent = "Loading…";
    try {
      const record = identifier ? (await api(`${type}?id=${encodeURIComponent(identifier)}`)).record : initial;
      const groups = type === "people" || type === "reservations" ? await allOptions("groups") : [];
      if (dialog !== view.node) return;
      view.feedback.textContent = "";
      const form = element("form", "access-form");
      const row = element("div", "access-form-grid");
      form.append(row);
      const name = field(row, type === "reservations" ? "Stay name" : "Name", record.name || "", "text", true);
      const readers = { name: () => name.value };
      const roomOptions = Object.fromEntries(catalog.rooms.map(room => [room.id, room.name]));
      if (type === "people") {
        const role = select(row, "Role", catalog.roles, record.role || "resident");
        const state = select(row, "User status", { active: "Active", disabled: "Disabled", archived: "Archived" }, record.status || "active");
        const contact = field(row, "Contact (optional)", record.contact || "");
        const rooms = checks(form, "Assigned bedroom / rooms", roomOptions, record.rooms);
        const assignedGroups = checks(form, "Access groups", Object.fromEntries(groups.map(group => [group.id, group.name])), record.groups);
        const advanced = element("details", "access-advanced");
        advanced.append(element("summary", "", "Permissions and access schedule"));
        const permissions = checks(advanced, "Planned capabilities", catalog.capabilities, record.permissions || catalog.role_defaults[role.value]);
        advanced.append(element("p", "access-note", "These are access policies for future protected controls. They do not create a Home Assistant administrator or send commands to devices."));
        role.addEventListener("change", () => permissions.set(catalog.role_defaults[role.value]));
        const dates = element("div", "access-form-grid");
        const start = field(dates, `Access starts (${catalog.timezone})`, localDateTime(record.start_at, catalog.timezone), "datetime-local");
        const end = field(dates, "Access ends (blank for ongoing access)", localDateTime(record.end_at, catalog.timezone), "datetime-local");
        advanced.append(dates);
        const days = checks(advanced, "Recurring hours · leave days unchecked for no weekly restriction", { 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday" }, record.staff_schedule?.days);
        const hours = element("div", "access-form-grid");
        const hoursStart = field(hours, "From", record.staff_schedule?.start || "09:00", "time");
        const hoursEnd = field(hours, "Until", record.staff_schedule?.end || "17:00", "time");
        advanced.append(hours);
        form.append(advanced);
        const notes = field(form, "Notes (optional)", record.notes || "", "textarea");
        Object.assign(readers, { role: () => role.value, status: () => state.value, contact: () => contact.value, rooms: rooms.value,
          groups: assignedGroups.value, permissions: permissions.value, start_at: () => start.value, end_at: () => end.value,
          staff_schedule: () => ({ days: days.value(), start: hoursStart.value, end: hoursEnd.value }), notes: () => notes.value });
      } else if (type === "groups") {
        const resources = checks(form, "Doors and locks · planning references only", Object.fromEntries(catalog.resources.map(resource => [resource.id, `${resource.name}${resource.kind === "door_sensor" ? " (sensor only)" : ""}`])), record.resources);
        const permissions = checks(form, "Allowed operations on these resources", catalog.capabilities, record.permissions);
        form.append(element("p", "access-note", "A door sensor cannot unlock a door. These references do not install a credential or configure an alarm webhook."));
        Object.assign(readers, { resources: resources.value, permissions: permissions.value });
      } else if (type === "panels") {
        const model = select(row, "Display model", { "": "Choose later", "SONOFF NSPanel Pro": "SONOFF NSPanel Pro", "Shelly Wall Display XL": "Shelly Wall Display XL", "Other": "Other" }, record.model || "");
        const room = select(row, "Assigned room", { "": "Unassigned", ...roomOptions }, record.rooms?.[0] || "");
        const timeout = field(row, "Return to limited view after (seconds)", record.timeout || 60, "number", true);
        timeout.min = "15"; timeout.max = "300";
        const modules = checks(form, "Planned dashboard modules", { lights: "Lights", climate: "Climate", shades: "Shades", room_modes: "Room modes", alarm: "Protected alarm actions" }, record.modules);
        form.append(element("p", "access-note", "Configuration only. Device enrollment, panel PIN entry, and protected commands are not enabled in this release. No owner token is issued to a panel."));
        Object.assign(readers, { model: () => model.value, rooms: () => room.value ? [room.value] : [], timeout: () => Number(timeout.value), modules: modules.value });
      } else if (type === "reservations") {
        const people = await api("people");
        if (dialog !== view.node) return;
        const guestOptions = Object.fromEntries(people.items.filter(person => person.status === "active").map(person => [person.id, person.name]));
        if (record.person_id && !guestOptions[record.person_id]) guestOptions[record.person_id] = (await api(`people?id=${record.person_id}`)).record.name;
        const guest = select(row, "Guest", { "": "Choose a person", ...guestOptions }, record.person_id || "");
        guest.required = true;
        const guestSearch = field(row, "Find a person", "", "search");
        row.append(button("Find guest", async () => {
          try {
            const result = await api(`people?search=${encodeURIComponent(guestSearch.value)}`);
            const selected = guest.value;
            guest.replaceChildren(element("option", "", "Choose a person"));
            guest.options[0].value = "";
            result.items.filter(person => person.status === "active").forEach(person => { const option = element("option", "", person.name); option.value = person.id; guest.append(option); });
            guest.value = selected;
          } catch (error) { report(error, view.feedback); }
        }));
        guest.addEventListener("change", () => { if (!name.value && guest.value) name.value = `${guest.selectedOptions[0].textContent} stay`; });
        const state = select(row, "Reservation status", { draft: "Draft", confirmed: "Confirmed" }, record.status || "confirmed");
        const rooms = checks(form, "Reserved rooms · select every room for a whole-house booking", roomOptions, record.rooms);
        const assignedGroups = checks(form, "Guest access groups", Object.fromEntries(groups.map(group => [group.id, group.name])), record.groups);
        const dates = element("div", "access-form-grid");
        const start = field(dates, `Arrival (${catalog.timezone})`, localDateTime(record.start_at, catalog.timezone), "datetime-local", true);
        const end = field(dates, "Checkout · access ends at this exact time", localDateTime(record.end_at, catalog.timezone), "datetime-local", true);
        form.append(dates);
        const notes = field(form, "Booking reference / notes", record.notes || "", "textarea");
        Object.assign(readers, { person_id: () => guest.value, status: () => state.value, rooms: rooms.value, groups: assignedGroups.value, start_at: () => start.value, end_at: () => end.value, notes: () => notes.value });
        if (record.status === "cancelled") form.append(element("p", "access-note", "This stay is cancelled. Create a new reservation rather than reactivating its credentials."));
      }
      const footer = element("div", "access-form-footer");
      const save = element("button", "access-button primary", identifier ? "Save changes" : "Create");
      save.type = "submit";
      footer.append(save);
      if (identifier) footer.append(button(type === "reservations" ? "Cancel stay" : "Delete", () => {
        if (!window.confirm(type === "people" ? `Delete ${record.name}? Their PINs will be revoked and profile details removed. A non-secret history is retained. Their Home Assistant account is not changed.` : type === "reservations" ? "Cancel this stay and revoke its PINs?" : "Delete this configuration?")) return;
        busy(view, async () => { await api(`${type}/remove`, { id: record.id, revision: record.revision, confirmed: true }); closeDialog(); load(); });
      }, true));
      form.append(footer);
      form.addEventListener("submit", event => {
        event.preventDefault();
        busy(view, async () => {
          const payload = Object.fromEntries(Object.entries(readers).map(([key, read]) => [key, read()]));
          const result = await api(`${type}/save`, { ...payload, id: record.id, revision: record.revision, confirmed: true });
          if (dialog !== view.node) return;
          closeDialog();
          load();
          edit(result.record.id);
        });
      });
      view.body.append(form);
      if (identifier && (type === "people" || type === "reservations")) {
        const person = type === "people" ? record : (await api(`people?id=${record.person_id}`)).record;
        if (dialog !== view.node) return;
        credentialSection(view, record, person, type);
        if (type === "reservations") extensionSection(view, record);
      }
    } catch (error) { report(error, view.feedback); }
  }

  function credentialSection(view, record, person, type) {
    const section = element("section", "access-detail-section");
    section.append(element("h3", "", "PINs"), element("p", "access-note", "Not connected to locks or wall panels. PINs are shown once; replacements will be needed when physical lock provisioning is added."));
    if (type === "people" && person.role === "guest") {
      section.append(element("p", "access-note", "Create guest PINs from their confirmed reservation so checkout is enforced."));
      section.append(button("Add reservation", () => { collection = "reservations"; closeDialog(); load(); edit(null, { person_id: person.id, name: `${person.name} stay`, rooms: person.rooms, groups: person.groups }); }));
    } else if (person.status === "active" && (type === "people" || record.status === "confirmed")) {
      section.append(button("Create PIN", () => pinForm(view, record, person, type)));
    }
    for (const credential of record.credentials || []) {
      const card = element("div", "access-credential");
      const header = element("div", "access-card-heading");
      header.append(element("strong", "", credential.label), badge(credential.state));
      card.append(header, element("p", "access-note", `${timeLabel(credential.start_at)} → ${timeLabel(credential.end_at)} · No device installed`));
      const actions = element("div", "access-actions");
      if (["active", "scheduled"].includes(credential.state)) {
        actions.append(button("Test PIN", () => testForm(view, credential)));
        if (type === "reservations" || !credential.reservation_id) actions.append(button("Replace", () => pinForm(view, record, person, type, credential)));
        actions.append(button("Revoke", () => revoke(credential, false), true));
      }
      actions.append(button("Delete PIN", () => revoke(credential, true), true));
      card.append(actions);
      section.append(card);
    }
    view.body.append(section);

    function revoke(credential, remove) {
      if (!window.confirm(`${remove ? "Delete" : "Revoke"} this PIN? It cannot be restored or revealed afterward.`)) return;
      busy(view, async () => { await api("pin/revoke", { id: credential.id, revision: credential.revision, delete: remove, confirmed: true }); edit(record.id); });
    }
  }

  function pinForm(parent, record, person, type, replacement) {
    if (!window.confirm("Save any profile changes first. Continue to the secure PIN form?")) return;
    const view = openDialog(replacement ? "Replace PIN" : "Create PIN");
    const form = element("form", "access-form");
    const label = field(form, "PIN label", replacement?.label || "Access PIN", "text", true);
    const method = select(form, "PIN selection", { generate: "Generate a random 6-digit PIN", manual: "Enter a PIN manually" }, "generate");
    const pin = field(form, "New PIN · 6–10 digits", "", "password");
    pin.inputMode = "numeric";
    pin.autocomplete = "new-password";
    pin.maxLength = 10;
    pin.pattern = "[0-9]{6,10}";
    pin.closest("label").hidden = true;
    method.addEventListener("change", () => { pin.closest("label").hidden = method.value !== "manual"; pin.required = method.value === "manual"; });
    const submit = element("button", "access-button primary", replacement ? "Replace and revoke old PIN" : "Issue PIN");
    submit.type = "submit";
    form.append(element("p", "access-note", "This does not unlock a door or activate a wall panel. The PIN will be shown once and cleared when this window closes."), submit);
    form.addEventListener("submit", event => {
      event.preventDefault();
      busy(view, async () => {
        const result = await api("pin/issue", { person_id: person.id, person_revision: person.revision, reservation_id: type === "reservations" ? record.id : null,
          label: label.value, generate: method.value === "generate", pin: pin.value, replace_id: replacement?.id, revision: replacement?.revision, confirmed: true });
        pin.value = "";
        if (dialog !== view.node) return;
        view.body.replaceChildren(element("h3", "", "PIN created"));
        const revealed = field(view.body, "Record this PIN now", result.pin, "text");
        revealed.readOnly = true;
        revealed.dataset.secret = "true";
        revealed.classList.add("access-pin");
        result.pin = "";
        view.body.append(element("p", "access-note", "Shown only once. It disappears after 60 seconds or when you close this window. No lock or panel has been programmed."));
        view.feedback.textContent = "Saved securely.";
        view.body.append(button("Done", () => edit(record.id)));
        secretTimer = window.setTimeout(() => { revealed.value = ""; view.feedback.textContent = "PIN display cleared. Replace it if you did not record it."; }, 60000);
      });
    });
    view.body.append(form);
  }

  function testForm(parent, credential) {
    const view = openDialog("Test PIN · no device action");
    const form = element("form", "access-form");
    const pin = field(form, "PIN", "", "password", true);
    pin.autocomplete = "off";
    pin.inputMode = "numeric";
    pin.maxLength = 10;
    const submit = element("button", "access-button primary", "Check PIN and access window");
    submit.type = "submit";
    form.append(submit, element("p", "access-note", "This checks the saved PIN, current time, user status, reservation, and recurring hours. It never sends an alarm or lock command."));
    form.addEventListener("submit", event => {
      event.preventDefault();
      busy(view, async () => { const result = await api("pin/test", { id: credential.id, pin: pin.value }); pin.value = ""; view.feedback.textContent = result.message; });
    });
    view.body.append(form);
  }

  function extensionSection(view, record) {
    const section = element("section", "access-detail-section");
    section.append(element("h3", "", "Stay extensions"));
    if (record.status === "confirmed") {
      const form = element("form", "access-form");
      const end = field(form, `Requested checkout (${catalog.timezone})`, localDateTime(record.end_at, catalog.timezone), "datetime-local", true);
      const reason = field(form, "Reason", "", "text", true);
      const submit = element("button", "access-button", "Request extension");
      submit.type = "submit";
      form.append(submit, element("p", "access-note", "Requesting does not extend access. Approve the pending request after reviewing room availability."));
      form.addEventListener("submit", event => {
        event.preventDefault();
        busy(view, async () => { await api("extension", { reservation_id: record.id, revision: record.revision, new_end: end.value, reason: reason.value, confirmed: true }); edit(record.id); });
      });
      section.append(form);
    }
    for (const extension of record.extensions || []) {
      const row = element("div", "access-credential");
      row.append(element("strong", "", `${timeLabel(extension.new_end)} · ${extension.state}`), element("p", "access-note", extension.reason));
      if (extension.state === "pending") {
        const actions = element("div", "access-actions");
        for (const action of ["approve", "reject"]) actions.append(button(action === "approve" ? "Approve extension" : "Reject", () => {
          if (!window.confirm(`${action === "approve" ? "Approve" : "Reject"} this extension to ${timeLabel(extension.new_end)}?`)) return;
          busy(view, async () => { await api("extension", { id: extension.id, action, confirmed: true }); edit(record.id); load(); });
        }));
        row.append(actions);
      }
      section.append(row);
    }
    view.body.append(section);
  }

  return {
    async show() { active = true; await load(); },
    leave() { active = false; generation += 1; closeDialog(); list.replaceChildren(); search.value = ""; },
  };
}
