/* invitio no-account manage page — administers one event via its manage_token
   (read from /m/<token>). Mirrors the host detail view but token-authenticated. */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

  const THEMES = ["violet", "rose", "ocean", "forest", "sunset", "midnight"];
  const THEME_HEX = { violet:"#7c3aed", rose:"#e11d6b", ocean:"#0ea5e9", forest:"#10b981", sunset:"#f97316", midnight:"#4f46e5" };

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

  function fmtDate(iso) {
    if (!iso) return "Date TBD";
    return new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric",
      year: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function toLocalInput(iso) {
    if (!iso) return "";
    const d = new Date(iso); const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function shareUrl(t) { return `${location.origin}/e/${t}`; }
  function manageUrl() { return `${location.origin}/m/${token}`; }

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

  async function load() {
    try {
      const [event, summary] = await Promise.all([api(""), api("/summary")]);
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
    const img = e.image_path
      ? `<div class="img" style="background-image:url('${esc(e.image_path)}')"><div class="upload-btn" id="img-btn">📷 Change image</div></div>`
      : `<div class="img"><div class="ph">🖼️</div><div class="upload-btn" id="img-btn">📷 Upload image</div></div>`;

    const rsvps = [...e.rsvps].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
    const rsvpRows = rsvps.length ? rsvps.map(rsvpRowHTML).join("")
      : `<p class="g-sub" style="padding:8px 0">No responses yet.</p>`;
    const inviteRows = e.invites.length ? e.invites.map((i) => `
      <div class="guest-row">
        <div><div class="g-name">${esc(i.guest_name || i.guest_email)}</div>
          <div class="g-sub">${esc(i.guest_email)}${i.sent_at ? " · ✉️ invited" : " · not emailed"}</div></div>
        <button class="btn btn-line btn-sm" data-copy="${esc(location.origin)}/i/${esc(i.token)}">Copy link</button>
      </div>`).join("") : `<p class="g-sub" style="padding:8px 0">No guests added yet.</p>`;

    $("#manage-content").innerHTML = `
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
            <button class="btn btn-ghost btn-sm" id="edit-btn">✎ Edit details</button>
            <a class="btn btn-line btn-sm" href="/e/${esc(e.public_token)}" target="_blank">👁 Preview invite</a>
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
          <div class="panel"><h4>Share link</h4>
            <p class="g-sub" style="margin-bottom:10px">Anyone with this link can RSVP.</p>
            <div class="share-box">
              <input readonly value="${esc(shareUrl(e.public_token))}">
              <button class="btn btn-primary btn-sm" data-copy="${esc(shareUrl(e.public_token))}">Copy</button>
            </div>
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
        </div>
      </div>`;

    $("#edit-btn").onclick = () => openEditModal(e);
    $("#del-btn").onclick = () => confirmDelete(e);
    $("#img-btn").onclick = () => $("#hidden-file").click();
    $("#add-invites-btn").onclick = () => addInvites();
    document.querySelectorAll("[data-copy]").forEach((b) =>
      b.addEventListener("click", () => copy(b.dataset.copy)));
  }

  function rsvpRowHTML(r) {
    const pill = `<span class="pill ${r.status}">${r.status === "yes" ? "Going" : r.status === "no" ? "Can't go" : "Maybe"}</span>`;
    const extra = r.status === "yes" && r.party_size > 1 ? ` · party of ${r.party_size}` : "";
    return `<div class="guest-row"><div>
      <div class="g-name">${esc(r.guest_name)} ${pill}</div>
      <div class="g-sub">${esc(r.guest_email || "no email")}${extra}${r.message ? ` · "${esc(r.message)}"` : ""}</div>
    </div></div>`;
  }

  // ── edit modal ──
  function openEditModal(e) {
    const swatches = THEMES.map((t) =>
      `<div class="sw ${t === e.theme ? "sel" : ""}" data-t="${t}" style="background:${THEME_HEX[t]}"></div>`).join("");
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
        <div class="field"><label>Description</label><textarea id="f-desc">${esc(e.description)}</textarea></div>
        <div class="field"><label>Theme</label><div class="theme-pick" id="theme-pick">${swatches}</div></div>
        <div class="field"><label style="display:flex;gap:8px;align-items:center;cursor:pointer">
          <input type="checkbox" id="f-plus" style="width:auto" ${e.allow_plus_ones ? "checked" : ""}> Allow +1s</label></div>
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
          location: $("#f-loc").value.trim(),
          description: $("#f-desc").value,
          theme,
          allow_plus_ones: $("#f-plus").checked,
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

  // ── image upload ──
  $("#hidden-file").addEventListener("change", async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    toast("Uploading image…");
    try { await api("/image", { method: "POST", form: fd }); toast("Image updated"); load(); }
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

  // ── modal helpers ──
  function mountModal(html) {
    $("#modal-root").innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
    const bg = $(".modal-bg");
    bg.addEventListener("click", (e) => { if (e.target === bg) closeModal(); });
    bg.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
  }
  function closeModal() { $("#modal-root").innerHTML = ""; }

  load();
})();
