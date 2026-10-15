/* Content protection (deterrents).
 * Browsers cannot technically prevent OS-level screenshots, phone cameras or a determined developer.
 * These measures stop casual copying: context menu, devtools/view-source/save/print shortcuts,
 * text selection and copy, image dragging, printing, and they hide the page when it loses focus
 * (e.g. when a snipping tool opens) or when developer tools appear to be open.
 */
(() => {
  "use strict";
  const shield = document.getElementById("shield");
  const editable = (el) => el && (el.closest("input, textarea, select, [contenteditable]"));
  const hide = (on) => { document.body.classList.toggle("shielded", !!on); };

  document.addEventListener("contextmenu", (e) => { if (!editable(e.target)) e.preventDefault(); });
  ["copy", "cut", "dragstart", "selectstart"].forEach((t) =>
    document.addEventListener(t, (e) => { if (!editable(e.target)) e.preventDefault(); }));

  document.addEventListener("keydown", (e) => {
    const k = (e.key || "").toLowerCase(), mod = e.ctrlKey || e.metaKey;
    const blocked =
      k === "f12" ||
      (mod && e.shiftKey && ["i", "j", "c", "k", "s", "3", "4", "5"].includes(k)) ||   // devtools, mac screenshot combos
      (mod && e.altKey && ["i", "j", "c", "u"].includes(k)) ||                          // mac devtools / view source
      (mod && ["u", "s", "p"].includes(k)) ||                                           // view source, save, print
      k === "printscreen";
    if (blocked) {
      e.preventDefault(); e.stopPropagation();
      if (k === "printscreen" && navigator.clipboard) navigator.clipboard.writeText("").catch(() => {});
      hide(true); setTimeout(() => hide(false), 1200);
    }
  }, true);
  document.addEventListener("keyup", (e) => {
    if ((e.key || "").toLowerCase() === "printscreen") {
      if (navigator.clipboard) navigator.clipboard.writeText("").catch(() => {});
      hide(true); setTimeout(() => hide(false), 1200);
    }
  });

  // page hidden while the window is not focused (snipping tools, screen recorders, tab switches)
  window.addEventListener("blur", () => hide(true));
  window.addEventListener("focus", () => hide(false));
  document.addEventListener("visibilitychange", () => hide(document.hidden));
  window.addEventListener("beforeprint", () => hide(true));
  window.addEventListener("afterprint", () => hide(false));

  // devtools heuristic: docked devtools shrink the inner viewport a lot relative to the window
  let devtools = false;
  setInterval(() => {
    const gapW = window.outerWidth - window.innerWidth, gapH = window.outerHeight - window.innerHeight;
    const open = window.outerWidth > 0 && (gapW > 200 || gapH > 260);
    if (open !== devtools) { devtools = open; document.body.classList.toggle("devtools", open); }
  }, 800);

  if (shield) shield.addEventListener("click", () => hide(false));
})();
