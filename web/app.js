/* Reel tracker dashboard. No framework, no build step. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  page: 0,
  perPage: 50,
  ideas: [],
  categories: {},
};

const fmt = {
  n: (v) => (v == null ? "—" : Number(v).toLocaleString()),
  compact: (v) => {
    const n = Number(v || 0);
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k";
    return String(n);
  },
  pct: (v) => (v == null ? "—" : (Number(v) * 100).toFixed(2) + "%"),
  x: (v) => (v == null ? "—" : Number(v).toFixed(1) + "×"),
  secs: (v) => (v == null ? "—" : Math.round(Number(v)) + "s"),
  date: (v) => (v ? String(v).slice(0, 10) : "—"),
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json();
  if (body && body.error) throw new Error(body.error);
  return body;
}

const post = (path, payload = {}) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

/* ----------------------------------------------------------------- tabs */

$("#tabs").addEventListener("click", (e) => {
  const button = e.target.closest("button[data-tab]");
  if (!button) return;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b === button));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${button.dataset.tab}`));
  const loaders = { signals: loadSignals, ideas: loadIdeas, plan: loadPlaybook, data: loadDataTab };
  loaders[button.dataset.tab]?.();
});

/* ---------------------------------------------------------------- header */

async function loadSummary() {
  const s = await api("/api/summary");
  if (!s.reels) {
    $("#stats").innerHTML = `<span>no data loaded</span>`;
    return s;
  }
  $("#stats").innerHTML = `
    <div><b>${fmt.n(s.reels)}</b><span>ranked reels</span></div>
    <div><b>${fmt.n(s.accounts)}</b><span>accounts</span></div>
    <div><b>${fmt.compact(s.median_views)}</b><span>median views</span></div>
    <div><b>${fmt.compact(s.p90_views)}</b><span>p90 views</span></div>
    <div><b>${fmt.x(s.median_reach_multiple)}</b><span>median ×reach</span></div>`;

  const banner = $("#sample-banner");
  if (s.sample_rows > 0) {
    banner.hidden = false;
    $("#sample-detail").textContent = `${fmt.n(s.sample_rows)} of ${fmt.n(s.reels)} ranked rows are synthetic.`;
  } else {
    banner.hidden = true;
  }
  return s;
}

/* ----------------------------------------------------------- leaderboard */

function boardParams() {
  const p = new URLSearchParams();
  p.set("limit", state.perPage);
  p.set("offset", state.page * state.perPage);
  const q = $("#q").value.trim();
  if (q) p.set("q", q);
  if ($("#tag").value) p.set("tag", $("#tag").value);
  if ($("#maxfollowers").value) p.set("max_followers", $("#maxfollowers").value);
  if ($("#hidesample").checked) p.set("sample", "0");
  const sort = $("#sort").value;
  p.set("sort", sort);
  p.set("dir", sort === "rank" ? "asc" : "desc");
  return p;
}

async function loadBoard() {
  const data = await api("/api/leaderboard?" + boardParams());
  const body = $("#board tbody");

  if (!data.rows.length) {
    body.innerHTML = `<tr><td colspan="9" class="empty">
      Nothing here yet. Open the <b>Data</b> tab and load the sample set,
      or run <code>python -m app seed</code>.</td></tr>`;
    $("#board-count").textContent = "";
    $("#page-label").textContent = "";
    return;
  }

  body.innerHTML = data.rows
    .map((r) => {
      const chips = (r.tags || [])
        .filter(([, kind]) => ["format", "hook", "subject", "length"].includes(kind))
        .slice(0, 4)
        .map(([t]) => `<span class="tag-chip">${esc(t)}</span>`)
        .join("");
      return `<tr class="clickable" data-id="${esc(r.reel_id)}">
        <td class="rank">${r.rank}</td>
        <td class="score">${r.score.toFixed(1)}</td>
        <td class="num">${fmt.compact(r.views)}</td>
        <td class="num">${fmt.x(r.reach_multiple)}</td>
        <td class="num">${fmt.pct(r.engagement_rate)}</td>
        <td class="num">${fmt.pct(r.intent_rate)}</td>
        <td class="num">${fmt.secs(r.duration_s)}</td>
        <td class="handle">@${esc(r.handle || "?")}<br><span class="muted">${fmt.compact(r.followers)} foll.</span>${
          r.is_sample ? '<span class="sampleflag">sample</span>' : ""
        }</td>
        <td class="caption">${esc((r.caption || "").slice(0, 130))}<div>${chips}</div></td>
      </tr>`;
    })
    .join("");

  $("#board-count").textContent = `${fmt.n(data.total)} matching`;
  const from = data.offset + 1;
  const to = Math.min(data.offset + data.limit, data.total);
  $("#page-label").textContent = `${from}–${to} of ${fmt.n(data.total)}`;
  $("#prev").disabled = state.page === 0;
  $("#next").disabled = to >= data.total;
}

$("#board").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-id]");
  if (row) openDrawer(row.dataset.id);
});

["q", "tag", "maxfollowers", "sort", "hidesample"].forEach((id) => {
  const el = $("#" + id);
  const event = el.tagName === "INPUT" && el.type === "search" ? "input" : "change";
  let timer;
  el.addEventListener(event, () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.page = 0;
      loadBoard();
    }, event === "input" ? 250 : 0);
  });
});

$("#prev").addEventListener("click", () => {
  state.page = Math.max(0, state.page - 1);
  loadBoard();
});
$("#next").addEventListener("click", () => {
  state.page += 1;
  loadBoard();
});

/* --------------------------------------------------------------- drawer */

async function openDrawer(id) {
  const r = await api("/api/reel?id=" + encodeURIComponent(id));
  const tags = (r.tags || []).map(([t]) => `<span class="tag-chip">${esc(t)}</span>`).join("");
  $("#drawer-body").innerHTML = `
    <h2 style="margin:0 0 4px">@${esc(r.handle || "unknown")}</h2>
    <div class="muted">${fmt.n(r.followers)} followers · posted ${fmt.date(r.posted_at)}${
      r.is_sample ? ' · <span class="sampleflag">sample row</span>' : ""
    }</div>
    <dl>
      <dt>rank</dt><dd>${r.rank ?? "unranked"}</dd>
      <dt>score</dt><dd>${r.score != null ? r.score.toFixed(1) : "—"} (raw ${r.raw_score != null ? r.raw_score.toFixed(1) : "—"})</dd>
      <dt>views</dt><dd>${fmt.n(r.views)}</dd>
      <dt>×reach</dt><dd>${fmt.x(r.reach_multiple)}</dd>
      <dt>likes</dt><dd>${fmt.n(r.likes)}</dd>
      <dt>comments</dt><dd>${fmt.n(r.comments)}</dd>
      <dt>saves</dt><dd>${fmt.n(r.saves)}</dd>
      <dt>shares</dt><dd>${fmt.n(r.shares)}</dd>
      <dt>engagement</dt><dd>${fmt.pct(r.engagement_rate)}</dd>
      <dt>intent</dt><dd>${fmt.pct(r.intent_rate)}</dd>
      <dt>views / day</dt><dd>${fmt.n(Math.round(r.velocity || 0))}</dd>
      <dt>length</dt><dd>${fmt.secs(r.duration_s)}</dd>
      <dt>audio</dt><dd>${esc(r.audio_name || "—")}</dd>
      <dt>percentiles</dt><dd>reach ${fmt.pct(r.pct_reach)} · viral ${fmt.pct(r.pct_virality)}<br>eng ${fmt.pct(
        r.pct_engagement
      )} · intent ${fmt.pct(r.pct_intent)}</dd>
    </dl>
    <p style="white-space:pre-wrap">${esc(r.caption || "")}</p>
    <div>${tags}</div>
    ${
      r.url && !r.url.includes("example.invalid")
        ? `<p><a href="${esc(r.url)}" target="_blank" rel="noopener">open on Instagram →</a></p>`
        : ""
    }
    ${
      (r.history || []).length > 1
        ? `<h3 style="font-size:13px;margin-top:20px">observations</h3><pre class="log">${r.history
            .map((h) => `${fmt.date(h.collected_at)}  ${String(fmt.n(h.views)).padStart(10)} views`)
            .join("\n")}</pre>`
        : ""
    }`;
  $("#drawer").hidden = false;
}

$("#drawer-close").addEventListener("click", () => ($("#drawer").hidden = true));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("#drawer").hidden = true;
});

/* -------------------------------------------------------------- signals */

function bars(container, rows, { label, value, format, n, center }) {
  if (!rows.length) {
    container.innerHTML = `<div class="empty">Not enough data.</div>`;
    return;
  }
  const values = rows.map(value);
  const max = Math.max(...values.map(Math.abs), center ? 1.4 : 0.0001);
  container.innerHTML = rows
    .map((r) => {
      const v = value(r);
      let style, cls;
      if (center) {
        // Diverging bar around lift = 1.00, drawn from the midpoint.
        const half = (Math.min(Math.abs(v - 1) / (max - 1 || 1), 1) * 50).toFixed(1);
        cls = v >= 1 ? "up" : "down";
        style = v >= 1 ? `left:50%;width:${half}%` : `right:50%;width:${half}%`;
      } else {
        cls = "up";
        style = `left:0;width:${((v / max) * 100).toFixed(1)}%`;
      }
      return `<div class="bar-row">
        <div class="bar-label" title="${esc(label(r))}">${esc(label(r))}${
        n ? ` <span class="bar-n">n=${n(r)}</span>` : ""
      }</div>
        <div class="bar-track">${center ? '<div class="bar-mid" style="left:50%"></div>' : ""}<div class="bar-fill ${cls}" style="${style}"></div></div>
        <div class="bar-value">${format(v)}</div>
      </div>`;
    })
    .join("");
}

async function loadSignals() {
  const s = await api("/api/signals");
  const tags = s.tags || [];

  const notable = [...tags.slice(0, 12), ...tags.slice(-6)].filter(
    (t, i, arr) => arr.findIndex((x) => x.tag === t.tag) === i
  );
  bars($("#taglift"), notable, {
    label: (r) => r.tag,
    value: (r) => r.lift,
    n: (r) => r.count,
    format: (v) => v.toFixed(2) + "×",
    center: true,
  });

  bars($("#durations"), s.duration || [], {
    label: (r) => r.bucket.replace("len:", ""),
    value: (r) => r.median_score,
    n: (r) => r.count,
    format: (v) => v.toFixed(1),
  });

  bars($("#timing"), (s.timing?.by_weekday || []), {
    label: (r) => r.day,
    value: (r) => r.median_score,
    n: (r) => r.count,
    format: (v) => v.toFixed(1),
  });

  $("#breakouts tbody").innerHTML =
    (s.breakouts || [])
      .slice(0, 25)
      .map(
        (b) => `<tr>
          <td class="handle">@${esc(b.handle)}</td>
          <td class="num">${fmt.compact(b.followers)}</td>
          <td class="num">${b.reels}</td>
          <td class="num">${fmt.x(b.best_reach_multiple)}</td>
          <td class="num">${fmt.compact(b.best_views)}</td>
          <td>${b.top_tags.map((t) => `<span class="tag-chip">${esc(t)}</span>`).join("")}</td>
        </tr>`
      )
      .join("") || `<tr><td colspan="6" class="empty">No small accounts in the corpus yet.</td></tr>`;

  $("#audio tbody").innerHTML =
    (s.audio || [])
      .map(
        (a) => `<tr>
          <td>${esc(a.audio)}</td>
          <td class="num">${a.uses}</td>
          <td class="num">${a.median_score.toFixed(1)}</td>
          <td class="num">${fmt.compact(a.median_views)}</td>
        </tr>`
      )
      .join("") || `<tr><td colspan="4" class="empty">No repeated audio yet.</td></tr>`;
}

/* ---------------------------------------------------------------- ideas */

async function loadIdeas() {
  if (!state.ideas.length) {
    const data = await api("/api/ideas");
    state.ideas = data.ideas;
    state.categories = data.categories;
    $("#idea-cat").innerHTML =
      `<option value="">all categories</option>` +
      Object.entries(data.categories)
        .map(([k, v]) => `<option value="${esc(k)}">${esc(v.split("—")[0].trim())}</option>`)
        .join("");
  }
  renderIdeas();
}

function renderIdeas() {
  const cat = $("#idea-cat").value;
  const goal = $("#idea-goal").value;
  const effort = $("#idea-effort").value;
  const list = state.ideas.filter(
    (i) => (!cat || i.category === cat) && (!goal || i.goal === goal) && (!effort || i.effort === effort)
  );

  $("#idea-count").textContent = `${list.length} ideas`;
  $("#ideas").innerHTML = list
    .map(
      (i) => `<article class="idea">
        <div class="idea-top">
          <h3>${esc(i.title)}</h3>
          <span class="pill goal-${esc(i.goal)}">${esc(i.goal)}</span>
        </div>
        ${i.hook ? `<div class="hook">${esc(i.hook)}</div>` : `<div class="hook">no hook text — open on the visual</div>`}
        <ol>${i.shots.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        <div class="why">${esc(i.why)}</div>
        ${i.cta ? `<div class="cta">CTA: ${esc(i.cta)}</div>` : ""}
        <div class="pills">
          <span class="pill">${esc(i.length_s)}s</span>
          <span class="pill">${esc(i.effort)} effort</span>
          <span class="pill">${esc(state.categories[i.category] || i.category).split("—")[0].trim()}</span>
          <span class="pill">${esc(i.id)}</span>
        </div>
      </article>`
    )
    .join("");
}

["idea-cat", "idea-goal", "idea-effort"].forEach((id) =>
  $("#" + id).addEventListener("change", renderIdeas)
);

/* ----------------------------------------------------------------- plan */

/* Deliberately small Markdown subset — headings, lists, tables, bold, code,
   blockquotes, rules. Enough for the playbook, and nothing that needs a
   dependency. Input is our own file, but everything is escaped anyway. */
function markdown(src) {
  const lines = esc(src).split("\n");
  const out = [];
  let list = null; // 'ul' | 'ol' | null
  let table = false;
  let para = []; // buffered wrapped lines of the current paragraph
  let li = null; // buffered wrapped lines of the current list item
  let quote = null;

  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Source is hard-wrapped, so a run of plain lines is one paragraph and an
  // unprefixed line after a bullet continues that bullet.
  const flushPara = () => {
    if (para.length) out.push(`<p>${inline(para.join(" "))}</p>`);
    para = [];
  };
  const flushLi = () => {
    if (li) out.push(`<li>${inline(li.join(" "))}</li>`);
    li = null;
  };
  const flushQuote = () => {
    if (quote) out.push(`<blockquote>${inline(quote.join(" "))}</blockquote>`);
    quote = null;
  };
  const closeList = () => {
    flushLi();
    if (list) out.push(`</${list}>`);
    list = null;
  };
  const closeTable = () => {
    if (table) out.push("</tbody></table></div>");
    table = false;
  };
  const closeAll = () => {
    flushPara();
    flushQuote();
    closeList();
    closeTable();
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (/^\s*\|/.test(line)) {
      if (/^[\s|:-]+$/.test(line)) continue; // header separator
      const cells = line.trim().split("|").slice(1, -1).map((c) => c.trim());
      if (!table) {
        flushPara();
        flushQuote();
        closeList();
        out.push(
          '<div class="tablewrap"><table><thead><tr>' +
            cells.map((c) => `<th>${inline(c)}</th>`).join("") +
            "</tr></thead><tbody>"
        );
        table = true;
      } else {
        out.push("<tr>" + cells.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>");
      }
      continue;
    }
    closeTable();

    if (!line.trim()) {
      flushPara();
      flushQuote();
      flushLi(); // blank line ends the item but leaves the list open
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeAll();
      out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      closeAll();
      out.push("<hr>");
      continue;
    }
    if (/^&gt;\s?/.test(line)) {
      flushPara();
      closeList();
      (quote ||= []).push(line.replace(/^&gt;\s?/, ""));
      continue;
    }
    flushQuote();

    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (ordered || bullet) {
      flushPara();
      const want = ordered ? "ol" : "ul";
      if (list !== want) {
        closeList();
        out.push(`<${want}>`);
        list = want;
      } else {
        flushLi();
      }
      li = [(ordered || bullet)[1]];
      continue;
    }

    if (li) {
      li.push(line.trim()); // wrapped continuation of the current bullet
    } else {
      closeList();
      para.push(line.trim());
    }
  }
  closeAll();
  return out.join("\n");
}

let playbookLoaded = false;
async function loadPlaybook() {
  if (playbookLoaded) return;
  const { markdown: md } = await api("/api/playbook");
  $("#playbook").innerHTML = markdown(md);
  playbookLoaded = true;
}

/* ------------------------------------------------------------------ data */

function log(message) {
  const el = $("#data-log");
  el.textContent = `${new Date().toLocaleTimeString()}  ${message}\n` + el.textContent;
}

async function run(label, fn) {
  log(`${label}…`);
  try {
    const result = await fn();
    log(`${label}: ${JSON.stringify(result)}`);
    await refreshAll();
  } catch (err) {
    log(`${label} FAILED: ${err.message}`);
  }
}

$("#do-seed").addEventListener("click", () => run("seed", () => post("/api/seed")));
$("#do-refresh").addEventListener("click", () => run("refresh", () => post("/api/refresh")));
$("#do-purge").addEventListener("click", () => {
  if (confirm("Delete every synthetic sample row? Real data is untouched.")) {
    run("purge sample", () => post("/api/purge-sample"));
  }
});
$("#do-import").addEventListener("click", () =>
  run("import", () => post("/api/import", { path: $("#import-path").value.trim() }))
);
$("#do-collect").addEventListener("click", () =>
  run("collect", () =>
    post("/api/collect", {
      kind: $("#collect-kind").value,
      targets: $("#collect-targets").value.split(",").map((s) => s.trim()).filter(Boolean),
    })
  )
);
$("#do-watch").addEventListener("click", async () => {
  await run("watch", () =>
    post("/api/watchlist/add", {
      kind: $("#watch-kind").value,
      values: $("#watch-value").value.split(",").map((s) => s.trim()).filter(Boolean),
    })
  );
  $("#watch-value").value = "";
  loadDataTab();
});

async function loadDataTab() {
  const [{ watchlist }, summary] = await Promise.all([api("/api/watchlist"), api("/api/summary")]);
  $("#watchlist").innerHTML = watchlist.length
    ? `<div class="pills">${watchlist
        .map((w) => `<span class="pill">${w.kind === "hashtag" ? "#" : "@"}${esc(w.value)}</span>`)
        .join("")}</div>`
    : `<div class="muted">empty — nothing scheduled for collection</div>`;

  if (summary.weights) {
    $("#weights").innerHTML = Object.entries(summary.weights)
      .map(([k, v]) => `<div>${esc(k)}<br><b>${(v * 100).toFixed(0)}%</b></div>`)
      .join("");
  }
}

/* ------------------------------------------------------------------ boot */

async function refreshAll() {
  await loadSummary();
  await loadBoard();
  playbookLoaded = false;
  if ($("#tab-signals").classList.contains("active")) loadSignals();
}

async function populateTags() {
  try {
    const s = await api("/api/signals");
    const select = $("#tag");
    const groups = {};
    for (const t of s.tags || []) (groups[t.kind] ||= []).push(t);
    select.innerHTML =
      `<option value="">all tags</option>` +
      Object.entries(groups)
        .map(
          ([kind, items]) =>
            `<optgroup label="${esc(kind)}">` +
            items
              .sort((a, b) => b.count - a.count)
              .map((t) => `<option value="${esc(t.tag)}">${esc(t.tag)} (${t.count})</option>`)
              .join("") +
            `</optgroup>`
        )
        .join("");
  } catch {
    /* no data yet — the select stays as "all tags" */
  }
}

(async function boot() {
  await loadSummary();
  await loadBoard();
  populateTags();
})();
