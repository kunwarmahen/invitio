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

  let toastTimer;
  function toast(msg, isErr = false) {
    const el = $("#toast");
    el.textContent = msg; el.classList.toggle("err", isErr); el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  function fmtDate(iso) {
    if (!iso) return "Date to be announced";
    return new Date(iso).toLocaleString(undefined, { weekday: "long", month: "long",
      day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
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
    $("#rsvp-root").innerHTML = `
      <div class="env-stage" id="env-stage">
        <div class="env-prompt">✦ You're invited <span class="tap">· tap to open</span></div>
        <div class="envelope" id="envelope" role="button" tabindex="0" aria-label="Open invitation">
          <div class="env-back"></div>
          <div class="env-letter"><div class="el-in">
            <div class="el-mark">✦</div>
            <div class="el-host">${esc(e.host_display_name || "You're")} invites you to</div>
            <div class="el-title">${esc(e.title)}</div>
          </div></div>
          <div class="env-pocket"></div>
          <div class="env-flap"></div>
          <div class="env-seal">✦</div>
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
    if (!e.image_path) return `<div class="invite-hero"><div class="ph">🎉</div></div>`;
    const url = esc(e.image_path);
    const hint = `<div class="zoom-hint">⤢ View full image</div>`;
    if (e.image_fit === "contain") {
      return `<div class="invite-hero contain zoomable" id="hero" style="--bgimg:url('${url}')">
        <img class="hero-img" src="${url}" alt="${esc(e.title)}">${hint}</div>`;
    }
    return `<div class="invite-hero zoomable" id="hero" style="background-image:url('${url}')">${hint}</div>`;
  }

  function openLightbox() {
    if (!event.image_path) return;
    const lb = document.createElement("div");
    lb.className = "lightbox";
    lb.innerHTML = `<button class="lb-close" aria-label="Close">×</button><img src="${esc(event.image_path)}" alt="${esc(event.title)}">`;
    const close = () => lb.remove();
    lb.addEventListener("click", close);
    document.body.appendChild(lb);
    document.addEventListener("keydown", function esc2(ev) {
      if (ev.key === "Escape") { close(); document.removeEventListener("keydown", esc2); }
    });
  }

  function render() {
    const e = event;
    const hero = heroHTML(e);

    const existing = e.existing_rsvp;
    const plusOne = e.allow_plus_ones;

    $("#rsvp-root").innerHTML = `
      <div class="invite-card">
        ${hero}
        <div class="invite-body">
          <div class="invite-kicker">${esc(e.host_display_name || "You")} invites you to</div>
          <h1 class="invite-title">${esc(e.title)}</h1>

          <div class="invite-detail"><span class="ic">📅</span><div><b>When</b><br>${esc(fmtDate(e.event_date))}</div></div>
          ${e.location ? `<div class="invite-detail"><span class="ic">📍</span><div><b>Where</b><br>${esc(e.location)}</div></div>` : ""}
          ${e.description ? `<p class="invite-desc">${esc(e.description)}</p>` : ""}
          ${calendarHTML()}

          <div class="rsvp-form" id="form-area">
            <h3 style="font-size:20px;margin-bottom:14px">Will you be there?</h3>
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
            <div class="field"><label>Note to the host (optional)</label>
              <textarea id="r-msg" placeholder="Can't wait! / Running late / dietary notes…">${esc(existing ? existing.message : "")}</textarea></div>
            <button class="btn btn-primary" id="rsvp-submit" style="width:100%;font-size:16px;padding:15px">
              ${existing ? "Update my RSVP" : "Send RSVP"}</button>
          </div>
        </div>
      </div>`;

    // status buttons
    const pick = $("#status-pick");
    pick.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      chosenStatus = b.dataset.on;
      pick.querySelectorAll("button").forEach((x) => x.classList.remove("sel"));
      b.classList.add("sel");
      $("#party-field").style.display = (plusOne && chosenStatus === "yes") ? "block" : "none";
    }));

    // preselect existing response
    if (existing) {
      const btn = pick.querySelector(`[data-on="${existing.status}"]`);
      if (btn) btn.click();
    }

    $("#rsvp-submit").addEventListener("click", submit);
    wireCalendar();
    const heroEl = $("#hero");
    if (heroEl && event.image_path) heroEl.addEventListener("click", openLightbox);
  }

  async function submit() {
    if (!chosenStatus) { toast("Please pick Yes, Maybe, or No", true); return; }
    const name = $("#r-name").value.trim();
    if (!name) { toast("Please enter your name", true); return; }
    const email = $("#r-email").value.trim();
    const partyEl = $("#r-party");
    const party = (chosenStatus === "yes" && event.allow_plus_ones && partyEl)
      ? Math.max(1, parseInt(partyEl.value, 10) || 1) : 1;

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
    if (status === "yes") wireCalendar();
    $("#edit-again").addEventListener("click", () => load(true));
  }

  load();
})();
