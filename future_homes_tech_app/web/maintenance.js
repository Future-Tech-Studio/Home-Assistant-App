const titles = { "safe-cleanup": "Safe Cleanup" };

function node(tag, text, className = "") {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  element.className = className;
  return element;
}

function button(text, action) {
  const element = node("button", text, "maint-button");
  element.type = "button";
  element.addEventListener("click", action);
  return element;
}

function date(value) {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString() : "Not observed";
}

async function api(route, payload, signal) {
  const headers = { Accept: "application/json" };
  if (payload !== undefined) {
    const sessionResponse = await fetch("api/access/session", { credentials: "same-origin", cache: "no-store", signal });
    const session = await sessionResponse.json();
    if (!sessionResponse.ok || !session.ok) throw new Error(session.error || "Administrator access required.");
    headers["X-FHT-Access-CSRF"] = session.csrf;
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`api/maintenance/${route}`, { method: payload === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", headers, body: payload === undefined ? undefined : JSON.stringify(payload), signal });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "Maintenance request failed.");
  return result;
}

export function createMaintenancePage(container) {
  let view = "";
  let generation = 0;
  let review;
  let dialog;
  let request;
  let busy = false;
  const selected = new Set();
  const toolbar = node("nav", undefined, "scene-toolbar-nav maint-toolbar");
  toolbar.setAttribute("aria-label", "Maintenance tools");
  const heading = node("h1", "", "scene-toolbar-heading");
  const refresh = button("Refresh", () => load());
  toolbar.append(heading, refresh);
  document.querySelector(".page-actions-primary").prepend(toolbar);
  const controls = node("div", undefined, "maint-controls");
  const scan = button("Scan unused helpers", () => scanReview());
  const archive = button("Archive selected", () => confirmArchive());
  const status = node("p", "", "maint-status");
  status.setAttribute("role", "status");
  const note = node("p", "", "maint-note");
  const list = node("div", undefined, "maint-list");
  controls.append(scan, archive);
  container.append(note, controls, status, list);

  function report(error) {
    status.textContent = error.name === "AbortError" ? "Request timed out. If you submitted a change, check Recovery before retrying." : error.message || "Unable to complete request.";
    status.classList.add("error");
  }

  async function run(task) {
    if (busy) return;
    const ticket = generation;
    busy = true;
    refresh.disabled = scan.disabled = archive.disabled = true;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 35000);
    status.classList.remove("error");
    try { await task(controller.signal, () => ticket === generation && !!view); }
    catch (error) { if (ticket === generation) report(error); }
    finally {
      clearTimeout(timeout);
      if (ticket === generation) {
        busy = false;
        refresh.disabled = scan.disabled = false;
        archive.disabled = selected.size === 0;
      }
    }
  }

  function card(title, key) {
    const item = node("article", undefined, "maint-card");
    if (key) item.dataset.key = key;
    item.append(node("h2", title));
    return item;
  }

  function badge(text, attention = false) {
    return node("span", text, `maint-badge${attention ? " attention" : ""}`);
  }

  async function load() {
    await run(async (signal, current) => {
      status.textContent = "Loading…";
      const result = await api("archives", undefined, signal);
      if (!current()) return;
      review = null;
      selected.clear();
      renderArchives(result);
      await loadRetired(current, signal);
    });
  }

  async function scanReview() {
    await run(async (signal, current) => {
      status.textContent = "Checking live helpers, current definitions and saved references…";
      const result = await api("review", undefined, signal);
      if (!current()) return;
      review = result;
      selected.clear();
      list.replaceChildren();
      const helpers = card("Unused helper review");
      helpers.append(node("p", result.limitations, "maint-note"));
      for (const item of result.items) {
        const row = node("label", undefined, "maint-check maint-report");
        const check = node("input");
        check.type = "checkbox";
        check.disabled = !item.eligible;
        check.addEventListener("change", () => {
          if (check.checked && selected.size >= 10) { check.checked = false; status.textContent = "Archive no more than ten helpers per reviewed batch."; return; }
          if (check.checked) selected.add(item.id); else selected.delete(item.id);
          archive.disabled = selected.size === 0;
        });
        const text = node("div");
        text.append(node("strong", item.name), node("p", item.id, "maint-note"), node("p", item.eligible ? "Not provided; no definition or reference found in scanned sources" : item.reasons.join(" · "), "maint-note"));
        if (item.references.length) text.append(node("p", item.references.join(", "), "maint-note"));
        row.append(check, text);
        helpers.append(row);
      }
      if (!result.items.length) helpers.append(node("p", "No restored FHT helpers found."));
      list.append(helpers);
      const groups = card("Duplicate group review");
      for (const item of result.duplicates) groups.append(node("p", `${item.groups.map(group => group.name).join(" / ")} — same ${item.members.length} direct members. Preserve assignments before consolidating.`));
      if (!result.duplicates.length) groups.append(node("p", "No groups with identical nonempty direct membership found."));
      list.append(groups);
      const leftovers = card("Leftover entities not made by Future Homes Tech");
      leftovers.append(node("p", "Home Assistant still lists these, but no integration provides them. Review each one, then delete it in Home Assistant under Settings → Devices & services → Entities. This page never deletes them.", "maint-note"));
      for (const item of result.leftovers || []) {
        const row = node("div", undefined, "maint-report");
        row.append(node("strong", item.name), node("p", item.id, "maint-note"), node("p", `Integration: ${item.integration}${item.device_linked ? " · linked to a device" : ""}`, "maint-note"));
        leftovers.append(row);
      }
      if (!(result.leftovers || []).length) leftovers.append(node("p", "No leftover entities found."));
      list.append(leftovers);
      status.textContent = "Review complete. Nothing has changed. Refresh opens recovery history.";
    });
  }

  function renderRetired(result) {
    const section = card("Retired Future Homes Tech entities");
    section.append(node("p", "The App no longer creates these, and nothing in your configuration uses them. They are deleted from Home Assistant only after you approve. Each deletion is recorded privately first.", "maint-note"));
    const chosen = new Set(result.items.map(item => item.entity_id));
    for (const item of result.items) {
      const row = node("label", undefined, "maint-check maint-report");
      const check = node("input");
      check.type = "checkbox";
      check.checked = true;
      check.addEventListener("change", () => { if (check.checked) chosen.add(item.entity_id); else chosen.delete(item.entity_id); remove.disabled = !chosen.size; });
      const text = node("div");
      text.append(node("strong", item.name), node("p", item.entity_id, "maint-note"));
      row.append(check, text);
      section.append(row);
    }
    const auto = node("input");
    auto.type = "checkbox";
    auto.checked = Boolean(result.auto_remove);
    const autoLabel = node("label", undefined, "maint-check");
    autoLabel.append(auto, node("span", "From now on, delete retired Future Homes Tech entities automatically at start-up"));
    const remove = button(result.items.length ? `Delete ${result.items.length === 1 ? "this entity" : "selected entities"}` : "Save", () => run(async (signal, current) => {
      status.textContent = "Deleting approved entities…";
      const outcome = await api("retired", { entities: [...chosen], auto_remove: auto.checked }, signal);
      if (!current()) return;
      status.textContent = outcome.removed.length ? `Deleted ${outcome.removed.length} retired ${outcome.removed.length === 1 ? "entity" : "entities"}.` : "Saved.";
      section.replaceWith(renderRetired(outcome));
    }));
    if (!result.items.length) section.append(node("p", "Nothing is waiting for approval."));
    section.append(autoLabel, remove);
    return section;
  }

  async function loadRetired(current, signal) {
    try {
      const result = await api("retired", undefined, signal);
      if (current()) list.prepend(renderRetired(result));
    } catch (error) {
      if (current()) list.prepend(node("p", error.message || "Unable to list retired entities.", "maint-note"));
    }
  }

  function renderArchives(result) {
    list.replaceChildren();
    const info = card("Recovery history");
    info.append(node("p", "Archiving disables and hides only reviewed FHT helpers. It does not permanently delete entities or merge groups. Prior registry settings are saved privately before any change.", "maint-note"));
    list.append(info);
    for (const item of result.items) {
      const entry = card(`${date(item.created_at)} · ${item.entities.length} helpers`);
      entry.append(badge(item.status, item.status.includes("partial") || item.status === "prepared"));
      const names = node("details");
      names.append(node("summary", "Included helpers"));
      item.entities.forEach(entityId => names.append(node("p", entityId, "maint-note")));
      entry.append(names);
      if (item.status !== "restored") entry.append(button("Restore previous settings", () => confirmRestore(item)));
      list.append(entry);
    }
    status.textContent = result.items.length ? "Select a batch to recover its prior registry settings." : "No archived batches yet. Run a scan to review unused helpers.";
  }

  function modal(title) {
    closeDialog();
    dialog = node("dialog", undefined, "maint-dialog");
    const header = node("div", undefined, "maint-dialog-heading");
    header.append(node("h2", title), button("Close", closeDialog));
    const body = node("div", undefined, "maint-dialog-body");
    dialog.append(header, body);
    document.body.append(dialog);
    const created = dialog;
    created.addEventListener("close", () => { created.remove(); if (dialog === created) dialog = null; });
    dialog.showModal();
    return body;
  }

  function closeDialog() {
    if (dialog) { const old = dialog; dialog = null; old.close(); old.remove(); }
  }

  function confirmArchive() {
    if (!review || !selected.size || busy) return;
    const ids = [...selected];
    const revision = review.revision;
    const body = modal(`Archive ${ids.length} helpers?`);
    body.append(node("p", "This disables and hides the listed helpers. Recovery restores their previous settings. No devices or active group definitions are deleted."));
    ids.forEach(id => body.append(node("p", review.items.find(item => item.id === id)?.name || id)));
    const check = node("input");
    check.type = "checkbox";
    const row = node("label", undefined, "maint-check");
    row.append(check, node("span", "I reviewed external controllers and dynamically constructed references for these exact helpers."));
    const apply = button("Confirm archive", () => {
      apply.disabled = true;
      closeDialog();
      run(async (signal, current) => {
        const result = await api("archive", { entities: ids, revision, confirmed: true, external_reviewed: check.checked }, signal);
        if (!current()) return;
        selected.clear(); review = null;
        const history = await api("archives", undefined, signal);
        if (!current()) return;
        renderArchives(history);
        status.textContent = `Archived ${result.count} helpers. Recovery batch: ${result.archive_id}`;
      });
    });
    apply.disabled = true;
    check.addEventListener("change", () => { apply.disabled = !check.checked; });
    body.append(row, apply);
  }

  function confirmRestore(item) {
    const body = modal("Restore previous helper settings?");
    body.append(node("p", `Restore the prior enabled/hidden settings for these ${item.entities.length} helpers? Changed identities or integration protections will block recovery.`));
    item.entities.forEach(id => body.append(node("p", id, "maint-note")));
    body.append(button("Confirm restore", () => {
      closeDialog();
      run(async (signal, current) => {
        await api("restore", { archive_id: item.id, confirmed: true }, signal);
        const result = await api("archives", undefined, signal);
        if (current()) renderArchives(result);
      });
    }));
  }

  return {
    async show(nextView) {
      this.leave();
      view = nextView;
      toolbar.hidden = false;
      heading.textContent = titles[view] || "Safe Cleanup";
      archive.disabled = true;
      note.textContent = "Administrator-only, reversible cleanup. Active and referenced helpers are protected. Scan on demand; no automatic background cleanup.";
      list.replaceChildren();
      await load();
    },
    leave() {
      generation += 1;
      view = "";
      request?.abort();
      busy = false;
      closeDialog();
      toolbar.hidden = true;
      selected.clear();
      review = null;
    },
  };
}
