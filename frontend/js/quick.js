/* invitio quick-create — make one event with no account, then go to /m/<token>. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const THEMES = ["violet", "rose", "ocean", "forest", "sunset", "midnight"];
  const THEME_HEX = { violet:"#7c3aed", rose:"#e11d6b", ocean:"#0ea5e9", forest:"#10b981", sunset:"#f97316", midnight:"#4f46e5" };

  let toastTimer;
  function toast(msg, err = false) {
    const el = $("#toast"); el.textContent = msg; el.classList.toggle("err", err); el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  let theme = "violet";
  $("#theme-pick").innerHTML = THEMES.map((t) =>
    `<div class="sw ${t === theme ? "sel" : ""}" data-t="${t}" style="background:${THEME_HEX[t]}"></div>`).join("");
  $("#theme-pick").querySelectorAll("[data-t]").forEach((sw) =>
    sw.addEventListener("click", () => {
      theme = sw.dataset.t;
      document.body.setAttribute("data-theme", theme);
      $("#theme-pick").querySelectorAll(".sw").forEach((s) => s.classList.remove("sel"));
      sw.classList.add("sel");
    }));

  $("#quick-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const dateVal = $("#f-date").value, endVal = $("#f-end").value;
    const email = $("#f-email").value.trim();
    const body = {
      title: $("#f-title").value.trim(),
      host_display_name: $("#f-host").value.trim(),
      event_date: dateVal ? new Date(dateVal).toISOString() : null,
      event_end: endVal ? new Date(endVal).toISOString() : null,
      location: $("#f-loc").value.trim(),
      description: $("#f-desc").value,
      theme,
      allow_plus_ones: $("#f-plus").checked,
      host_email: email || null,
    };
    const btn = $("#submit"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await fetch("/api/public/events", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Could not create the event.");
      // Remember the manage link locally as a convenience fallback.
      try {
        const saved = JSON.parse(localStorage.getItem("invitio_my_events") || "[]");
        saved.unshift({ title: body.title, manage_token: data.manage_token, at: Date.now() });
        localStorage.setItem("invitio_my_events", JSON.stringify(saved.slice(0, 20)));
      } catch (_) {}
      location.href = `/m/${data.manage_token}?created=1`;
    } catch (err) {
      toast(err.message, true);
      btn.disabled = false; btn.textContent = "Create event";
    }
  });
})();
