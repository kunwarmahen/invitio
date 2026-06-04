/* invitio host app — auth, event CRUD, image upload, invites, RSVP dashboard. */
(() => {
  "use strict";

  const TOKEN_KEY = "invitio_token";
  const THEMES = ["violet", "rose", "ocean", "forest", "sunset", "midnight"];
  const THEME_HEX = { violet:"#7c3aed", rose:"#e11d6b", ocean:"#0ea5e9", forest:"#10b981", sunset:"#f97316", midnight:"#4f46e5" };

  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

  let me = null;          // current user
  let currentEvent = null; // loaded EventDetail

  // ── api helper ──────────────────────────────────────────────────────────
  function token() { return localStorage.getItem(TOKEN_KEY); }
  async function api(path, { method = "GET", body, form } = {}) {
    const headers = {};
    const t = token();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    let payload;
    if (form) { payload = form; }
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    const res = await fetch(`/api${path}`, { method, headers, body: payload });
    if (res.status === 401) { logout(); throw new Error("Session expired — please sign in again."); }
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
  }

  // ── toast ───────────────────────────────────────────────────────────────
  let toastTimer;
  function toast(msg, isErr = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.toggle("err", isErr);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  function fmtDate(iso) {
    if (!iso) return "Date TBD";
    const d = new Date(iso);
    return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric",
      year: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function fmtDateShort(iso) {
    if (!iso) return "Date TBD";
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
  // datetime-local needs "YYYY-MM-DDTHH:mm" in local time
  function toLocalInput(iso) {
    if (!iso) return "";
    const d = new Date(iso); const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  // ════════════════════════════════════════════════════════════════════════
  //  AUTH
  // ════════════════════════════════════════════════════════════════════════
  let signupMode = false;
  function renderAuthMode() {
    $("#auth-title").textContent = signupMode ? "Create your account" : "Welcome back";
    $("#auth-sub").textContent = signupMode
      ? "Start sending beautiful invitations." : "Sign in to manage your invitations.";
    $("#auth-submit").textContent = signupMode ? "Create account" : "Sign in";
    $("#name-field").style.display = signupMode ? "block" : "none";
    $("#auth-password").autocomplete = signupMode ? "new-password" : "current-password";
    $("#auth-toggle").innerHTML = signupMode
      ? `Already have an account? <a id="tg">Sign in</a>`
      : `New here? <a id="tg">Create an account</a>`;
    $("#tg").onclick = () => { signupMode = !signupMode; renderAuthMode(); };
  }

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#auth-submit");
    const email = $("#auth-email").value.trim();
    const password = $("#auth-password").value;
    const name = $("#auth-name").value.trim();
    btn.disabled = true; const label = btn.textContent; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const path = signupMode ? "/auth/signup" : "/auth/login";
      const body = signupMode ? { email, password, name } : { email, password };
      const data = await api(path, { method: "POST", body });
      localStorage.setItem(TOKEN_KEY, data.token);
      me = data.user;
      enterApp();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    me = null; currentEvent = null;
    $("#app-screen").classList.add("hidden");
    $("#auth-screen").classList.remove("hidden");
  }
  $("#logout-btn").addEventListener("click", logout);

  // ════════════════════════════════════════════════════════════════════════
  //  APP SHELL
  // ════════════════════════════════════════════════════════════════════════
  function enterApp() {
    $("#auth-screen").classList.add("hidden");
    $("#app-screen").classList.remove("hidden");
    $("#who-name").textContent = me.name || me.email;
    $("#who-avatar").textContent = (me.name || me.email).charAt(0).toUpperCase();
    showList();
  }

  function showList() {
    currentEvent = null;
    $("#detail-view").classList.add("hidden");
    $("#list-view").classList.remove("hidden");
    loadEvents();
  }
  $("#back-btn").addEventListener("click", showList);

  async function loadEvents() {
    const grid = $("#events-grid");
    grid.innerHTML = '<div class="center-load"><div class="spinner"></div></div>';
    try {
      const events = await api("/events");
      if (!events.length) {
        grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
          <div class="big">🎉</div>
          <h3>No events yet</h3>
          <p>Create your first invitation to get started.</p>
        </div>`;
        return;
      }
      grid.innerHTML = events.map(eventCardHTML).join("");
      grid.querySelectorAll("[data-eid]").forEach((el) =>
        el.addEventListener("click", () => openEvent(el.dataset.eid)));
    } catch (err) { grid.innerHTML = `<p class="empty">${esc(err.message)}</p>`; }
  }

  function eventCardHTML(e) {
    const thumb = e.image_path
      ? `<div class="thumb" style="background-image:url('${esc(e.image_path)}')"></div>`
      : `<div class="thumb"><div class="ph">🎟️</div></div>`;
    return `<div class="event-card" data-eid="${e.id}">
      ${thumb}
      <div class="body">
        <h3>${esc(e.title)}</h3>
        <div class="meta">📅 ${esc(fmtDateShort(e.event_date))}${e.location ? " · 📍 " + esc(e.location) : ""}</div>
      </div>
    </div>`;
  }

  // ════════════════════════════════════════════════════════════════════════
  //  CREATE / EDIT EVENT MODAL
  // ════════════════════════════════════════════════════════════════════════
  $("#new-event-btn").addEventListener("click", () => openEventModal(null));

  function openEventModal(ev) {
    const editing = !!ev;
    const data = ev || { title: "", description: "", location: "", event_date: null, event_end: null,
      host_display_name: me.name || "", theme: "violet", allow_plus_ones: true };
    const swatches = THEMES.map((t) =>
      `<div class="sw ${t === data.theme ? "sel" : ""}" data-theme-pick="${t}" style="background:${THEME_HEX[t]}"></div>`).join("");

    mountModal(`
      <h3>${editing ? "Edit event" : "Create event"}</h3>
      <form id="ev-form">
        <div class="field"><label>Event title *</label>
          <input id="f-title" required value="${esc(data.title)}" placeholder="Summer Rooftop Party"></div>
        <div class="field"><label>Hosted by</label>
          <input id="f-host" value="${esc(data.host_display_name)}" placeholder="Your name"></div>
        <div class="row">
          <div class="field"><label>Starts</label>
            <input id="f-date" type="datetime-local" value="${toLocalInput(data.event_date)}"></div>
          <div class="field"><label>Ends (optional)</label>
            <input id="f-end" type="datetime-local" value="${toLocalInput(data.event_end)}"></div>
        </div>
        <div class="field"><label>Location</label>
          <input id="f-loc" value="${esc(data.location)}" placeholder="123 Main St"></div>
        <div class="field"><label>Description</label>
          <textarea id="f-desc" placeholder="Tell your guests what to expect…">${esc(data.description)}</textarea></div>
        <div class="field"><label>Theme</label><div class="theme-pick" id="theme-pick">${swatches}</div></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-plus" style="width:auto" ${data.allow_plus_ones ? "checked" : ""}>
          Allow guests to bring +1s</label></div>
        <div class="modal-foot">
          <button type="button" class="btn btn-line" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary" id="ev-save">${editing ? "Save changes" : "Create event"}</button>
        </div>
      </form>
    `);

    let theme = data.theme;
    $("#theme-pick").querySelectorAll("[data-theme-pick]").forEach((sw) =>
      sw.addEventListener("click", () => {
        theme = sw.dataset.themePick;
        $("#theme-pick").querySelectorAll(".sw").forEach((s) => s.classList.remove("sel"));
        sw.classList.add("sel");
      }));

    $("#ev-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const dateVal = $("#f-date").value;
      const endVal = $("#f-end").value;
      const body = {
        title: $("#f-title").value.trim(),
        host_display_name: $("#f-host").value.trim(),
        event_date: dateVal ? new Date(dateVal).toISOString() : null,
        event_end: endVal ? new Date(endVal).toISOString() : null,
        location: $("#f-loc").value.trim(),
        description: $("#f-desc").value,
        theme,
        allow_plus_ones: $("#f-plus").checked,
      };
      const btn = $("#ev-save"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
      try {
        if (editing) {
          await api(`/events/${ev.id}`, { method: "PUT", body });
          closeModal(); toast("Event updated");
          openEvent(ev.id);
        } else {
          const created = await api("/events", { method: "POST", body });
          closeModal(); toast("Event created 🎉");
          openEvent(created.id);
        }
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Save"; }
    });
  }

  // ════════════════════════════════════════════════════════════════════════
  //  EVENT DETAIL
  // ════════════════════════════════════════════════════════════════════════
  async function openEvent(id) {
    $("#list-view").classList.add("hidden");
    $("#detail-view").classList.remove("hidden");
    const c = $("#detail-content");
    c.innerHTML = '<div class="center-load"><div class="spinner"></div></div>';
    try {
      const [event, summary] = await Promise.all([
        api(`/events/${id}`), api(`/events/${id}/summary`),
      ]);
      currentEvent = event;
      renderDetail(event, summary);
    } catch (err) { c.innerHTML = `<p class="empty">${esc(err.message)}</p>`; }
  }

  function shareUrl(token) { return `${location.origin}/e/${token}`; }

  function renderDetail(e, s) {
    const img = e.image_path
      ? `<div class="img" style="background-image:url('${esc(e.image_path)}')"><div class="upload-btn" id="img-btn">📷 Change image</div></div>`
      : `<div class="img"><div class="ph">🖼️</div><div class="upload-btn" id="img-btn">📷 Upload image</div></div>`;

    const rsvps = [...e.rsvps].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
    const rsvpRows = rsvps.length ? rsvps.map(rsvpRowHTML).join("") :
      `<p class="g-sub" style="padding:8px 0">No responses yet.</p>`;

    const inviteRows = e.invites.length ? e.invites.map((i) => `
      <div class="guest-row">
        <div><div class="g-name">${esc(i.guest_name || i.guest_email)}</div>
          <div class="g-sub">${esc(i.guest_email)}${i.sent_at ? " · ✉️ invited" : " · not emailed"}</div></div>
        <button class="btn btn-line btn-sm" data-copy="${esc(location.origin)}/i/${esc(i.token)}">Copy link</button>
      </div>`).join("") : `<p class="g-sub" style="padding:8px 0">No guests added yet.</p>`;

    $("#detail-content").innerHTML = `
      <div class="detail-hero">
        ${img}
        <div class="info">
          <h2>${esc(e.title)}</h2>
          <div class="detail-meta">
            <span>📅 ${esc(fmtDate(e.event_date))}</span>
            ${e.location ? `<span>📍 ${esc(e.location)}</span>` : ""}
            ${e.host_display_name ? `<span>👤 ${esc(e.host_display_name)}</span>` : ""}
          </div>
          ${e.description ? `<p style="color:var(--muted);white-space:pre-wrap">${esc(e.description)}</p>` : ""}
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="btn btn-ghost btn-sm" id="edit-btn">✎ Edit</button>
            <a class="btn btn-line btn-sm" href="/e/${esc(e.public_token)}" target="_blank">👁 Preview invite</a>
            <button class="btn btn-danger btn-sm" id="del-btn">🗑 Delete</button>
          </div>
        </div>
      </div>

      <div class="two-col">
        <div>
          <div class="panel">
            <h4>Responses</h4>
            <div class="stats">
              <div class="stat yes"><div class="n">${s.yes}</div><div class="l">Yes</div></div>
              <div class="stat maybe"><div class="n">${s.maybe}</div><div class="l">Maybe</div></div>
              <div class="stat no"><div class="n">${s.no}</div><div class="l">No</div></div>
              <div class="stat"><div class="n">${s.head_count}</div><div class="l">Coming</div></div>
            </div>
            <p class="g-sub" style="text-align:center;margin-top:8px">${s.responded} of ${s.invited} invited have responded</p>
          </div>
          <div class="panel">
            <h4>Who's responded</h4>
            ${rsvpRows}
          </div>
        </div>

        <div>
          <div class="panel">
            <h4>Share link</h4>
            <p class="g-sub" style="margin-bottom:10px">Anyone with this link can RSVP.</p>
            <div class="share-box">
              <input id="share-input" readonly value="${esc(shareUrl(e.public_token))}">
              <button class="btn btn-primary btn-sm" data-copy="${esc(shareUrl(e.public_token))}">Copy</button>
            </div>
          </div>
          <div class="panel">
            <h4>Invite by email</h4>
            <div class="field" style="margin-bottom:10px">
              <textarea id="emails-input" placeholder="Enter guest emails, separated by commas or new lines"></textarea>
            </div>
            <label style="display:flex;gap:8px;align-items:center;cursor:pointer;margin-bottom:12px">
              <input type="checkbox" id="send-email-chk" checked style="width:auto"> Email an RSVP link to each guest</label>
            <button class="btn btn-primary" id="add-invites-btn" style="width:100%">Send invitations</button>
            <div class="panel" style="box-shadow:none;border:none;padding:14px 0 0;margin:6px 0 0">
              <h4>Guest list (${e.invites.length})</h4>
              ${inviteRows}
            </div>
          </div>
        </div>
      </div>`;

    // wire up
    $("#edit-btn").onclick = () => openEventModal(e);
    $("#del-btn").onclick = () => confirmDelete(e);
    $("#img-btn").onclick = () => triggerUpload(e.id);
    $("#add-invites-btn").onclick = () => addInvites(e.id);
    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy)));
  }

  function rsvpRowHTML(r) {
    const pill = `<span class="pill ${r.status}">${r.status === "yes" ? "Going" : r.status === "no" ? "Can't go" : "Maybe"}</span>`;
    const extra = r.status === "yes" && r.party_size > 1 ? ` · party of ${r.party_size}` : "";
    return `<div class="guest-row">
      <div>
        <div class="g-name">${esc(r.guest_name)} ${pill}</div>
        <div class="g-sub">${esc(r.guest_email || "no email")}${extra}${r.message ? ` · "${esc(r.message)}"` : ""}</div>
      </div>
    </div>`;
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
    catch { toast("Copy failed — select manually", true); }
  }

  function confirmDelete(e) {
    mountModal(`
      <h3>Delete "${esc(e.title)}"?</h3>
      <p style="color:var(--muted);margin-bottom:18px">This removes the event, its guest list, and all RSVPs. This can't be undone.</p>
      <div class="modal-foot">
        <button class="btn btn-line" data-close>Cancel</button>
        <button class="btn btn-danger" id="confirm-del">Delete event</button>
      </div>`);
    $("#confirm-del").onclick = async () => {
      try { await api(`/events/${e.id}`, { method: "DELETE" }); closeModal(); toast("Event deleted"); showList(); }
      catch (err) { toast(err.message, true); }
    };
  }

  // ── image upload ──
  let uploadTargetId = null;
  function triggerUpload(eventId) { uploadTargetId = eventId; $("#hidden-file").click(); }
  $("#hidden-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file || !uploadTargetId) return;
    const fd = new FormData(); fd.append("file", file);
    toast("Uploading image…");
    try {
      await api(`/events/${uploadTargetId}/image`, { method: "POST", form: fd });
      toast("Image updated");
      openEvent(uploadTargetId);
    } catch (err) { toast(err.message, true); }
    finally { e.target.value = ""; uploadTargetId = null; }
  });

  // ── add invites ──
  async function addInvites(eventId) {
    const raw = $("#emails-input").value;
    const emails = raw.split(/[\s,;]+/).map((s) => s.trim()).filter((s) => s.includes("@"));
    if (!emails.length) { toast("Enter at least one valid email", true); return; }
    const btn = $("#add-invites-btn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await api(`/events/${eventId}/invites`, {
        method: "POST", body: { emails, send_email: $("#send-email-chk").checked },
      });
      if (!res.added.length) toast("Those guests are already invited");
      else if (!res.email_enabled) toast(`${res.added.length} added — email not configured, copy links to share`);
      else toast(`${res.added.length} invited · ${res.emailed} emailed`);
      openEvent(eventId);
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Send invitations"; }
  }

  // ── modal helpers ──
  function mountModal(html) {
    $("#modal-root").innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
    const bg = $(".modal-bg");
    bg.addEventListener("click", (e) => { if (e.target === bg) closeModal(); });
    bg.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
  }
  function closeModal() { $("#modal-root").innerHTML = ""; }

  // ════════════════════════════════════════════════════════════════════════
  //  BOOT
  // ════════════════════════════════════════════════════════════════════════
  async function boot() {
    renderAuthMode();
    if (token()) {
      try { me = await api("/auth/me"); enterApp(); return; }
      catch { /* token invalid → fall through to auth */ }
    }
    $("#auth-screen").classList.remove("hidden");
  }
  boot();
})();
