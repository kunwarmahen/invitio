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
  // Markup for the tone-picker + "Generate" row shown under the description box.
  window.invitioGenRow = function () {
    const opts = window.INVITIO_TONES
      .map(([v, label]) => `<option value="${v}">${label}</option>`).join("");
    return `<div class="row" style="gap:8px;margin-top:6px;align-items:center;flex-wrap:wrap">
      <select id="gen-tone" class="field" title="Tone of voice" style="margin:0;width:auto;flex:0 0 auto">${opts}</select>
      <button type="button" class="btn btn-line btn-sm" id="gen-desc" style="flex:0 0 auto">✨ Generate with AI</button>
    </div>`;
  };
})();
