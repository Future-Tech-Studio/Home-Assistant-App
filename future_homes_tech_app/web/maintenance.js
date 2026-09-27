const titles = { "device-health": "Device Health", "action-timeline": "Action Timeline", "safe-cleanup": "Safe Cleanup" };

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
  let data;
  let review;
  let nextBefore;
  let dialog;
  let request;
  let busy = false;
  let timer;
  const selected = new Set();
  const toolbar = node("nav", undefined, "scene-toolbar-nav maint-toolbar");
  toolbar.setAttribute("aria-label", "Maintenance tools");
  const heading = node("h1", "", "scene-toolbar-heading");
  const refresh = button("Refresh", () => load());
  toolbar.append(heading, refresh);
  document.querySelector(".page-actions-primary").prepend(toolbar);
  const controls = node("div", undefined, "maint-controls");
  const search = node("input");
  search.type = "search";
  search.placeholder = "Search devices or rooms";
  search.setAttribute("aria-label", "Search maintenance records");
  const issues = node("input");
  issues.type = "checkbox";
  issues.checked = true;
  const issueLabel = node("label", undefined, "maint-check");
  issueLabel.append(issues, node("span", "Needs attention only"));
  const find = button("Search", () => view === "device-health" ? renderHealth() : load());
  const scan = button("Scan unused helpers", () => scanReview());
  const archive = button("Archive selected", () => confirmArchive());
  const status = node("p", "", "maint-status");
  status.setAttribute("role", "status");
  const note = node("p", "", "maint-note");
  const list = node("div", undefined, "maint-list");
  const more = button("Load older changes", () => load(true));
  controls.append(search, find, issueLabel, scan, archive);
  container.append(note, controls, status, list, more);
  search.addEventListener("keydown", event => { if (event.key === "Enter") find.click(); });
  search.addEventListener("input", () => { if (view === "device-health") renderHealth(); });
  issues.addEventListener("change", renderHealth);

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

  async function load(append = false) {
    await run(async (signal, current) => {
      status.textContent = "Loading…";
      const route = view === "device-health" ? "health" : view === "action-timeline" ? `timeline?search=${encodeURIComponent(search.value)}&before=${append ? nextBefore || 0 : 0}` : "archives";
      const result = await api(route, undefined, signal);
      if (!current()) return;
      data = result;
      if (view === "device-health") renderHealth();
      else if (view === "action-timeline") renderTimeline(result, append);
      else { review = null; selected.clear(); renderArchives(result); }
    });
  }

  function renderHealth() {
    if (!data || view !== "device-health") return;
    const open = new Set([...list.querySelectorAll("details[open]")].map(item => item.dataset.key));
    list.replaceChildren();
    const query = search.value.toLowerCase();
    const items = data.items.filter(item => (!issues.checked || item.attention) && `${item.name} ${item.area}`.toLowerCase().includes(query));
    for (const item of items) {
      const entry = card(item.name, item.id);
      entry.append(badge(item.status, item.status !== "Reporting"), node("p", item.area || "Unassigned", "maint-note"));
      for (const battery of item.batteries) entry.append(badge(`${battery.percent}% · ${battery.type}`, battery.percent < 20));
      for (const update of item.updates) {
        const description = update.possibly_stalled ? "May be stalled — no state update for 15+ minutes" : update.in_progress ? `Installing${update.progress !== null ? ` · ${update.progress}%` : ""}` : update.available ? "Update available" : "No update reported";
        entry.append(node("p", `${update.name}: ${update.installed} → ${update.latest}. ${description}`, "maint-note"));
      }
      const details = node("details");
      details.dataset.key = item.id;
      details.open = open.has(item.id);
      details.append(node("summary", `${item.entities.length} entity reports`));
      for (const entity of item.entities) {
        const row = node("div", undefined, "maint-report");
        row.append(node("strong", entity.name), badge(entity.restored ? "Not provided" : entity.state, entity.restored || entity.state === "unavailable"));
        row.append(node("p", `Last state report: ${date(entity.last_report)}`, "maint-note"));
        if (entity.offline_since) row.append(node("p", `Unavailable since: ${date(entity.offline_since)}`, "maint-note"));
        if (entity.last_recovered) row.append(node("p", `Last observed recovery: ${date(entity.last_recovered)}`, "maint-note"));
        details.append(row);
      }
      if (item.availability_history?.length) {
        details.append(node("h3", "Observed availability history"));
        for (const event of item.availability_history) details.append(node("p", `${date(event.at)} · ${event.status} · ${item.entities.find(entity => entity.id === event.entity_id)?.name || event.entity_id}`, "maint-note"));
      }
      entry.append(details);
      list.append(entry);
    }
    status.textContent = `${items.length} devices shown. ${data.stale ? "Cached data may be stale; connectivity is not confirmed." : "Shared live inventory."}`;
    if (!items.length) list.append(node("p", "No matching device reports."));
    more.hidden = true;
  }

  function renderTimeline(result, append) {
    if (!append) list.replaceChildren();
    for (const item of result.items) {
      const entry = card(item.name);
      entry.append(node("p", `${date(item.at)} · ${item.area || "Unassigned"}`, "maint-note"));
      entry.append(node("p", `${item.before} → ${item.after}${item.brightness !== null ? ` · ${Math.round(item.brightness / 255 * 100)}%` : ""}`));
      entry.append(node("strong", item.source), node("p", item.evidence, "maint-note"));
      if (item.source_entity) entry.append(button("View trace summaries", () => showTraces(item.source_entity)));
      list.append(entry);
    }
    status.textContent = result.items.length || append ? `Observing since ${date(result.observed_since)}. ${result.retention}` : "No matching changes captured yet. Use a device normally, then refresh.";
    nextBefore = result.next_before;
    more.hidden = nextBefore === null;
  }

  async function showTraces(entityId) {
    await run(async (signal, current) => {
      const result = await api(`traces?entity_id=${encodeURIComponent(entityId)}`, undefined, signal);
      if (!current()) return;
      const body = modal("Home Assistant trace summaries");
      body.append(node("p", "Read-only summaries. Raw variables and service payloads are withheld.", "maint-note"));
      for (const item of result.items) body.append(node("p", `${date(item.timestamp?.start || item.timestamp)} · ${item.state} · ${item.result}`));
      if (!result.items.length) body.append(node("p", "No stored traces are available for this automation."));
      status.textContent = "";
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
      status.textContent = "Review complete. Nothing has changed. Refresh opens recovery history.";
    });
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
    more.hidden = true;
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
      const ticket = generation;
      view = nextView;
      toolbar.hidden = false;
      heading.textContent = titles[view];
      search.hidden = find.hidden = view === "safe-cleanup";
      issueLabel.hidden = view !== "device-health";
      scan.hidden = archive.hidden = view !== "safe-cleanup";
      archive.disabled = true;
      search.value = "";
      note.textContent = view === "device-health" ? "Last state report is not a network heartbeat. Sleeping devices are not assumed offline. Availability history starts when this app starts and resets on restart. Firmware warnings never force an update or reset a device." : view === "action-timeline" ? "Read-only observed changes. Automation attribution requires matching Home Assistant context; unavailable evidence is never guessed." : "Administrator-only, reversible cleanup. Active and referenced helpers are protected. Scan on demand; no automatic background cleanup.";
      list.replaceChildren();
      more.hidden = true;
      await load();
      if (ticket === generation && view === "device-health") timer = setInterval(() => { if (!document.hidden && !busy && !dialog) load(); }, 30000);
    },
    leave() {
      generation += 1;
      view = "";
      request?.abort();
      busy = false;
      clearInterval(timer);
      closeDialog();
      toolbar.hidden = true;
      selected.clear();
      review = null;
      data = null;
    },
  };
}
