(() => {
  "use strict";
  const BASE = "";

  const cookieBanner = document.getElementById("cookie-banner");
  const cookieAccept = document.getElementById("cookie-accept");
  const cookieConsentKey = "inkfall-cookie-consent";

  if (cookieBanner && cookieAccept) {
    const accepted = localStorage.getItem(cookieConsentKey) === "1";
    if (!accepted) {
      cookieBanner.classList.add("show");
    }

    cookieAccept.addEventListener("click", () => {
      localStorage.setItem(cookieConsentKey, "1");
      cookieBanner.classList.remove("show");
    });
  }

  let state = {
    lang: "en",
    q: "",
    unique: "cards",
    sort: "name",
    sortDir: "asc",
    page: 1,
  };

  const $ = id => document.getElementById(id);

  const searchInput  = $("search-input");
  const sortSelect   = $("sort-select");
  const sortDirBtn   = $("sort-dir-btn");
  const refreshBtn   = $("refresh-btn");
  const cardGrid     = $("card-grid");
  const pagination   = $("pagination");
  const resultsCount = $("results-count");
  const resultsQuery = $("results-query");
  const loading      = $("loading");
  const errorMsg     = $("error-msg");
  const warnMsg      = $("warn-msg");

  // ── Card size slider ───────────────────────────────────────────────────
  const sizeSlider = $("size-slider");
  const grid = $("card-grid");
  const savedSize = localStorage.getItem("cardSize");
  if (sizeSlider) {
    if (savedSize) sizeSlider.value = savedSize;
    const applySize = v => document.documentElement.style.setProperty("--card-min-width", v + "px");
    applySize(sizeSlider.value);
    sizeSlider.addEventListener("input", () => {
      applySize(sizeSlider.value);
      localStorage.setItem("cardSize", sizeSlider.value);
    });
  }

  // ── Language toggle ────────────────────────────────────────────────────
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (btn.dataset.lang === state.lang) return;
      state.lang = btn.dataset.lang;
      state.page = 1;
      document.querySelectorAll(".lang-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.lang === state.lang)
      );
      fetchCards();
    });
  });

  // ── Search form (GET navigation for non-JS fallback) ──────────────────
  // The form has method=get but we intercept for AJAX
  document.getElementById("search-form").addEventListener("submit", e => {
    e.preventDefault();
    state.q = searchInput.value.trim();
    state.page = 1;
    // deactivate color pills
    document.querySelectorAll(".color-pill").forEach(b => b.classList.remove("active"));
    fetchCards();
  });

  // ── Color pills ────────────────────────────────────────────────────────
  document.querySelectorAll(".color-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      const already = btn.classList.contains("active");
      document.querySelectorAll(".color-pill").forEach(b => b.classList.remove("active"));
      if (already) {
        state.q = "";
        if (searchInput) searchInput.value = "";
      } else {
        state.q = btn.dataset.query;
        if (searchInput) searchInput.value = state.q;
        btn.classList.add("active");
      }
      state.page = 1;
      fetchCards();
    });
  });

  // ── Cards / All Prints toggle ──────────────────────────────────────────
  document.querySelectorAll(".unique-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (btn.dataset.unique === state.unique) return;
      state.unique = btn.dataset.unique;
      state.page = 1;
      document.querySelectorAll(".unique-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.unique === state.unique)
      );
      fetchCards();
    });
  });

  // ── Sort ───────────────────────────────────────────────────────────────
  sortSelect.addEventListener("change", () => { state.sort = sortSelect.value; state.page = 1; fetchCards(); });
  sortDirBtn.addEventListener("click", () => {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    sortDirBtn.textContent = state.sortDir === "asc" ? "↑" : "↓";
    state.page = 1; fetchCards();
  });

  // ── Refresh ────────────────────────────────────────────────────────────
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.classList.add("busy");
    try {
      const res = await fetch(`${BASE}/api/refresh?lang=${state.lang}`);
      const d = await res.json();
      if (d.ok) fetchCards();
    } finally {
      setTimeout(() => refreshBtn.classList.remove("busy"), 2000);
    }
  });

  // ── URL state sync ──────────────────────────────────────────────────────
  function syncUrl(push) {
    const p = new URLSearchParams();
    if (state.q)              p.set("q",      state.q);
    if (state.page > 1)       p.set("page",   state.page);
    if (state.lang !== "en")  p.set("lang",   state.lang);
    if (state.unique !== "cards") p.set("unique", state.unique);
    if (state.sort !== "name")    p.set("sort",   state.sort);
    if (state.sortDir !== "asc")  p.set("dir",    state.sortDir);
    const url = p.toString() ? `?${p}` : location.pathname;
    if (push) history.pushState(null, "", url);
    else      history.replaceState(null, "", url);
  }

  function applyUrlState() {
    const p = new URLSearchParams(location.search);
    state.q       = p.get("q")      || "";
    state.page    = parseInt(p.get("page")) || 1;
    state.lang    = p.get("lang")   || "en";
    state.unique  = p.get("unique") || "cards";
    state.sort    = p.get("sort")   || "name";
    state.sortDir = p.get("dir")    || "asc";
    if (searchInput) searchInput.value = state.q;
    if (sortSelect)  sortSelect.value  = state.sort;
    if (sortDirBtn)  sortDirBtn.textContent = state.sortDir === "asc" ? "↑" : "↓";
    document.querySelectorAll(".lang-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.lang === state.lang)
    );
    document.querySelectorAll(".unique-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.unique === state.unique)
    );
    document.querySelectorAll(".color-pill").forEach(b =>
      b.classList.toggle("active", state.q !== "" && b.dataset.query === state.q)
    );
  }

  window.addEventListener("popstate", () => {
    applyUrlState();
    fetchCards(false);
  });

  // ── Fetch & render ─────────────────────────────────────────────────────
  async function fetchCards(push = true) {
    syncUrl(push);
    loading.classList.remove("hidden");
    cardGrid.innerHTML = "";
    pagination.innerHTML = "";
    errorMsg.classList.add("hidden");
    if (warnMsg) warnMsg.classList.add("hidden");
    resultsCount.textContent = "";
    if (resultsQuery) resultsQuery.textContent = "";

    const params = new URLSearchParams({
      lang: state.lang,
      unique: state.unique,
      sort: state.sort,
      sort_dir: state.sortDir,
      page: state.page,
    });
    if (state.q) params.set("q", state.q);

    try {
      const res = await fetch(`${BASE}/api/cards?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      loading.classList.add("hidden");
      if (data.error) {
        errorMsg.textContent = `Search error: ${data.error}`;
        errorMsg.classList.remove("hidden");
      }
      if (warnMsg && data.warnings?.length) {
        warnMsg.textContent = `⚠ ${data.warnings.join(" · ")}`;
        warnMsg.classList.remove("hidden");
      }
      if (data.total === 1 && data.cards?.length === 1) {
        location.href = `${BASE}/card/${data.cards[0].id}?lang=${state.lang}`;
        return;
      }
      renderCards(data.cards || [], data.total, data.page, data.pages);
    } catch (e) {
      loading.classList.add("hidden");
      errorMsg.textContent = `Failed to load: ${e.message}`;
      errorMsg.classList.remove("hidden");
    }
  }

  function renderCards(cards, total, page, pages) {
    resultsCount.textContent = `${total.toLocaleString()} card${total !== 1 ? "s" : ""}`;
    if (resultsQuery && state.q) {
      resultsQuery.textContent = `for "${state.q}"`;
    }

    if (!cards.length) {
      cardGrid.innerHTML = `<p style="color:var(--text-muted);padding:32px 0;grid-column:1/-1">No cards match your search.</p>`;
      renderPagination(page, pages);
      return;
    }

    const frag = document.createDocumentFragment();
    for (const card of cards) {
      const colorCls = card.colorClass || "";
      const tile = document.createElement("a");
      tile.className = "card-tile";
      tile.href = `${BASE}/card/${card.id}?lang=${state.lang}`;
      tile.setAttribute("aria-label", card.fullName);
      tile.innerHTML = `
        <div class="card-img-wrap">
          ${card.thumbnail
            ? `<img src="${esc(card.thumbnail)}" alt="" loading="lazy" />`
            : `<div class="card-placeholder">✦</div>`}
          ${colorCls ? `<div class="card-color-strip ${esc(colorCls)}"></div>` : ""}
        </div>
        <div class="card-body">
          <div class="card-name">${esc(card.fullName)}</div>
          <div class="card-meta">
            ${card.cost != null ? `<span class="card-cost">${card.cost}</span>` : ""}
            <span class="card-type-label">${esc(card.type)}</span>
            <span class="card-rarity-dot ${esc(card.rarity)}" title="${esc(card.rarity)}"></span>
          </div>
        </div>`;
      frag.appendChild(tile);
    }
    cardGrid.appendChild(frag);
    renderPagination(page, pages);
  }

  // ── Pagination ─────────────────────────────────────────────────────────
  function renderPagination(page, pages) {
    if (pages <= 1) return;
    const addBtn = (label, pg, disabled, active) => {
      const btn = document.createElement("button");
      btn.className = "page-btn" + (active ? " active" : "");
      btn.textContent = label;
      btn.disabled = disabled;
      if (!disabled && !active)
        btn.addEventListener("click", () => { state.page = pg; fetchCards(); window.scrollTo({ top: 0, behavior: "smooth" }); });
      return btn;
    };
    pagination.appendChild(addBtn("←", page - 1, page === 1));
    let last = null;
    for (const p of buildRange(page, pages)) {
      if (last !== null && p - last > 1) {
        const el = document.createElement("span");
        el.className = "page-ellipsis"; el.textContent = "…";
        pagination.appendChild(el);
      }
      pagination.appendChild(addBtn(p, p, false, p === page));
      last = p;
    }
    pagination.appendChild(addBtn("→", page + 1, page === pages));
  }
  function buildRange(cur, total) {
    const s = new Set([1, total]);
    for (let i = cur - 2; i <= cur + 2; i++) if (i >= 1 && i <= total) s.add(i);
    return [...s].sort((a, b) => a - b);
  }

  // ── Utilities ──────────────────────────────────────────────────────────
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Init ───────────────────────────────────────────────────────────────
  applyUrlState();
  fetchCards(false);
})();