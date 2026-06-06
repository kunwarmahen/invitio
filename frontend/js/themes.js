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
})();
