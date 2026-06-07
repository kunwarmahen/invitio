/* invitio public RSVP page — no auth. Reads the token from the URL path:
   /e/<token> = shareable event link, /i/<token> = personalized invite link. */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

  const parts = location.pathname.split("/").filter(Boolean); // ["e"|"i", token]
  const kind = parts[0];          // "e" or "i"
  const token = parts[1] || "";
  const isInvite = kind === "i";

  let event = null;
  let chosenStatus = null;
  let viewLogged = false;

  // Tell the host this invite was actually opened (in a real browser, so link-
  // preview bots that don't run JS don't count). Fired once per page open;
  // sendBeacon survives the page being navigated away. Purely best-effort.
  function logView() {
    if (viewLogged) return;
    viewLogged = true;
    const url = `/api/public/view/${token}`;
    try {
      if (navigator.sendBeacon && navigator.sendBeacon(url)) return;
    } catch (_) {}
    fetch(url, { method: "POST", keepalive: true }).catch(() => {});
  }

  // Decorative motif for the event's template (e.g. 🎂 for birthday), used on the
  // envelope and the empty-image placeholder. Falls back to ✦.
  const motif = () => (window.invitioMotif ? window.invitioMotif(event && event.theme) : "✦");

  // ── Location maps (keyless: Google "search" link + embeddable map) ──
  const mapsLink = (loc) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc)}`;
  const mapEmbed = (loc) => `https://www.google.com/maps?q=${encodeURIComponent(loc)}&output=embed`;
  function mapBlockHTML(e) {
    if (!e.location) return "";
    return `<iframe class="map-embed" loading="lazy" referrerpolicy="no-referrer-when-downgrade"
      allowfullscreen title="Map to ${esc(e.location)}" src="${esc(mapEmbed(e.location))}"></iframe>`;
  }

  let toastTimer;
  function toast(msg, isErr = false) {
    const el = $("#toast");
    el.textContent = msg; el.classList.toggle("err", isErr); el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Link copied — paste it anywhere"); }
    catch { toast("Copy failed — select manually", true); }
  }

  // ── "Invite a friend" forwardable share ───────────────────────────────────
  // Always shares the public event link (/e/<public_token>), never a personal
  // invite token — so a forwarded link can't let a friend RSVP as the guest.
  const NATIVE_SHARE = typeof navigator !== "undefined" && !!navigator.share;
  function friendUrl() { return `${location.origin}/e/${event.public_token}`; }
  function inviteFriendHTML(e) {
    if (!e.public_token) return "";
    const url = friendUrl();
    const title = e.title || "this event";
    const text = `You're invited to ${title}! RSVP here: ${url}`;
    const t = encodeURIComponent(text);
    const subj = encodeURIComponent(`You're invited: ${title}`);
    return `<div class="wall-section invite-friend">
      <h3 style="font-size:18px;margin:0 0 6px">Know someone who'd love this?</h3>
      <p class="g-sub" style="margin:0 0 12px">Forward the invite — they can RSVP too.</p>
      <div class="share-actions">
        <a class="btn btn-line btn-sm" href="https://wa.me/?text=${t}" target="_blank" rel="noopener">💬 WhatsApp</a>
        <a class="btn btn-line btn-sm" href="sms:?&body=${t}">📱 SMS</a>
        <a class="btn btn-line btn-sm" href="mailto:?subject=${subj}&body=${t}">✉️ Email</a>
        ${NATIVE_SHARE
          ? `<button class="btn btn-line btn-sm" id="friend-share">📤 Share…</button>`
          : `<button class="btn btn-line btn-sm" id="friend-copy">🔗 Copy link</button>`}
      </div>
    </div>`;
  }
  function wireInviteFriend() {
    const s = $("#friend-share");
    if (s) s.addEventListener("click", () =>
      navigator.share({ title: event.title, text: `You're invited to ${event.title}!`, url: friendUrl() }).catch(() => {}));
    const c = $("#friend-copy");
    if (c) c.addEventListener("click", () => copy(friendUrl()));
  }

  // Soft RSVP-by note above the form: a gentle "please RSVP by …" before the
  // deadline, and a still-open "were requested by …" after it (responses are
  // never blocked — the cutoff is just to help the host plan a headcount).
  function deadlineNoteHTML(e) {
    if (!e.rsvp_deadline) return "";
    const when = fmtDate(e.rsvp_deadline);
    const past = new Date(e.rsvp_deadline).getTime() < Date.now();
    const text = past
      ? `RSVPs were requested by ${esc(when)} — you can still respond.`
      : `Please RSVP by ${esc(when)}.`;
    return `<p class="g-sub" style="margin:-4px 0 14px">⏰ ${text}</p>`;
  }

  function fmtDate(iso) {
    if (!iso) return "Date to be announced";
    const opts = { weekday: "long", month: "long", day: "numeric", year: "numeric",
      hour: "numeric", minute: "2-digit" };
    // Render in the event's own timezone so every guest sees the same local time
    // (e.g. a 6pm New York party shows "6:00 PM EDT" to a guest in London too).
    if (event.timezone) { opts.timeZone = event.timezone; opts.timeZoneName = "short"; }
    return new Date(iso).toLocaleString(undefined, opts);
  }

  // ── Add to Calendar ─────────────────────────────────────────────────────
  // Format a Date as UTC basic ICS/Google form: YYYYMMDDTHHMMSSZ
  function calStamp(d) {
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}${p(d.getUTCMonth()+1)}${p(d.getUTCDate())}T` +
           `${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`;
  }
  function calRange() {
    if (!event.event_date) return null;
    const start = new Date(event.event_date);
    // End = explicit end, else +2h from start.
    const end = event.event_end ? new Date(event.event_end)
      : new Date(start.getTime() + 2 * 60 * 60 * 1000);
    return { start, end };
  }
  function googleCalUrl() {
    const r = calRange();
    if (!r) return null;
    const q = new URLSearchParams({
      action: "TEMPLATE",
      text: event.title,
      dates: `${calStamp(r.start)}/${calStamp(r.end)}`,
      details: event.description || `Hosted by ${event.host_display_name || ""}`.trim(),
      location: event.location || "",
    });
    // Dates are absolute (UTC Z); ctz tells Google to display them in the event's
    // timezone rather than the viewer's.
    if (event.timezone) q.set("ctz", event.timezone);
    return `https://calendar.google.com/calendar/render?${q.toString()}`;
  }
  function downloadIcs() {
    const r = calRange();
    if (!r) { toast("No date set for this event", true); return; }
    const esc2 = (s) => String(s || "").replace(/[\\;,]/g, (c) => "\\" + c).replace(/\n/g, "\\n");
    const ics = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//invitio//EN",
      "BEGIN:VEVENT",
      `UID:${token}@invitio`,
      `DTSTAMP:${calStamp(new Date())}`,
      `DTSTART:${calStamp(r.start)}`,
      `DTEND:${calStamp(r.end)}`,
      `SUMMARY:${esc2(event.title)}`,
      `DESCRIPTION:${esc2(event.description)}`,
      `LOCATION:${esc2(event.location)}`,
      "END:VEVENT", "END:VCALENDAR",
    ].join("\r\n");
    const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(event.title || "event").replace(/[^\w]+/g, "-").toLowerCase()}.ics`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function calendarHTML() {
    if (!event.event_date) return "";
    return `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:18px">
        <a class="btn btn-line btn-sm" id="gcal" target="_blank" rel="noopener">📅 Google Calendar</a>
        <button class="btn btn-line btn-sm" id="ics">⬇️ Apple / Outlook (.ics)</button>
      </div>`;
  }
  function wireCalendar() {
    const g = $("#gcal"); if (g) { const u = googleCalUrl(); if (u) g.href = u; }
    const i = $("#ics"); if (i) i.addEventListener("click", downloadIcs);
  }

  const SEEN_KEY = `invitio_opened_${token}`;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  async function load(skipEnvelope = false) {
    try {
      const path = isInvite ? `/public/invite/${token}` : `/public/event/${token}`;
      const res = await fetch(`/api${path}`);
      if (!res.ok) throw new Error("This invitation link is invalid or has expired.");
      event = await res.json();
      logView();
      document.body.setAttribute("data-theme", event.theme || "violet");
      // First visit this session → play the envelope reveal. Re-renders (e.g.
      // "change my response") and reduced-motion users go straight to the card.
      let alreadySeen = true;
      try { alreadySeen = sessionStorage.getItem(SEEN_KEY) === "1"; } catch (_) {}
      if (!skipEnvelope && !alreadySeen && !reducedMotion) {
        showEnvelope();
      } else {
        render();
      }
    } catch (err) {
      $("#rsvp-root").innerHTML = `<div class="invite-card"><div class="invite-body">
        <div class="confirm"><div class="big">🤔</div><h3>Hmm…</h3><p>${esc(err.message)}</p></div>
      </div></div>`;
    }
  }

  // ── envelope reveal ───────────────────────────────────────────────────────
  function showEnvelope() {
    const e = event;
    // The "letter" that rises out is a mini of the real invitation: the host's
    // own image (Punchbowl-style) when there is one, else a typeset card.
    const letterInner = e.image_path
      ? `<div class="el-photo" style="background-image:url('${esc(e.image_thumb_path || e.image_path)}')"></div>
         <div class="el-overlay"><div class="el-title">${esc(e.title)}</div>
           <div class="el-host">${esc(e.host_display_name ? e.host_display_name + " invites you" : "You're invited")}</div></div>`
      : `<div class="el-text">
           <div class="el-mark">${motif()}</div>
           <div class="el-host">${esc(e.host_display_name || "You're")} invites you to</div>
           <div class="el-title">${esc(e.title)}</div>
         </div>`;
    $("#rsvp-root").innerHTML = `
      <div class="env-stage" id="env-stage">
        <div class="env-prompt">${motif()} You're invited <span class="tap">· tap to open</span></div>
        <div class="envelope${e.image_path ? " has-photo" : ""}" id="envelope" role="button" tabindex="0" aria-label="Open invitation">
          <div class="env-back"></div>
          <div class="env-letter">${letterInner}</div>
          <div class="env-pocket"></div>
          <div class="env-flap"></div>
          <div class="env-seal">${motif()}</div>
        </div>
      </div>`;
    const env = $("#envelope");
    const open = () => openEnvelope();
    env.addEventListener("click", open, { once: true });
    env.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } });
  }

  function openEnvelope() {
    try { sessionStorage.setItem(SEEN_KEY, "1"); } catch (_) {}
    const env = $("#envelope");
    const prompt = $(".env-prompt");
    if (prompt) prompt.style.opacity = "0";
    env.classList.add("opening");
    // After the flap opens + letter rises, fly the envelope away and reveal.
    setTimeout(() => env.classList.add("leaving"), 1150);
    setTimeout(() => { render(); const card = $(".invite-card"); if (card) card.classList.add("reveal-in"); }, 1500);
  }

  function heroHTML(e) {
    if (!e.image_path) return `<div class="invite-hero"><div class="ph">${motif()}</div></div>`;
    const url = esc(e.image_path);
    if (e.image_fit === "contain") {
      // Whole image, height-capped over a blurred backdrop; tap to enlarge.
      return `<div class="invite-hero contain zoomable" id="hero" style="--bgimg:url('${url}')">
        <img class="hero-img" src="${url}" alt="${esc(e.title)}">
        <div class="zoom-hint">⤢ Tap to enlarge</div></div>`;
    }
    // Cover: crop to fill, positioned at the host's chosen focal point so the
    // subject stays visible.
    const pos = `${e.image_focal_x ?? 50}% ${e.image_focal_y ?? 50}%`;
    return `<div class="invite-hero zoomable" id="hero" style="background-image:url('${url}');background-position:${pos}">
      <div class="zoom-hint">⤢ View full image</div></div>`;
  }

  // All gallery images (cover first), used by the lightbox carousel.
  function galleryImages(e) {
    const imgs = (e.images || []).slice().sort((a, b) => (b.is_cover - a.is_cover) || (a.position - b.position));
    if (imgs.length) return imgs.map((i) => i.path);
    return e.image_path ? [e.image_path] : [];
  }

  // Non-cover photos shown as a tappable strip under the invite body.
  function galleryStripHTML(e) {
    const extras = (e.images || []).filter((i) => !i.is_cover)
      .sort((a, b) => a.position - b.position);
    if (!extras.length) return "";
    const thumbs = extras.map((i) => {
      const all = galleryImages(e);
      const idx = all.indexOf(i.path);
      return `<div class="gthumb" data-gidx="${idx}" style="background-image:url('${esc(i.thumb_path || i.path)}')"></div>`;
    }).join("");
    return `<div class="wall-section"><h3 style="font-size:18px;margin:0 0 10px">Photos</h3>
      <div class="gallery-strip" id="gallery-strip">${thumbs}</div></div>`;
  }

  function openLightbox(startIndex = 0) {
    const imgs = galleryImages(event);
    if (!imgs.length) return;
    let i = Math.max(0, Math.min(startIndex, imgs.length - 1));
    const multi = imgs.length > 1;
    const lb = document.createElement("div");
    lb.className = "lightbox";
    lb.innerHTML = `<button class="lb-close" aria-label="Close">×</button>
      ${multi ? `<button class="lb-nav prev" aria-label="Previous">‹</button>
                 <button class="lb-nav next" aria-label="Next">›</button>` : ""}
      <img src="${esc(imgs[i])}" alt="${esc(event.title)}">
      ${multi ? `<div class="lb-count"></div>` : ""}`;
    const imgEl = lb.querySelector("img");
    const countEl = lb.querySelector(".lb-count");
    const show = (n) => {
      i = (n + imgs.length) % imgs.length;
      imgEl.src = imgs[i];
      if (countEl) countEl.textContent = `${i + 1} / ${imgs.length}`;
    };
    if (multi) show(i);
    const close = () => { lb.remove(); document.removeEventListener("keydown", onKey); };
    function onKey(ev) {
      if (ev.key === "Escape") close();
      else if (multi && ev.key === "ArrowLeft") show(i - 1);
      else if (multi && ev.key === "ArrowRight") show(i + 1);
    }
    lb.addEventListener("click", (ev) => {
      if (ev.target.classList.contains("lb-nav")) {
        ev.stopPropagation();
        show(i + (ev.target.classList.contains("next") ? 1 : -1));
      } else { close(); }
    });
    document.body.appendChild(lb);
    document.addEventListener("keydown", onKey);
  }

  // ── Custom host questions ─────────────────────────────────────────────────
  function questionsHTML(e) {
    const qs = e.questions || [];
    if (!qs.length) return "";
    const ans = {};
    ((e.existing_rsvp && e.existing_rsvp.answers) || []).forEach((a) => { ans[a.question_id] = a.value; });
    const rows = qs.map((q) => {
      const star = q.required ? ' <span style="color:#e11d48">*</span>' : "";
      const label = `<label>${esc(q.prompt)}${star}</label>`;
      if (q.qtype === "choice" || q.qtype === "multi") {
        const multi = q.qtype === "multi";
        const sel = multi ? (Array.isArray(ans[q.id]) ? ans[q.id] : []) : ans[q.id];
        const opts = (q.options || []).map((o) => {
          const on = multi ? sel.includes(o) : sel === o;
          const attr = multi ? `data-qm="${q.id}"` : `type="radio" name="q-${q.id}" data-qc="${q.id}"`;
          const type = multi ? `type="checkbox"` : "";
          return `<label class="q-opt"><input ${type} ${attr} value="${esc(o)}" ${on ? "checked" : ""}> ${esc(o)}</label>`;
        }).join("");
        return `<div class="field">${label}<div class="q-opts">${opts}</div></div>`;
      }
      return `<div class="field">${label}
        <input data-q="${q.id}" value="${esc(ans[q.id] || "")}" placeholder="Your answer"></div>`;
    }).join("");
    return `<div id="questions-area" style="display:none">${rows}</div>`;
  }

  function collectAnswers() {
    return (event.questions || []).map((q) => {
      if (q.qtype === "choice") {
        const el = $(`[data-qc="${q.id}"]:checked`);
        return { question_id: q.id, value: el ? el.value : "" };
      }
      if (q.qtype === "multi") {
        const els = [...document.querySelectorAll(`[data-qm="${q.id}"]:checked`)];
        return { question_id: q.id, value: els.map((x) => x.value) };
      }
      const el = $(`[data-q="${q.id}"]`);
      return { question_id: q.id, value: el ? el.value.trim() : "" };
    });
  }

  // ── Guest wall + who's-coming ─────────────────────────────────────────────
  function comingHTML(e) {
    if (!e.guestlist_public) return "";
    const list = e.coming || [];
    const total = list.reduce((n, c) => n + (c.party_size || 1), 0);
    const names = list.length
      ? list.map((c) => `<span class="coming-chip">${esc(c.guest_name)}${c.party_size > 1 ? ` +${c.party_size - 1}` : ""}</span>`).join("")
      : `<p class="g-sub" style="padding:4px 0">No one's said yes yet — be the first!</p>`;
    return `<div class="wall-section">
      <h3 style="font-size:18px;margin:0 0 10px">Who's coming${total ? ` (${total})` : ""}</h3>
      <div class="coming-list">${names}</div></div>`;
  }

  function wallPostHTML(p) {
    return `<div class="wall-post">
      <div class="wall-msg">${esc(p.message)}</div>
      <div class="g-sub">— ${esc(p.guest_name)}</div></div>`;
  }

  function wallHTML(e) {
    if (!e.wall_enabled) return "";
    const posts = (e.wall_posts || []).map(wallPostHTML).join("");
    return `<div class="wall-section">
      <h3 style="font-size:18px;margin:0 0 10px">Guest wall</h3>
      <div class="wall-form">
        <input id="wall-name" placeholder="Your name" value="${esc((event.existing_rsvp && event.existing_rsvp.guest_name) || event.guest_name || "")}">
        <textarea id="wall-msg" placeholder="Leave a well-wish…"></textarea>
        <button class="btn btn-line btn-sm" id="wall-post">Post to the wall</button>
      </div>
      <div id="wall-list" style="margin-top:14px">${posts ||
        `<p class="g-sub" style="padding:4px 0">No messages yet — say something nice!</p>`}</div>
    </div>`;
  }

  async function submitWallPost() {
    const name = $("#wall-name").value.trim();
    const message = $("#wall-msg").value.trim();
    if (!name || !message) { toast("Add your name and a message", true); return; }
    const btn = $("#wall-post"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await fetch(`/api/public/wall/${token}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guest_name: name, message }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't post — please try again");
      const list = $("#wall-list");
      if (list.querySelector(".g-sub")) list.innerHTML = "";
      list.insertAdjacentHTML("afterbegin", wallPostHTML(data));
      $("#wall-msg").value = "";
      toast("Posted to the wall 🎉");
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; btn.textContent = "Post to the wall"; }
  }

  // Notice shown in place of the RSVP form once the host has cancelled the event.
  function cancelledNoticeHTML(e) {
    return `<div class="cancelled-notice">
      <div class="big">⊘</div>
      <h3>This event has been cancelled</h3>
      ${e.cancellation_message
        ? `<p class="cancel-note">${esc(e.cancellation_message)}</p>`
        : `<p class="g-sub">The host has called off this event.</p>`}
    </div>`;
  }

  function render() {
    const e = event;
    const hero = heroHTML(e);
    const cancelled = !!e.cancelled_at;

    const existing = e.existing_rsvp;
    const plusOne = e.allow_plus_ones;

    $("#rsvp-root").innerHTML = `
      <div class="invite-card${cancelled ? " is-cancelled" : ""}">
        ${hero}
        <div class="invite-body">
          ${cancelled ? `<div class="cancel-banner"><strong>⊘ Cancelled</strong></div>` : ""}
          <div class="invite-kicker">${esc(e.host_display_name || "You")} invites you to</div>
          <h1 class="invite-title">${esc(e.title)}</h1>

          <div class="invite-detail"><span class="ic">📅</span><div><b>When</b><br>${esc(fmtDate(e.event_date))}</div></div>
          ${e.location ? `<div class="invite-detail"><span class="ic">📍</span><div><b>Where</b><br>${esc(e.location)}
            <br><a href="${esc(mapsLink(e.location))}" target="_blank" rel="noopener" class="map-link">Open in Maps ↗</a></div></div>` : ""}
          ${mapBlockHTML(e)}
          ${e.description ? `<p class="invite-desc">${esc(e.description)}</p>` : ""}
          ${calendarHTML()}

          ${cancelled ? cancelledNoticeHTML(e) : `
          <div class="rsvp-form" id="form-area">
            <h3 style="font-size:20px;margin-bottom:14px">Will you be there?</h3>
            ${deadlineNoteHTML(e)}
            <div class="status-pick" id="status-pick">
              <button data-on="yes"><span class="em">🎉</span>Yes</button>
              <button data-on="maybe"><span class="em">🤔</span>Maybe</button>
              <button data-on="no"><span class="em">😢</span>No</button>
            </div>
            <div class="field"><label>Your name *</label>
              <input id="r-name" value="${esc(existing ? existing.guest_name : e.guest_name)}" placeholder="Your full name"></div>
            <div class="field"><label>Email${isInvite ? "" : " (so the host can reach you)"}</label>
              <input id="r-email" type="email" value="${esc(existing ? existing.guest_email : e.guest_email)}" placeholder="you@example.com"></div>
            <div class="field" id="party-field" style="display:none"><label>How many in your party? (including you)</label>
              <input id="r-party" type="number" min="1" max="50" value="${existing && existing.party_size ? existing.party_size : 1}"></div>
            ${questionsHTML(e)}
            <div class="field"><label>Note to the host (optional)</label>
              <textarea id="r-msg" placeholder="Can't wait! / Running late / dietary notes…">${esc(existing ? existing.message : "")}</textarea></div>
            <button class="btn btn-primary" id="rsvp-submit" style="width:100%;font-size:16px;padding:15px">
              ${existing ? "Update my RSVP" : "Send RSVP"}</button>
          </div>`}
          ${galleryStripHTML(e)}
          ${comingHTML(e)}
          ${cancelled ? "" : inviteFriendHTML(e)}
          ${cancelled ? "" : wallHTML(e)}
        </div>
      </div>`;

    // Cancelled events show the notice instead of the form — skip all the form
    // wiring (the elements don't exist), but keep the gallery/calendar handlers.
    if (!cancelled) {
      const pick = $("#status-pick");
      pick.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        chosenStatus = b.dataset.on;
        pick.querySelectorAll("button").forEach((x) => x.classList.remove("sel"));
        b.classList.add("sel");
        $("#party-field").style.display = (plusOne && chosenStatus === "yes") ? "block" : "none";
        // Host questions only matter for attendees — hidden for a "no".
        const qa = $("#questions-area");
        if (qa) qa.style.display = (chosenStatus === "no") ? "none" : "block";
      }));

      // preselect existing response
      if (existing) {
        const btn = pick.querySelector(`[data-on="${existing.status}"]`);
        if (btn) btn.click();
      }

      $("#rsvp-submit").addEventListener("click", submit);
      const wallBtn = $("#wall-post");
      if (wallBtn) wallBtn.addEventListener("click", submitWallPost);
      wireInviteFriend();
    }
    wireCalendar();
    const heroEl = $("#hero");
    if (heroEl && event.image_path) heroEl.addEventListener("click", () => openLightbox(0));
    document.querySelectorAll("#gallery-strip .gthumb").forEach((t) =>
      t.addEventListener("click", () => openLightbox(parseInt(t.dataset.gidx, 10) || 0)));
  }

  async function submit() {
    if (!chosenStatus) { toast("Please pick Yes, Maybe, or No", true); return; }
    const name = $("#r-name").value.trim();
    if (!name) { toast("Please enter your name", true); return; }
    const email = $("#r-email").value.trim();
    const partyEl = $("#r-party");
    const party = (chosenStatus === "yes" && event.allow_plus_ones && partyEl)
      ? Math.max(1, parseInt(partyEl.value, 10) || 1) : 1;

    const answers = collectAnswers();
    if (chosenStatus !== "no") {
      for (const q of (event.questions || [])) {
        if (!q.required) continue;
        const a = answers.find((x) => x.question_id === q.id);
        const empty = !a || (Array.isArray(a.value) ? a.value.length === 0 : !a.value);
        if (empty) { toast(`Please answer: ${q.prompt}`, true); return; }
      }
    }

    const btn = $("#rsvp-submit"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await fetch(`/api/public/rsvp/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guest_name: name,
          guest_email: email || null,
          status: chosenStatus,
          party_size: party,
          message: $("#r-msg").value,
          answers,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong. Please try again.");
      showConfirm(chosenStatus, name);
    } catch (err) {
      toast(err.message, true);
      btn.disabled = false; btn.textContent = "Send RSVP";
    }
  }

  // Celebratory confetti burst on a "yes" — pure canvas, no dependencies.
  // Honours reduced-motion (callers skip it) and cleans itself up when done.
  function confettiBurst() {
    const colors = ["#7c3aed", "#f472b6", "#fbbf24", "#34d399", "#60a5fa", "#fb7185"];
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:9999";
    canvas.width = innerWidth; canvas.height = innerHeight;
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const DURATION = 2600;
    const pieces = Array.from({ length: 130 }, () => ({
      x: innerWidth / 2 + (Math.random() - 0.5) * 140,
      y: innerHeight / 3,
      vx: (Math.random() - 0.5) * 14,
      vy: Math.random() * -16 - 4,
      size: Math.random() * 6 + 4,
      color: colors[(Math.random() * colors.length) | 0],
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.3,
    }));
    const start = performance.now();
    (function frame(now) {
      const elapsed = now - start;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = Math.max(0, 1 - elapsed / DURATION);
      for (const p of pieces) {
        p.vy += 0.5;                 // gravity
        p.x += p.vx; p.y += p.vy; p.rot += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y); ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }
      if (elapsed < DURATION) requestAnimationFrame(frame);
      else canvas.remove();
    })(start);
  }

  function showConfirm(status, name) {
    const map = {
      yes: { em: "🎉", h: "You're going!", p: "We've let the host know. See you there!" },
      maybe: { em: "🤔", h: "Marked as maybe", p: "Thanks for letting the host know — update anytime." },
      no: { em: "💌", h: "Response received", p: "Sorry you can't make it. Thanks for letting us know!" },
    };
    const m = map[status];
    const cal = status === "yes" ? calendarHTML() : "";
    $("#form-area").innerHTML = `<div class="confirm">
      <div class="big">${m.em}</div>
      <h3>${m.h}</h3>
      <p>${esc(m.p)}</p>
      <div style="display:flex;justify-content:center">${cal}</div>
      <button class="btn btn-line btn-sm" style="margin-top:18px" id="edit-again">Change my response</button>
    </div>`;
    if (status === "yes") {
      wireCalendar();
      if (!reducedMotion) confettiBurst();
    }
    $("#edit-again").addEventListener("click", () => load(true));
  }

  load();
})();
