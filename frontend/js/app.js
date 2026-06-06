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

  // Render event datetimes in the event's own timezone (falls back to the
  // viewer's local zone for legacy events without one).
  function fmtDate(iso, tz) {
    if (!iso) return "Date TBD";
    const opts = { weekday: "short", month: "short", day: "numeric",
      year: "numeric", hour: "numeric", minute: "2-digit" };
    if (tz) { opts.timeZone = tz; opts.timeZoneName = "short"; }
    return new Date(iso).toLocaleString(undefined, opts);
  }
  function fmtDateShort(iso, tz) {
    if (!iso) return "Date TBD";
    const opts = { month: "short", day: "numeric", year: "numeric" };
    if (tz) opts.timeZone = tz;
    return new Date(iso).toLocaleDateString(undefined, opts);
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
  // AI availability — fetched once; generate buttons only show when configured.
  let aiStatus = { llm: false, image: false };
  async function loadAiStatus() {
    try { aiStatus = await api("/ai/status"); } catch { aiStatus = { llm: false, image: false }; }
  }

  function enterApp() {
    $("#auth-screen").classList.add("hidden");
    $("#app-screen").classList.remove("hidden");
    $("#who-name").textContent = me.name || me.email;
    $("#who-avatar").textContent = (me.name || me.email).charAt(0).toUpperCase();
    loadAiStatus();
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
        <h3>${esc(e.title)}${e.is_owner ? "" : ` <span class="shared-badge">Shared</span>`}</h3>
        <div class="meta">📅 ${esc(fmtDateShort(e.event_date, e.timezone))}${e.location ? " · 📍 " + esc(e.location) : ""}</div>
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
      host_display_name: me.name || "", theme: "violet", image_fit: "contain", allow_plus_ones: true,
      wall_enabled: false, guestlist_public: false };
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
          <textarea id="f-desc" placeholder="Tell your guests what to expect…">${esc(data.description)}</textarea>
          ${aiStatus.llm ? `<button type="button" class="btn btn-line btn-sm" id="gen-desc" style="margin-top:6px">✨ Generate with AI</button>` : ""}</div>
        <div class="field"><label>Theme</label><div class="theme-pick" id="theme-pick">${swatches}</div></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-fit" style="width:auto" ${data.image_fit === "contain" ? "checked" : ""}>
          Show the full image (don't crop it)</label>
          <p class="g-sub" style="margin-top:4px">Off = fill the banner (cropped). On = show the whole image.</p></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-plus" style="width:auto" ${data.allow_plus_ones ? "checked" : ""}>
          Allow guests to bring +1s</label></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-wall" style="width:auto" ${data.wall_enabled ? "checked" : ""}>
          Enable the guest wall (public well-wishes)</label></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-guestlist" style="width:auto" ${data.guestlist_public ? "checked" : ""}>
          Show a public "who's coming" list</label></div>
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

    const genDesc = $("#gen-desc");
    if (genDesc) genDesc.addEventListener("click", async () => {
      const title = $("#f-title").value.trim();
      if (!title) { toast("Add an event title first", true); return; }
      genDesc.disabled = true; genDesc.innerHTML = '<span class="spinner"></span> Generating…';
      try {
        const res = await api("/ai/text", { method: "POST", body: {
          kind: "description", title, event_date: $("#f-date").value || null,
          location: $("#f-loc").value.trim(), host_display_name: $("#f-host").value.trim(), theme,
        }});
        $("#f-desc").value = res.text;
      } catch (err) { toast(err.message, true); }
      finally { genDesc.disabled = false; genDesc.innerHTML = "✨ Generate with AI"; }
    });

    $("#ev-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const dateVal = $("#f-date").value;
      const endVal = $("#f-end").value;
      const body = {
        title: $("#f-title").value.trim(),
        host_display_name: $("#f-host").value.trim(),
        event_date: dateVal ? new Date(dateVal).toISOString() : null,
        event_end: endVal ? new Date(endVal).toISOString() : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        location: $("#f-loc").value.trim(),
        description: $("#f-desc").value,
        theme,
        image_fit: $("#f-fit").checked ? "contain" : "cover",
        allow_plus_ones: $("#f-plus").checked,
        wall_enabled: $("#f-wall").checked,
        guestlist_public: $("#f-guestlist").checked,
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
    const rsvpRows = rsvps.length ? rsvps.map((r) => rsvpRowHTML(r, e.questions)).join("") :
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
            <span>📅 ${esc(fmtDate(e.event_date, e.timezone))}</span>
            ${e.location ? `<span>📍 ${esc(e.location)}</span>` : ""}
            ${e.host_display_name ? `<span>👤 ${esc(e.host_display_name)}</span>` : ""}
          </div>
          ${e.description ? `<p style="color:var(--muted);white-space:pre-wrap">${esc(e.description)}</p>` : ""}
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="btn btn-ghost btn-sm" id="edit-btn">✎ Edit</button>
            <a class="btn btn-line btn-sm" href="/e/${esc(e.public_token)}" target="_blank">👁 Preview invite</a>
            <button class="btn btn-line btn-sm" id="broadcast-btn">✉️ Message guests</button>
            ${aiStatus.image ? `<button class="btn btn-line btn-sm" id="gen-img-btn">✨ Generate image</button>` : ""}
            ${e.is_owner ? `<button class="btn btn-danger btn-sm" id="del-btn">🗑 Delete</button>` : ""}
          </div>
          ${e.is_owner ? "" : `<p class="g-sub" style="margin-top:8px">🔗 Shared with you as a co-host.</p>`}
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
          <div class="panel">
            <h4>Guest wall (${e.wall_posts.length})</h4>
            ${e.wall_enabled ? "" : `<p class="g-sub" style="margin-bottom:8px">The guest wall is off — enable it in Edit.</p>`}
            ${wallModerationHTML(e.wall_posts)}
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
          <div class="panel">
            <h4>RSVP questions (${e.questions.length})</h4>
            ${questionsListHTML(e.questions)}
            <button class="btn btn-line btn-sm" id="edit-questions-btn" style="margin-top:10px">✎ Edit questions</button>
          </div>
          <div class="panel">
            <h4>Co-hosts (${e.cohosts.length})</h4>
            ${cohostsHTML(e)}
            ${e.is_owner ? `<div class="share-box" style="margin-top:10px">
              <input id="cohost-email" type="email" placeholder="their@email.com">
              <button class="btn btn-primary btn-sm" id="add-cohost-btn">Add</button>
            </div>
            <p class="g-sub" style="margin-top:6px">They need an invitio account. Co-hosts can manage everything except deleting the event.</p>` : ""}
          </div>
        </div>
      </div>`;

    // wire up
    $("#edit-btn").onclick = () => openEventModal(e);
    const delBtn = $("#del-btn"); if (delBtn) delBtn.onclick = () => confirmDelete(e);
    $("#img-btn").onclick = () => triggerUpload(e.id);
    $("#add-invites-btn").onclick = () => addInvites(e.id);
    $("#broadcast-btn").onclick = () => openBroadcastModal(e);
    $("#edit-questions-btn").onclick = () => openQuestionsModal(e);
    const genImg = $("#gen-img-btn");
    if (genImg) genImg.onclick = () => generateImage(e.id, genImg);
    const addCohost = $("#add-cohost-btn");
    if (addCohost) addCohost.onclick = () => addCohostHandler(e.id);
    document.querySelectorAll("[data-del-post]").forEach((b) =>
      b.addEventListener("click", () => deleteWallPost(e.id, b.dataset.delPost)));
    document.querySelectorAll("[data-del-cohost]").forEach((b) =>
      b.addEventListener("click", () => removeCohost(e.id, b.dataset.delCohost)));
    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy)));
  }

  function wallModerationHTML(posts) {
    if (!posts || !posts.length) return `<p class="g-sub" style="padding:8px 0">No posts yet.</p>`;
    return posts.map((p) => `<div class="guest-row">
      <div><div class="g-name">${esc(p.guest_name)}</div>
        <div class="g-sub" style="white-space:pre-wrap">${esc(p.message)}</div></div>
      <button class="btn btn-line btn-sm" data-del-post="${p.id}">Delete</button>
    </div>`).join("");
  }

  function cohostsHTML(e) {
    if (!e.cohosts.length) return `<p class="g-sub" style="padding:8px 0">No co-hosts yet.</p>`;
    return e.cohosts.map((c) => `<div class="guest-row">
      <div><div class="g-name">${esc(c.name || c.email)}</div><div class="g-sub">${esc(c.email)}</div></div>
      ${e.is_owner ? `<button class="btn btn-line btn-sm" data-del-cohost="${c.user_id}">Remove</button>` : ""}
    </div>`).join("");
  }

  async function deleteWallPost(eventId, postId) {
    try { await api(`/events/${eventId}/wall/${postId}`, { method: "DELETE" }); toast("Post removed"); openEvent(eventId); }
    catch (err) { toast(err.message, true); }
  }

  async function addCohostHandler(eventId) {
    const email = $("#cohost-email").value.trim();
    if (!email) { toast("Enter their email", true); return; }
    const btn = $("#add-cohost-btn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try { await api(`/events/${eventId}/cohosts`, { method: "POST", body: { email } }); toast("Co-host added"); openEvent(eventId); }
    catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Add"; }
  }

  async function removeCohost(eventId, userId) {
    try { await api(`/events/${eventId}/cohosts/${userId}`, { method: "DELETE" }); toast("Co-host removed"); openEvent(eventId); }
    catch (err) { toast(err.message, true); }
  }

  async function generateImage(eventId, btn) {
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating…';
    toast("Generating image — this can take a moment…");
    try {
      await api(`/events/${eventId}/ai/image`, { method: "POST", body: { prompt: "" } });
      toast("Image generated"); openEvent(eventId);
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.innerHTML = "✨ Generate image"; }
  }

  function questionsListHTML(questions) {
    if (!questions || !questions.length)
      return `<p class="g-sub" style="padding:8px 0">No custom questions yet.</p>`;
    const kind = { text: "Text", choice: "Single choice", multi: "Multi-select" };
    return questions.map((q) => `<div class="guest-row">
      <div>
        <div class="g-name">${esc(q.prompt)}${q.required ? ' <span style="color:#e11d48">*</span>' : ""}</div>
        <div class="g-sub">${kind[q.qtype] || q.qtype}${q.options && q.options.length ? " · " + esc(q.options.join(", ")) : ""}</div>
      </div>
    </div>`).join("");
  }

  function answersHTML(answers, questions) {
    if (!answers || !answers.length || !questions || !questions.length) return "";
    const prompts = {};
    questions.forEach((q) => { prompts[q.id] = q.prompt; });
    return answers.map((a) => {
      const v = Array.isArray(a.value) ? a.value.join(", ") : a.value;
      if (!v) return "";
      return `<div class="g-sub" style="margin-top:2px">↳ ${esc(prompts[a.question_id] || "Question")}: <b>${esc(v)}</b></div>`;
    }).filter(Boolean).join("");
  }

  function rsvpRowHTML(r, questions) {
    const pill = `<span class="pill ${r.status}">${r.status === "yes" ? "Going" : r.status === "no" ? "Can't go" : "Maybe"}</span>`;
    const extra = r.status === "yes" && r.party_size > 1 ? ` · party of ${r.party_size}` : "";
    return `<div class="guest-row">
      <div>
        <div class="g-name">${esc(r.guest_name)} ${pill}</div>
        <div class="g-sub">${esc(r.guest_email || "no email")}${extra}${r.message ? ` · "${esc(r.message)}"` : ""}</div>
        ${answersHTML(r.answers, questions)}
      </div>
    </div>`;
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
    catch { toast("Copy failed — select manually", true); }
  }

  // ── custom questions editor ──
  function openQuestionsModal(e) {
    const typeSel = (sel) => `<select class="q-type">
      <option value="text"${sel === "text" ? " selected" : ""}>Text</option>
      <option value="choice"${sel === "choice" ? " selected" : ""}>Single choice</option>
      <option value="multi"${sel === "multi" ? " selected" : ""}>Multi-select</option></select>`;
    const rowHTML = (q = { prompt: "", qtype: "text", options: [], required: false, id: null }) => `
      <div class="q-row" data-id="${q.id ?? ""}" style="border:1px solid var(--border,#e6e6ef);border-radius:10px;padding:12px;margin-bottom:10px">
        <div class="field" style="margin-bottom:8px"><input class="q-prompt" placeholder="Question (e.g. Chicken or fish?)" value="${esc(q.prompt)}"></div>
        <div class="row" style="align-items:center;margin-bottom:8px">
          <div class="field" style="margin-bottom:0">${typeSel(q.qtype)}</div>
          <label style="display:flex;gap:6px;align-items:center;cursor:pointer;font-size:14px"><input type="checkbox" class="q-req" style="width:auto"${q.required ? " checked" : ""}> Required</label>
        </div>
        <div class="field q-opts-wrap" style="margin-bottom:8px;display:${q.qtype === "text" ? "none" : "block"}">
          <input class="q-options" placeholder="Options, comma-separated" value="${esc((q.options || []).join(", "))}"></div>
        <button type="button" class="btn btn-line btn-sm q-remove">Remove</button>
      </div>`;
    mountModal(`
      <h3>RSVP questions</h3>
      <p class="g-sub" style="margin-bottom:14px">Guests answer these when they RSVP. They appear top to bottom.</p>
      <div id="q-rows">${(e.questions || []).map(rowHTML).join("")}</div>
      <button type="button" class="btn btn-line btn-sm" id="q-add">+ Add question</button>
      <div class="modal-foot">
        <button class="btn btn-line" data-close>Cancel</button>
        <button class="btn btn-primary" id="q-save">Save questions</button>
      </div>`);
    const wireRow = (row) => {
      row.querySelector(".q-type").addEventListener("change", (ev) => {
        row.querySelector(".q-opts-wrap").style.display = ev.target.value === "text" ? "none" : "block";
      });
      row.querySelector(".q-remove").addEventListener("click", () => row.remove());
    };
    $("#q-rows").querySelectorAll(".q-row").forEach(wireRow);
    $("#q-add").addEventListener("click", () => {
      const tmp = document.createElement("div"); tmp.innerHTML = rowHTML();
      const row = tmp.firstElementChild; $("#q-rows").appendChild(row); wireRow(row);
    });
    $("#q-save").addEventListener("click", async () => {
      const questions = [...$("#q-rows").querySelectorAll(".q-row")].map((row) => {
        const qtype = row.querySelector(".q-type").value;
        const id = row.dataset.id ? parseInt(row.dataset.id, 10) : null;
        return {
          id, qtype,
          prompt: row.querySelector(".q-prompt").value.trim(),
          required: row.querySelector(".q-req").checked,
          options: qtype === "text" ? []
            : row.querySelector(".q-options").value.split(",").map((s) => s.trim()).filter(Boolean),
        };
      }).filter((q) => q.prompt);
      const btn = $("#q-save"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
      try {
        await api(`/events/${e.id}/questions`, { method: "PUT", body: { questions } });
        closeModal(); toast("Questions saved"); openEvent(e.id);
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Save questions"; }
    });
  }

  // ── broadcast (message all guests) ──
  function openBroadcastModal(e) {
    mountModal(`
      <h3>Message guests</h3>
      <p class="g-sub" style="margin-bottom:14px">Send an update or cancellation by email.</p>
      <div class="field"><label>Send to</label>
        <select id="bc-aud">
          <option value="all">Everyone with an email</option>
          <option value="yes">Guests who said yes</option>
          <option value="maybe">Guests who said maybe</option>
          <option value="no">Guests who said no</option>
          <option value="pending">Haven't responded yet</option>
        </select></div>
      <div class="field"><label>Subject</label><input id="bc-subj" placeholder="An update about the event"></div>
      <div class="field"><label>Message</label><textarea id="bc-msg" placeholder="Write your message…" style="min-height:120px"></textarea>
        ${aiStatus.llm ? `<div class="row" style="align-items:center;margin-top:6px">
          <input id="bc-intent" class="field" style="margin:0" placeholder="What's it about? (e.g. venue moved indoors)">
          <button type="button" class="btn btn-line btn-sm" id="bc-gen" style="flex:0 0 auto">✨ Draft</button></div>` : ""}</div>
      <div class="modal-foot">
        <button class="btn btn-line" data-close>Cancel</button>
        <button class="btn btn-primary" id="bc-send">Send</button>
      </div>`);
    const bcGen = $("#bc-gen");
    if (bcGen) bcGen.addEventListener("click", async () => {
      bcGen.disabled = true; bcGen.innerHTML = '<span class="spinner"></span>';
      try {
        const res = await api("/ai/text", { method: "POST", body: {
          kind: "broadcast", title: e.title, audience: $("#bc-aud").value,
          location: e.location, host_display_name: e.host_display_name,
          instructions: $("#bc-intent").value.trim(),
        }});
        $("#bc-msg").value = res.text;
      } catch (err) { toast(err.message, true); }
      finally { bcGen.disabled = false; bcGen.innerHTML = "✨ Draft"; }
    });
    $("#bc-send").addEventListener("click", async () => {
      const subject = $("#bc-subj").value.trim();
      const message = $("#bc-msg").value.trim();
      if (!subject || !message) { toast("Add a subject and a message", true); return; }
      const btn = $("#bc-send"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
      try {
        const res = await api(`/events/${e.id}/broadcast`, {
          method: "POST", body: { subject, message, audience: $("#bc-aud").value },
        });
        closeModal();
        if (!res.email_enabled) toast(`Email isn't configured — ${res.recipients} guest(s) would have been messaged`, true);
        else if (!res.recipients) toast("No guests match that audience");
        else toast(`Sent to ${res.sent} of ${res.recipients} guest(s)`);
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Send"; }
    });
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
