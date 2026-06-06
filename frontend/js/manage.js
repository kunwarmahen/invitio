/* invitio no-account manage page — administers one event via its manage_token
   (read from /m/<token>). Mirrors the host detail view but token-authenticated. */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

  // Template catalog is shared across pages (see js/themes.js).
  const THEMES = window.INVITIO_THEMES;
  const THEME_HEX = window.INVITIO_THEME_HEX;
  const THEME_MOTIF = window.INVITIO_THEME_MOTIF;
  const themeSwatch = (t, selected) =>
    `<div class="sw ${selected ? "sel" : ""}" data-t="${t}" title="${esc((window.INVITIO_THEME_LABEL || {})[t] || t)}" style="background:${THEME_HEX[t]}">${THEME_MOTIF[t] === "✦" ? "" : THEME_MOTIF[t]}</div>`;

  const token = location.pathname.split("/").filter(Boolean)[1] || "";
  const justCreated = new URLSearchParams(location.search).has("created");

  let toastTimer;
  function toast(msg, err = false) {
    const el = $("#toast"); el.textContent = msg; el.classList.toggle("err", err); el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
    catch { toast("Copy failed — select manually", true); }
  }

  function fmtDate(iso, tz) {
    if (!iso) return "Date TBD";
    const opts = { weekday: "short", month: "short", day: "numeric",
      year: "numeric", hour: "numeric", minute: "2-digit" };
    if (tz) { opts.timeZone = tz; opts.timeZoneName = "short"; }
    return new Date(iso).toLocaleString(undefined, opts);
  }
  function toLocalInput(iso) {
    if (!iso) return "";
    const d = new Date(iso); const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function shareUrl(t) { return `${location.origin}/e/${t}`; }
  function manageUrl() { return `${location.origin}/m/${token}`; }
  const mapsLink = (loc) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc)}`;

  // ── share buttons (WhatsApp / SMS / email / native share) ──────────────────
  const NATIVE_SHARE = typeof navigator !== "undefined" && !!navigator.share;
  function shareActionsHTML(url, title) {
    const text = `You're invited to ${title}! RSVP here: ${url}`;
    const t = encodeURIComponent(text);
    const subj = encodeURIComponent(`You're invited: ${title}`);
    return `<div class="share-actions">
      <a class="btn btn-line btn-sm" href="https://wa.me/?text=${t}" target="_blank" rel="noopener">💬 WhatsApp</a>
      <a class="btn btn-line btn-sm" href="sms:?&body=${t}">📱 SMS</a>
      <a class="btn btn-line btn-sm" href="mailto:?subject=${subj}&body=${t}">✉️ Email</a>
      ${NATIVE_SHARE ? `<button class="btn btn-line btn-sm" data-share-native data-url="${esc(url)}" data-title="${esc(title)}">📤 Share…</button>` : ""}
    </div>`;
  }
  function nativeShare(url, title) {
    navigator.share({ title, text: `You're invited to ${title}!`, url }).catch(() => {});
  }

  // ── api ──
  async function api(path, { method = "GET", body, form } = {}) {
    const headers = {}; let payload;
    if (form) payload = form;
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    const res = await fetch(`/api/public/manage/${token}${path}`, { method, headers, body: payload });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
  }

  // AI availability — generate buttons only show when configured. Status lives at
  // /api/ai/status (outside the manage prefix), so fetch it directly.
  let aiStatus = { llm: false, image: false };
  async function loadAiStatus() {
    try { aiStatus = await (await fetch("/api/ai/status")).json(); }
    catch { aiStatus = { llm: false, image: false }; }
  }

  async function load() {
    try {
      const [event, summary] = await Promise.all([api(""), api("/summary"), loadAiStatus()]);
      document.title = `Manage · ${event.title}`;
      render(event, summary);
    } catch (err) {
      $("#manage-content").innerHTML = `<div class="empty"><div class="big">🔗</div>
        <h3>Can't open this event</h3><p>${esc(err.message)}</p></div>`;
    }
  }

  function banner(event) {
    if (!justCreated) {
      $("#manage-banner").innerHTML = `<div class="panel" style="background:var(--accent-soft);border:none">
        <b>🔑 This is your private manage link.</b> Bookmark it — it's the only way back in without an account.
        <div class="share-box" style="margin-top:10px">
          <input readonly value="${esc(manageUrl())}"><button class="btn btn-primary btn-sm" data-copy="${esc(manageUrl())}">Copy</button>
        </div></div>`;
    } else {
      $("#manage-banner").innerHTML = `<div class="panel" style="background:var(--accent-soft);border:none">
        <div class="big" style="font-size:32px">🎉</div>
        <b>Your event is live!</b> Save this private manage link — it's the only way back in:
        <div class="share-box" style="margin-top:10px">
          <input readonly value="${esc(manageUrl())}"><button class="btn btn-primary btn-sm" data-copy="${esc(manageUrl())}">Copy</button>
        </div>
        <p style="color:var(--muted);font-size:13px;margin-top:8px">Next: upload an image and invite your guests below.</p>
      </div>`;
    }
    $("#manage-banner").querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy)));
  }

  function render(e, s) {
    banner(e);
    const focalPos = `${e.image_focal_x ?? 50}% ${e.image_focal_y ?? 50}%`;
    const img = e.image_path
      ? `<div class="img" style="background-image:url('${esc(e.image_path)}');background-position:${focalPos}"><div class="upload-btn" id="img-btn">＋ Add photos</div></div>`
      : `<div class="img"><div class="ph">🖼️</div><div class="upload-btn" id="img-btn">＋ Add photos</div></div>`;

    const rsvps = [...e.rsvps].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
    const rsvpRows = rsvps.length ? rsvps.map((r) => rsvpRowHTML(r, e.questions)).join("")
      : `<p class="g-sub" style="padding:8px 0">No responses yet.</p>`;
    const inviteRows = e.invites.length ? e.invites.map((i) => `
      <div class="guest-row">
        <div><div class="g-name">${esc(i.guest_name || i.guest_email)}</div>
          <div class="g-sub">${esc(i.guest_email)}${i.sent_at ? " · ✉️ invited" : " · not emailed"}${i.viewed_at ? " · 👁 opened" : ""}</div></div>
        <button class="btn btn-line btn-sm" data-copy="${esc(location.origin)}/i/${esc(i.token)}">Copy link</button>
      </div>`).join("") : `<p class="g-sub" style="padding:8px 0">No guests added yet.</p>`;

    $("#manage-content").innerHTML = `
      <div class="detail-hero">
        ${img}
        <div class="info">
          <h2>${esc(e.title)}</h2>
          <div class="detail-meta">
            <span>📅 ${esc(fmtDate(e.event_date, e.timezone))}</span>
            ${e.location ? `<span>📍 ${esc(e.location)} · <a href="${esc(mapsLink(e.location))}" target="_blank" rel="noopener">Open in Maps ↗</a></span>` : ""}
            ${e.host_display_name ? `<span>👤 ${esc(e.host_display_name)}</span>` : ""}
          </div>
          ${e.description ? `<p style="color:var(--muted);white-space:pre-wrap">${esc(e.description)}</p>` : ""}
          <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="btn btn-ghost btn-sm" id="edit-btn">✎ Edit details</button>
            <a class="btn btn-line btn-sm" href="/e/${esc(e.public_token)}" target="_blank">👁 Preview invite</a>
            <button class="btn btn-line btn-sm" id="broadcast-btn">✉️ Message guests</button>
            ${aiStatus.image ? `<button class="btn btn-line btn-sm" id="gen-img-btn">✨ Generate image</button>` : ""}
            <button class="btn btn-danger btn-sm" id="del-btn">🗑 Delete</button>
          </div>
        </div>
      </div>

      <div class="two-col">
        <div>
          <div class="panel"><h4>Responses</h4>
            <div class="stats">
              <div class="stat yes"><div class="n">${s.yes}</div><div class="l">Yes</div></div>
              <div class="stat maybe"><div class="n">${s.maybe}</div><div class="l">Maybe</div></div>
              <div class="stat no"><div class="n">${s.no}</div><div class="l">No</div></div>
              <div class="stat"><div class="n">${s.head_count}</div><div class="l">Coming</div></div>
            </div>
            <p class="g-sub" style="text-align:center;margin-top:8px">${s.responded} of ${s.invited} invited have responded</p>
          </div>
          <div class="panel"><h4>Who's responded</h4>${rsvpRows}</div>
        </div>
        <div>
          <div class="panel"><h4>Photos (${e.images.length})</h4>
            ${galleryGridHTML(e)}
            <p class="g-sub" style="margin-top:10px">The cover photo is the invite banner${e.image_fit === "cover" ? " — use “Adjust crop” to choose what stays visible" : ""}. Drag to reorder.</p>
          </div>
          <div class="panel"><h4>Share link</h4>
            <p class="g-sub" style="margin-bottom:10px">Anyone with this link can RSVP.</p>
            <div class="share-box">
              <input readonly value="${esc(shareUrl(e.public_token))}">
              <button class="btn btn-primary btn-sm" data-copy="${esc(shareUrl(e.public_token))}">Copy</button>
            </div>
            ${shareActionsHTML(shareUrl(e.public_token), e.title)}
          </div>
          <div class="panel"><h4>Invite by email</h4>
            <div class="field" style="margin-bottom:10px">
              <textarea id="emails-input" placeholder="Guest emails, separated by commas or new lines"></textarea></div>
            <label style="display:flex;gap:8px;align-items:center;cursor:pointer;margin-bottom:12px">
              <input type="checkbox" id="send-email-chk" checked style="width:auto"> Email an RSVP link to each guest</label>
            <button class="btn btn-primary" id="add-invites-btn" style="width:100%">Send invitations</button>
            <div class="panel" style="box-shadow:none;border:none;padding:14px 0 0;margin:6px 0 0">
              <h4>Guest list (${e.invites.length})</h4>${inviteRows}</div>
          </div>
          <div class="panel"><h4>RSVP questions (${e.questions.length})</h4>
            ${questionsListHTML(e.questions)}
            <button class="btn btn-line btn-sm" id="edit-questions-btn" style="margin-top:10px">✎ Edit questions</button>
          </div>
          <div class="panel"><h4>Guest wall (${e.wall_posts.length})</h4>
            ${e.wall_enabled ? "" : `<p class="g-sub" style="margin-bottom:8px">The guest wall is off — enable it in Edit.</p>`}
            ${wallModerationHTML(e.wall_posts)}
          </div>
        </div>
      </div>`;

    $("#edit-btn").onclick = () => openEditModal(e);
    $("#del-btn").onclick = () => confirmDelete(e);
    $("#img-btn").onclick = () => $("#hidden-file").click();
    wireGallery(e);
    $("#add-invites-btn").onclick = () => addInvites();
    $("#broadcast-btn").onclick = () => openBroadcastModal(e);
    $("#edit-questions-btn").onclick = () => openQuestionsModal(e);
    const genImg = $("#gen-img-btn");
    if (genImg) genImg.onclick = async () => {
      genImg.disabled = true; genImg.innerHTML = '<span class="spinner"></span> Generating…';
      toast("Generating image — this can take a moment…");
      try { await api("/ai/image", { method: "POST", body: { prompt: "" } }); toast("Image generated"); load(); }
      catch (err) { toast(err.message, true); genImg.disabled = false; genImg.innerHTML = "✨ Generate image"; }
    };
    document.querySelectorAll("[data-del-post]").forEach((b) =>
      b.addEventListener("click", async () => {
        try { await api(`/wall/${b.dataset.delPost}`, { method: "DELETE" }); toast("Post removed"); load(); }
        catch (err) { toast(err.message, true); }
      }));
    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy)));
    document.querySelectorAll("[data-share-native]").forEach((b) =>
      b.addEventListener("click", () => nativeShare(b.dataset.url, b.dataset.title)));
  }

  function wallModerationHTML(posts) {
    if (!posts || !posts.length) return `<p class="g-sub" style="padding:8px 0">No posts yet.</p>`;
    return posts.map((p) => `<div class="guest-row">
      <div><div class="g-name">${esc(p.guest_name)}</div>
        <div class="g-sub" style="white-space:pre-wrap">${esc(p.message)}</div></div>
      <button class="btn btn-line btn-sm" data-del-post="${p.id}">Delete</button>
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
    return `<div class="guest-row"><div>
      <div class="g-name">${esc(r.guest_name)} ${pill}</div>
      <div class="g-sub">${esc(r.guest_email || "no email")}${extra}${r.message ? ` · "${esc(r.message)}"` : ""}</div>
      ${answersHTML(r.answers, questions)}
    </div></div>`;
  }

  function questionsListHTML(questions) {
    if (!questions || !questions.length)
      return `<p class="g-sub" style="padding:8px 0">No custom questions yet.</p>`;
    const kind = { text: "Text", choice: "Single choice", multi: "Multi-select" };
    return questions.map((q) => `<div class="guest-row"><div>
      <div class="g-name">${esc(q.prompt)}${q.required ? ' <span style="color:#e11d48">*</span>' : ""}</div>
      <div class="g-sub">${kind[q.qtype] || q.qtype}${q.options && q.options.length ? " · " + esc(q.options.join(", ")) : ""}</div>
    </div></div>`).join("");
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
        await api("/questions", { method: "PUT", body: { questions } });
        closeModal(); toast("Questions saved"); load();
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
        const res = await api("/broadcast", { method: "POST", body: { subject, message, audience: $("#bc-aud").value } });
        closeModal();
        if (!res.email_enabled) toast(`Email isn't configured — ${res.recipients} guest(s) would have been messaged`, true);
        else if (!res.recipients) toast("No guests match that audience");
        else toast(`Sent to ${res.sent} of ${res.recipients} guest(s)`);
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Send"; }
    });
  }

  // ── edit modal ──
  function openEditModal(e) {
    const swatches = THEMES.map((t) => themeSwatch(t, t === e.theme)).join("");
    mountModal(`
      <h3>Edit event</h3>
      <form id="ev-form">
        <div class="field"><label>Event title *</label><input id="f-title" required value="${esc(e.title)}"></div>
        <div class="field"><label>Hosted by</label><input id="f-host" value="${esc(e.host_display_name)}"></div>
        <div class="row">
          <div class="field"><label>Starts</label><input id="f-date" type="datetime-local" value="${toLocalInput(e.event_date)}"></div>
          <div class="field"><label>Ends</label><input id="f-end" type="datetime-local" value="${toLocalInput(e.event_end)}"></div>
        </div>
        <div class="field"><label>Location</label><input id="f-loc" value="${esc(e.location)}"></div>
        <div class="field"><label>Description</label><textarea id="f-desc">${esc(e.description)}</textarea>
          ${aiStatus.llm ? `<button type="button" class="btn btn-line btn-sm" id="gen-desc" style="margin-top:6px">✨ Generate with AI</button>` : ""}</div>
        <div class="field"><label>Theme</label><div class="theme-pick" id="theme-pick">${swatches}</div></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-fit" style="width:auto" ${e.image_fit === "contain" ? "checked" : ""}> Show the full image (don't crop it)</label></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-plus" style="width:auto" ${e.allow_plus_ones ? "checked" : ""}> Allow +1s</label></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-wall" style="width:auto" ${e.wall_enabled ? "checked" : ""}> Enable the guest wall (public well-wishes)</label></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-guestlist" style="width:auto" ${e.guestlist_public ? "checked" : ""}> Show a public "who's coming" list</label></div>
        <div class="modal-foot">
          <button type="button" class="btn btn-line" data-close>Cancel</button>
          <button type="submit" class="btn btn-primary" id="ev-save">Save changes</button>
        </div>
      </form>`);
    let theme = e.theme;
    $("#theme-pick").querySelectorAll("[data-t]").forEach((sw) => sw.addEventListener("click", () => {
      theme = sw.dataset.t;
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
    $("#ev-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const dateVal = $("#f-date").value, endVal = $("#f-end").value;
      const btn = $("#ev-save"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
      try {
        await api("", { method: "PUT", body: {
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
        }});
        closeModal(); toast("Saved"); load();
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Save changes"; }
    });
  }

  function confirmDelete(e) {
    mountModal(`<h3>Delete "${esc(e.title)}"?</h3>
      <p style="color:var(--muted);margin-bottom:18px">This removes the event, guest list, and all RSVPs. This can't be undone.</p>
      <div class="modal-foot"><button class="btn btn-line" data-close>Cancel</button>
        <button class="btn btn-danger" id="confirm-del">Delete event</button></div>`);
    $("#confirm-del").onclick = async () => {
      try { await api("", { method: "DELETE" }); closeModal();
        $("#manage-banner").innerHTML = "";
        $("#manage-content").innerHTML = `<div class="empty"><div class="big">👋</div><h3>Event deleted</h3>
          <p><a href="/quick">Create another</a></p></div>`;
      } catch (err) { toast(err.message, true); }
    };
  }

  // ── photo gallery ──
  function galleryGridHTML(e) {
    const imgs = [...(e.images || [])].sort((a, b) => a.position - b.position);
    const tiles = imgs.map((im) => {
      const pos = im.is_cover ? `;background-position:${e.image_focal_x ?? 50}% ${e.image_focal_y ?? 50}%` : "";
      return `<div class="gphoto" draggable="true" data-img="${im.id}" style="background-image:url('${esc(im.path)}')${pos}">
        ${im.is_cover ? `<span class="cover-badge">Cover</span>` : ""}
        <div class="gphoto-actions">
          ${im.is_cover
            ? `<button data-crop="${im.id}">Adjust crop</button>`
            : `<button data-cover="${im.id}">Set cover</button>`}
          <button class="danger" data-delimg="${im.id}">Delete</button>
        </div>
      </div>`;
    }).join("");
    return `<div class="gallery-grid" id="gallery-grid">${tiles}
      <div class="gallery-add" id="add-photos"><div class="plus">＋</div>Add photos</div></div>`;
  }

  function wireGallery(e) {
    const add = $("#add-photos");
    if (add) add.onclick = () => $("#hidden-file").click();
    document.querySelectorAll("[data-cover]").forEach((b) =>
      b.addEventListener("click", () => setCover(b.dataset.cover)));
    document.querySelectorAll("[data-delimg]").forEach((b) =>
      b.addEventListener("click", () => deleteImage(b.dataset.delimg)));
    document.querySelectorAll("[data-crop]").forEach((b) =>
      b.addEventListener("click", () => openFocalPicker(e)));
    wireGalleryDrag();
  }

  function wireGalleryDrag() {
    const grid = $("#gallery-grid");
    if (!grid) return;
    let dragEl = null;
    grid.querySelectorAll(".gphoto").forEach((tile) => {
      tile.addEventListener("dragstart", () => { dragEl = tile; tile.classList.add("dragging"); });
      tile.addEventListener("dragend", () => { tile.classList.remove("dragging"); saveGalleryOrder(grid); });
      tile.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        if (!dragEl || dragEl === tile) return;
        const after = ev.clientY > tile.getBoundingClientRect().top + tile.offsetHeight / 2
          || ev.clientX > tile.getBoundingClientRect().left + tile.offsetWidth / 2;
        grid.insertBefore(dragEl, after ? tile.nextSibling : tile);
      });
    });
  }

  async function saveGalleryOrder(grid) {
    const ids = [...grid.querySelectorAll(".gphoto")].map((t) => parseInt(t.dataset.img, 10));
    try { await api("/images/order", { method: "PUT", body: { ids } }); load(); }
    catch (err) { toast(err.message, true); load(); }
  }

  async function setCover(imageId) {
    try { await api(`/images/${imageId}/cover`, { method: "POST" }); toast("Cover updated"); load(); }
    catch (err) { toast(err.message, true); }
  }

  async function deleteImage(imageId) {
    try { await api(`/images/${imageId}`, { method: "DELETE" }); toast("Photo removed"); load(); }
    catch (err) { toast(err.message, true); }
  }

  function openFocalPicker(e) {
    let fx = e.image_focal_x ?? 50, fy = e.image_focal_y ?? 50;
    mountModal(`
      <h3>Adjust crop</h3>
      <p class="g-sub" style="margin-bottom:14px">Drag the dot to choose what stays in view when the cover photo is cropped.${e.image_fit === "cover" ? "" : " (This event currently shows the full image — switch off “Show the full image” in Edit to crop.)"}</p>
      <div class="focal-stage" id="focal-stage" style="background-image:url('${esc(e.image_path)}');background-position:${fx}% ${fy}%">
        <div class="focal-dot" id="focal-dot" style="left:${fx}%;top:${fy}%"></div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-line" data-close>Cancel</button>
        <button class="btn btn-primary" id="focal-save">Save crop</button>
      </div>`);
    const stage = $("#focal-stage"), dot = $("#focal-dot");
    const place = (ev) => {
      const r = stage.getBoundingClientRect();
      const cx = (ev.touches ? ev.touches[0].clientX : ev.clientX);
      const cy = (ev.touches ? ev.touches[0].clientY : ev.clientY);
      fx = Math.max(0, Math.min(100, ((cx - r.left) / r.width) * 100));
      fy = Math.max(0, Math.min(100, ((cy - r.top) / r.height) * 100));
      dot.style.left = fx + "%"; dot.style.top = fy + "%";
      stage.style.backgroundPosition = `${fx}% ${fy}%`;
    };
    let dragging = false;
    stage.addEventListener("pointerdown", (ev) => { dragging = true; stage.setPointerCapture(ev.pointerId); place(ev); });
    stage.addEventListener("pointermove", (ev) => { if (dragging) place(ev); });
    stage.addEventListener("pointerup", () => { dragging = false; });
    $("#focal-save").addEventListener("click", async () => {
      const btn = $("#focal-save"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
      try {
        await api("", { method: "PUT", body: {
          image_focal_x: Math.round(fx * 10) / 10, image_focal_y: Math.round(fy * 10) / 10,
        }});
        closeModal(); toast("Crop saved"); load();
      } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Save crop"; }
    });
  }

  // ── image upload ──
  $("#hidden-file").addEventListener("change", async (e) => {
    const files = [...e.target.files]; if (!files.length) return;
    const fd = new FormData(); files.forEach((f) => fd.append("files", f));
    toast(files.length > 1 ? `Uploading ${files.length} photos…` : "Uploading photo…");
    try { await api("/images", { method: "POST", form: fd }); toast("Photos updated"); load(); }
    catch (err) { toast(err.message, true); }
    finally { e.target.value = ""; }
  });

  async function addInvites() {
    const raw = $("#emails-input").value;
    const emails = raw.split(/[\s,;]+/).map((s) => s.trim()).filter((s) => s.includes("@"));
    if (!emails.length) { toast("Enter at least one valid email", true); return; }
    const btn = $("#add-invites-btn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await api("/invites", { method: "POST", body: { emails, send_email: $("#send-email-chk").checked } });
      if (!res.added.length) toast("Those guests are already invited");
      else if (!res.email_enabled) toast(`${res.added.length} added — email not configured, copy links to share`);
      else toast(`${res.added.length} invited · ${res.emailed} emailed`);
      load();
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Send invitations"; }
  }

  // ── dark-mode toggle (cycles system → light → dark; persisted by scheme.js) ──
  const SCHEME_ICON = { system: "🖥️", light: "☀️", dark: "🌙" };
  function wireSchemeToggle() {
    const btn = $("#scheme-btn"); if (!btn || !window.invitioScheme) return;
    const sync = () => {
      const pref = window.invitioScheme.get();
      btn.textContent = SCHEME_ICON[pref] || "🖥️";
      btn.title = `Theme: ${pref}` + (pref === "system" ? " (follows your device)" : "");
    };
    btn.addEventListener("click", () => { window.invitioScheme.cycle(); sync(); });
    sync();
  }

  // ── modal helpers ──
  function mountModal(html) {
    $("#modal-root").innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
    const bg = $(".modal-bg");
    bg.addEventListener("click", (e) => { if (e.target === bg) closeModal(); });
    bg.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
  }
  function closeModal() { $("#modal-root").innerHTML = ""; }

  // ── PWA service worker ──
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
    let _reloadingForSW = false;
    if (navigator.serviceWorker.controller) {
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (_reloadingForSW) return; _reloadingForSW = true; window.location.reload();
      });
    }
  }

  wireSchemeToggle();
  load();
})();
