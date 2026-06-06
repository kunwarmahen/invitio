/* invitio color-scheme resolver. Loaded *blocking in <head>* on every page so the
   right scheme is set on <html> before first paint (no flash). Preference is
   "system" | "light" | "dark" (default system); stored in localStorage and
   resolved against the OS setting. window.invitioScheme lets the topbar toggle
   cycle it. */
(function () {
  "use strict";
  var KEY = "invitio_scheme";
  var ORDER = ["system", "light", "dark"];

  function stored() {
    try { return localStorage.getItem(KEY) || "system"; } catch (_) { return "system"; }
  }
  function systemDark() {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  function resolve(pref) {
    pref = pref || stored();
    return pref === "system" ? (systemDark() ? "dark" : "light") : pref;
  }
  function apply(pref) {
    document.documentElement.setAttribute("data-scheme", resolve(pref));
  }

  apply(); // run immediately, before body paints

  window.invitioScheme = {
    get: stored,
    resolve: resolve,
    set: function (pref) {
      try { localStorage.setItem(KEY, pref); } catch (_) {}
      apply(pref);
      return pref;
    },
    // cycle system → light → dark → system, returns the new preference
    cycle: function () {
      var next = ORDER[(ORDER.indexOf(stored()) + 1) % ORDER.length];
      return this.set(next);
    },
  };

  // Follow the OS while the preference is "system".
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () { if (stored() === "system") apply(); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }
})();
