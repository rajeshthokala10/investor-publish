(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ZONE_COLOR = { east: "#2a78d6", north: "#eb6834", south: "#1baf7a", west: "#eda100", outer: "#4a3aa7" };
  const fmt = new Intl.NumberFormat("en-IN");
  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;

  const ICONS = {
    metro: '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14M8 21l2-4M16 21l-2-4"/>',
    suburban_rail: '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14M8 21l2-4M16 21l-2-4"/>',
    road: '<path d="M8 21 11 3M16 3l3 18M13.5 6v2M13.5 12v2M13.5 18v1"/>',
    airport: '<path d="M2 13 22 5l-3 9-6-2-3 5-1-6z"/>',
    township: '<path d="M4 21V9h7v12M11 21V4h9v17M2 21h20M7 13h1M7 17h1M15 8h1M15 12h1M15 16h1"/>',
    water: '<path d="M12 3c4 6 6 9 6 12a6 6 0 0 1-12 0c0-3 2-6 6-12z"/>',
    governance: '<path d="M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-6 10 6z"/>',
    policy: '<path d="M6 3h9l4 4v14H6zM9 12h7M9 16h7"/>',
  };

  function relTime(iso) {
    if (!iso) return "";
    const d = new Date(iso); if (isNaN(d)) return "";
    const h = Math.round((Date.now() - d) / 36e5);
    if (h < 1) return "just now"; if (h < 24) return `${h}h ago`;
    const days = Math.round(h / 24); return days === 1 ? "yesterday" : `${days} days ago`;
  }

  function skyline(svg, seed = 7, w = 1440, h = 360) {
    let s = seed; const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
    let x = 0, out = "";
    while (x < w) {
      const bw = 26 + rnd() * 60, bh = 70 + rnd() * (h * 0.72);
      const tone = ["#0a2a54", "#0d366b", "#12437f", "#184f95"][Math.floor(rnd() * 4)];
      out += `<rect x="${x.toFixed(0)}" y="${(h - bh).toFixed(0)}" width="${bw.toFixed(0)}" height="${bh.toFixed(0)}" fill="${tone}"/>`;
      for (let wy = h - bh + 10; wy < h - 10; wy += 14)
        for (let wx = x + 6; wx < x + bw - 6; wx += 10)
          if (rnd() < 0.35) out += `<rect x="${wx.toFixed(0)}" y="${wy.toFixed(0)}" width="4" height="6" fill="#ffcf5a" opacity="${(0.25 + rnd() * 0.6).toFixed(2)}"/>`;
      x += bw + 3 + rnd() * 10;
    }
    svg.innerHTML = out;
  }

  /* ---------- quotes ---------- */
  function quotes(list) {
    if (!list?.length) return;
    const fig = $("#quote"), dots = $("#qdots"); let i = 0, timer;
    dots.innerHTML = list.map((_, k) => `<button role="tab" aria-label="Quote ${k + 1}"></button>`).join("");
    const show = (k) => {
      i = (k + list.length) % list.length; fig.style.opacity = 0;
      setTimeout(() => {
        $("blockquote", fig).textContent = `“${list[i].text}”`;
        $("figcaption", fig).textContent = `— ${list[i].author}`;
        fig.style.opacity = 1;
      }, 250);
      [...dots.children].forEach((b, n) => b.setAttribute("aria-selected", n === i));
    };
    [...dots.children].forEach((b, n) => b.addEventListener("click", () => { show(n); restart(); }));
    const restart = () => { clearInterval(timer); timer = setInterval(() => show(i + 1), 7000); };
    show(0); restart();
  }

  /* ---------- KPIs ---------- */
  function kpis(list) {
    $("#kpis").innerHTML = list.map((k) => `
      <div class="kpi reveal"><div class="v">${esc(k.display)}</div><div class="l">${esc(k.label)}</div>
        <div class="c">${esc(k.change)}</div><div class="s">${esc(k.period)} · <a href="${esc(k.url)}" target="_blank" rel="noopener">${esc(k.source)}</a></div></div>`).join("");
  }

  /* ---------- news ---------- */
  function news(n) {
    const ins = n.insights || [];
    $("#insights").innerHTML = (ins.length ? ins.slice(0, 2) : []).map((c) => `
      <article class="insight reveal"><span class="tag">${esc(c.zone)} · ${esc(c.area)}</span>
        <h3>${esc(c.title)}</h3><p class="meta">${esc(c.publisher)} · ${esc(c.published_at || "")}</p>
        <a href="${esc(c.url)}" target="_blank" rel="noopener">Read the source →</a></article>`).join("") ||
      `<article class="insight reveal"><span class="tag">Today</span><h3>The latest Bengaluru property headlines, refreshed every morning at 6:00 IST.</h3></article>`;
    const zones = ["All", ...new Set((n.headlines || []).map((h) => h.zone))];
    let zone = "All", shown = 10;
    const filter = $("#zone-filter");
    filter.innerHTML = zones.map((z) => `<button class="chip" aria-pressed="${z === "All"}" data-z="${esc(z)}">${esc(z)}</button>`).join("");
    const render = () => {
      const rows = (n.headlines || []).filter((h) => zone === "All" || h.zone === zone);
      $("#headlines").innerHTML = rows.slice(0, shown).map((h) => `
        <a class="news-card" href="${esc(h.url)}" target="_blank" rel="noopener">
          <h4>${esc(h.title)}</h4>
          <div class="meta"><span class="zone ${esc(h.zone)}">${esc(h.zone)}</span><span>${esc((h.publishers || [])[0] || "")}</span><span>${esc(relTime(h.published_at))}</span></div>
        </a>`).join("") + (rows.length > shown ? `<button class="btn btn-outline btn-sm more" id="more">Show more headlines</button>` : "");
      $("#more")?.addEventListener("click", () => { shown += 10; render(); });
    };
    filter.addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      zone = b.dataset.z; shown = 10;
      [...filter.children].forEach((c) => c.setAttribute("aria-pressed", c === b)); render();
    });
    render();
  }

  /* ---------- charts ---------- */
  function chartDefaults() {
    if (!window.Chart) return false;
    Chart.defaults.font.family = "Inter, sans-serif";
    Chart.defaults.color = dark() ? "#b4bcc8" : "#4a5462";
    Chart.defaults.borderColor = dark() ? "#263241" : "#e4e7ec";
    return true;
  }
  const unitFmt = (u, v) => (u.includes("₹") ? `₹${fmt.format(v)}` : u.includes("%") ? `${v}%` : fmt.format(v));

  function growthCharts(series) {
    const box = $("#charts");
    box.innerHTML = series.map((s, i) => {
      const a = s.points[0].value, b = s.points[s.points.length - 1].value;
      const pct = a ? Math.round(((b - a) / a) * 100) : null;
      return `<div class="card reveal"><div class="card-head"><h3>${esc(s.title)}</h3>${pct !== null ? `<span class="growth">${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct)}% over the period</span>` : ""}</div>
        <p class="card-note">${esc(s.note)}</p><div class="chart-box"><canvas id="c${i}" aria-label="${esc(s.title)}"></canvas></div>
        <p class="src">Source: ${s.points.map((p) => `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.source)}</a>`).filter((v, k, arr) => arr.indexOf(v) === k).join(", ")}</p></div>`;
    }).join("");
    if (!chartDefaults()) { box.insertAdjacentHTML("beforeend", "<p>Charts need an internet connection (Chart.js CDN).</p>"); return; }
    series.forEach((s, i) => {
      const ctx = $(`#c${i}`).getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, 0, 220); grad.addColorStop(0, "rgba(42,120,214,.28)"); grad.addColorStop(1, "rgba(42,120,214,0)");
      const bar = s.chart === "bar";
      new Chart(ctx, {
        type: bar ? "bar" : "line",
        data: { labels: s.points.map((p) => p.label), datasets: [{ data: s.points.map((p) => p.value), borderColor: "#2a78d6", backgroundColor: bar ? "#2a78d6" : grad,
          fill: !bar, tension: 0.35, borderWidth: 2.5, pointRadius: 5, pointHoverRadius: 7, pointBackgroundColor: "#fff", pointBorderWidth: 2.5,
          borderRadius: 6, maxBarThickness: 56 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (c) => `${unitFmt(s.unit, c.parsed.y)} · ${s.points[c.dataIndex].source}` } } },
          scales: { y: { beginAtZero: bar, grid: { drawTicks: false }, ticks: { callback: (v) => unitFmt(s.unit, v) } }, x: { grid: { display: false } } } },
      });
    });
  }

  function areaChart(rows) {
    if (!rows.length || !chartDefaults()) return;
    const sorted = [...rows].sort((a, b) => b.high - a.high);
    $("#area-legend").innerHTML = Object.entries({ East: "east", North: "north", South: "south", West: "west", Outer: "outer" })
      .filter(([, z]) => rows.some((r) => r.zone === z)).map(([n, z]) => `<span><i style="background:${ZONE_COLOR[z]}"></i>${n}</span>`).join("");
    new Chart($("#area-chart"), {
      type: "bar",
      data: { labels: sorted.map((r) => r.area), datasets: [{ data: sorted.map((r) => (r.low === r.high ? [r.low - 120, r.high + 120] : [r.low, r.high])),
        backgroundColor: sorted.map((r) => ZONE_COLOR[r.zone] || "#8a8984"), borderRadius: 6, borderSkipped: false, barThickness: 16 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (c) => { const r = sorted[c.dataIndex]; return `₹${fmt.format(r.low)}${r.high > r.low ? "–" + fmt.format(r.high) : ""}/sq ft · ${r.basis} · ${r.source}`; } } } },
        scales: { x: { min: Math.floor((Math.min(...rows.map((r) => r.low)) * 0.85) / 500) * 500,
          ticks: { callback: (v) => `₹${fmt.format(v)}` } }, y: { grid: { display: false } } } },
    });
  }

  /* ---------- builders ---------- */
  function builders(list, tracked) {
    const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    const count = Object.fromEntries((tracked || []).map((t) => [t.developer.split(" ")[0].toLowerCase(), t.tracked_projects]));
    $("#builder-cards").innerHTML = list.map((b) => {
      const n = count[b.name.split(" ")[0].toLowerCase()];
      return `<article class="builder reveal"><div class="bhead"><div class="mono">${esc(initials(b.name))}</div>
        <div><h3>${esc(b.name)}</h3>${n ? `<span class="bml">${n} project${n > 1 ? "s" : ""} tracked</span>` : ""}</div></div>
        <div><div class="bm">${esc(b.metric_display)}</div><div class="bml">${esc(b.metric_label)}</div></div>
        <p>${esc(b.headline)}</p>
        ${b.projects.length ? `<div class="tags">${b.projects.slice(0, 4).map((p) => `<span>${esc(p)}</span>`).join("")}</div>` : ""}
        <p class="src">Source: <a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.sources.join(", "))}</a></p></article>`;
    }).join("");
  }

  /* ---------- plans, towns, zones ---------- */
  function plans(rows) {
    $("#plans-list").innerHTML = rows.map((r) => `
      <article class="plan reveal"><div class="pi"><svg viewBox="0 0 24 24">${ICONS[r.category] || ICONS.policy}</svg></div>
        <div><h3>${esc(r.project)}</h3><p>${esc(r.status)}</p><span class="when">${esc(r.timeline)}</span><span class="where">${esc(r.areas)}</span></div></article>`).join("");
  }
  function towns(rows, zones) {
    $("#towns-list").innerHTML = rows.map((t, i) => `
      <article class="town reveal"><div class="tsky"><svg id="ts${i}" viewBox="0 0 400 60" preserveAspectRatio="none"></svg></div>
        <div class="tb"><h3>${esc(t.name)}</h3><p>${esc(t.why)}</p>${t.price_text ? `<p class="tp">${esc(t.price_text)}</p>` : ""}<p class="tw"><b>Watch:</b> ${esc(t.risks)}</p></div></article>`).join("");
    rows.forEach((_, i) => skyline($(`#ts${i}`), 11 + i * 7, 400, 60));
    $("#zones").innerHTML = zones.map((z) => `
      <article class="zcard ${esc(z.zone)} reveal"><p class="kicker">${esc(z.zone)} Bengaluru</p><h3>${esc(z.title)}</h3><p>${esc(z.standfirst)}</p>
        <ul>${z.markets.slice(0, 5).map((m) => `<li><b>${esc(m.name)}</b><span>${esc(m.price_text || "")}</span></li>`).join("")}</ul></article>`).join("");
  }

  /* ---------- magazine + downloads ---------- */
  function magazine(s) {
    const m = s.magazine || {}, d = s.downloads || {};
    if (m.cover?.headline) {
      $("#hero-headline").textContent = m.cover.headline;
      $("#hero-sub").textContent = m.cover.subhead || $("#hero-sub").textContent;
    }
    $("#edition-label").textContent = m.label || "Today";
    $("#cover-badge").textContent = m.label ? `${m.label} issue` : "Latest issue";
    $("#mag-title").textContent = d.magazine?.title || "Bengaluru Property Review";
    $("#mag-note").innerHTML = (m.editor_note || []).slice(0, 2).map((p) => `<p>${esc(p.text)}</p>`).join("");
    $("#downloads").innerHTML = [d.magazine && { ...d.magazine, label: "Monthly magazine" }, d.daily && { ...d.daily, label: "Daily brief" }]
      .filter(Boolean).map((x) => `<div class="dl"><b>${esc(x.label)}</b><span>${esc(x.title)} · ${x.pages} pages · ${x.size_mb} MB</span>
        <a class="btn btn-navy btn-sm" href="/download/${esc(x.file)}">Download PDF</a></div>`).join("");
    if (!d.magazine) $("#cover-img").closest("a").style.display = "none";
  }

  function status(s) {
    const t = s.generated_at ? new Date(s.generated_at) : null;
    $("#updated").textContent = t ? `Updated ${t.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" })} IST · next refresh 6:00 IST` : "";
    fetch("/api/status").then((r) => r.json()).then((st) => {
      const j = st.jobs?.[0];
      $("#status-line").textContent = `${st.subscribers} subscriber${st.subscribers === 1 ? "" : "s"} · last batch ${j ? `${j.status} (${relTime(j.finished_at || j.started_at)})` : "—"}`;
    }).catch(() => {});
  }

  /* ---------- subscribe ---------- */
  function subscribe() {
    const f = $("#sub-form"), msg = $("#sub-msg");
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      msg.className = "form-msg"; msg.textContent = "Subscribing…";
      try {
        const r = await fetch("/api/subscribe", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: fd.get("email"), name: fd.get("name") || "", interests: fd.getAll("interests") }) });
        const j = await r.json();
        msg.textContent = j.message || (j.detail ? "Please check your details." : "Done.");
        msg.className = "form-msg " + (r.ok && j.ok ? "ok" : "err");
        if (r.ok && j.ok) f.reset();
      } catch { msg.textContent = "Could not reach the server. Please try again."; msg.className = "form-msg err"; }
    });
  }

  function reveal() {
    const io = new IntersectionObserver((es) => es.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } }), { rootMargin: "0px 0px -40px" });
    document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
  }

  function menu() {
    const b = $("#menu-btn"), nav = $(".nav");
    b.addEventListener("click", () => { const o = nav.classList.toggle("open"); b.setAttribute("aria-expanded", o); });
    nav.addEventListener("click", () => { nav.classList.remove("open"); b.setAttribute("aria-expanded", false); });
  }

  async function main() {
    skyline($("#hero-skyline"));
    menu(); subscribe();
    let s;
    try { s = await (await fetch("/api/site")).json(); }
    catch { $("#updated").textContent = "Could not load data from the server."; return; }
    if (s.detail) { $("#updated").textContent = s.detail; return; }
    quotes(s.quotes); kpis(s.metrics.kpis); news(s.news); growthCharts(s.metrics.series); areaChart(s.metrics.area_prices);
    builders(s.metrics.builders, s.metrics.tracked_developers); plans(s.plans); towns(s.growth_towns, s.zones); magazine(s); status(s);
    reveal();
  }
  main();
})();
