/* invitio shared template catalog — used by the host app, quick-create, the
   no-account manage page, and the public RSVP page. Keeping it in one file stops
   the theme list from drifting across those four scripts.

   Each template is a `data-theme` value (its palette lives in css/style.css) plus
   a swatch colour and a decorative motif emoji used on the invite (envelope seal,
   empty-hero placeholder) and on the picker swatch. The first six are the
   original plain accent themes; the rest are seasonal / occasion templates. */
(function () {
  "use strict";
  // ordered: classic accents first, then occasion/seasonal templates
  window.INVITIO_THEMES = [
    "violet", "rose", "ocean", "forest", "sunset", "midnight",
    "birthday", "wedding", "christmas", "halloween", "baby", "newyear", "autumn", "spring",
  ];
  window.INVITIO_THEME_HEX = {
    violet: "#7c3aed", rose: "#e11d6b", ocean: "#0ea5e9", forest: "#10b981",
    sunset: "#f97316", midnight: "#4f46e5",
    birthday: "#db2777", wedding: "#b08968", christmas: "#c0392b", halloween: "#ea580c",
    baby: "#38bdf8", newyear: "#ca8a04", autumn: "#b45309", spring: "#65a30d",
  };
  window.INVITIO_THEME_MOTIF = {
    violet: "✦", rose: "✦", ocean: "✦", forest: "✦", sunset: "✦", midnight: "✦",
    birthday: "🎂", wedding: "💍", christmas: "🎄", halloween: "🎃",
    baby: "🍼", newyear: "🎆", autumn: "🍂", spring: "🌸",
  };
  // Human labels for the picker tooltip (title attr).
  window.INVITIO_THEME_LABEL = {
    violet: "Violet", rose: "Rose", ocean: "Ocean", forest: "Forest",
    sunset: "Sunset", midnight: "Midnight",
    birthday: "Birthday", wedding: "Wedding", christmas: "Christmas", halloween: "Halloween",
    baby: "Baby shower", newyear: "New Year", autumn: "Autumn", spring: "Spring",
  };
  // Motif for a theme, falling back to the default mark.
  window.invitioMotif = function (theme) {
    return window.INVITIO_THEME_MOTIF[theme] || "✦";
  };

  // Tone presets for AI description generation. Keys are sent to the backend
  // (see ai_service.TONE_PRESETS); labels are shown in the picker. Kept here so
  // the host app and the no-account manage page expose the same list.
  window.INVITIO_TONES = [
    ["warm", "Warm"], ["funny", "Funny"], ["heartfelt", "Heartfelt"],
    ["elegant", "Elegant"], ["playful", "Playful"], ["exciting", "Exciting"],
    ["somber", "Somber"], ["casual", "Casual"],
  ];
  // Shown under a generate button when the LLM server is configured but offline
  // (it usually runs on a separate machine). The button is disabled in that case.
  window.INVITIO_LLM_DOWN_MSG =
    "The AI writing assistant is offline right now — please write this manually.";
  const llmDownNote = (up) => up ? "" :
    `<p class="g-sub" style="margin-top:6px;width:100%;color:#dc2626">${window.INVITIO_LLM_DOWN_MSG}</p>`;

  // Markup for the tone-picker + "Generate" row shown under the description box.
  // Pass up=false when the LLM is unreachable to disable it and show the notice.
  window.invitioGenRow = function (up = true) {
    const opts = window.INVITIO_TONES
      .map(([v, label]) => `<option value="${v}">${label}</option>`).join("");
    const dis = up ? "" : "disabled";
    return `<div class="row" style="gap:8px;margin-top:6px;align-items:center;flex-wrap:wrap">
      <select id="gen-tone" class="field" title="Tone of voice" style="margin:0;width:auto;flex:0 0 auto" ${dis}>${opts}</select>
      <button type="button" class="btn btn-line btn-sm" id="gen-desc" style="flex:0 0 auto" ${dis}>✨ Generate with AI</button>
      ${llmDownNote(up)}
    </div>`;
  };

  // Markup for the "intent + Draft" row inside the broadcast/message-guests modal.
  window.invitioBroadcastGenRow = function (up = true) {
    const dis = up ? "" : "disabled";
    return `<div class="row" style="align-items:center;margin-top:6px;flex-wrap:wrap">
      <input id="bc-intent" class="field" style="margin:0" placeholder="What's it about? (e.g. venue moved indoors)" ${dis}>
      <button type="button" class="btn btn-line btn-sm" id="bc-gen" style="flex:0 0 auto" ${dis}>✨ Draft</button>
      ${llmDownNote(up)}</div>`;
  };
})();
