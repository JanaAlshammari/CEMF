(() => {
  const API = "/api/v1";
  const TOKEN_KEY = "cemf_token";

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const dateTimeFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
  const fmtDateTime = (iso) => dateTimeFmt.format(new Date(iso));
  const fmtTime = (iso) => timeFmt.format(new Date(iso));
  const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
  const fmtRange = (start, end) => `${fmtDateTime(start)} to ${sameDay(start, end) ? fmtTime(end) : fmtDateTime(end)}`;

  function formatDetail(d) {
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map((e) => {
        const field = (e.loc || []).filter((x) => x !== "body").join(".");
        return field ? `${field}: ${e.msg}` : e.msg;
      }).join("; ");
    }
    return "Something went wrong. Please try again.";
  }

  // ---------- API ----------
  async function api(path, opts = {}) {
    const { method = "GET", body, form } = opts;
    const headers = {};
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && !form) headers.Authorization = `Bearer ${token}`;
    let payload;
    if (form) {
      payload = new URLSearchParams(form);
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (body !== undefined) {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    let res;
    try {
      res = await fetch(API + path, { method, headers, body: payload });
    } catch {
      throw new ApiError(0, "Can't reach the server. Check that it is running.");
    }
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }

    if (res.status === 401 && token && !form) {
      // Expired or invalid token: drop it, and retry once as a guest (public pages still work).
      localStorage.removeItem(TOKEN_KEY);
      if (!opts._retried) return api(path, { ...opts, _retried: true });
    }
    if (!res.ok) throw new ApiError(res.status, formatDetail(data && data.detail));
    return data;
  }

  async function download(path, filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const res = await fetch(API + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) {
      let d = null; try { d = await res.json(); } catch { /* not json */ }
      throw new ApiError(res.status, formatDetail(d && d.detail));
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ---------- auth ----------
  let _user;
  async function currentUser() {
    if (_user !== undefined) return _user;
    if (!localStorage.getItem(TOKEN_KEY)) return (_user = null);
    try { _user = await api("/users/me"); } catch { _user = null; }
    return _user;
  }
  const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
  function logout() { localStorage.removeItem(TOKEN_KEY); window.location.href = "/"; }
  async function requireLogin() {
    const user = await currentUser();
    if (!user) {
      window.location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
      return null;
    }
    return user;
  }
  function safeNext(value) {
    return value && value.startsWith("/") && !value.startsWith("//") ? value : "/events";
  }

  // ---------- UI pieces ----------
  const CAT = { academic: "Academic", workshop: "Workshop", social: "Social", sports: "Sports", cultural: "Cultural", career: "Career", competition: "Competition", other: "Other" };
  const CAT_DOT = { academic: "bg-sky-500", workshop: "bg-violet-500", social: "bg-pink-500", sports: "bg-emerald-500", cultural: "bg-orange-500", career: "bg-indigo-500", competition: "bg-red-500", other: "bg-slate-400" };
  const STATUS = {
    draft: ["Draft", "bg-amber-100 text-amber-800"],
    published: ["Published", "bg-emerald-100 text-emerald-800"],
    cancelled: ["Cancelled", "bg-red-100 text-red-700"],
    completed: ["Completed", "bg-slate-200 text-slate-700"],
  };
  const statusBadge = (s) => {
    const [label, cls] = STATUS[s] || [s, "bg-slate-200 text-slate-700"];
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  };

  function seatsMeter(e) {
    const pct = e.capacity ? Math.min(100, Math.round((e.registered_count / e.capacity) * 100)) : 0;
    const full = e.seats_left === 0;
    const low = !full && e.seats_left <= Math.max(5, e.capacity * 0.1);
    const color = full ? "bg-coral" : low ? "bg-marigold" : "bg-brand";
    return `<div class="h-2 rounded-full bg-slate-200 overflow-hidden" role="img" aria-label="${pct}% of seats taken"><div class="h-full ${color}" style="width:${pct}%"></div></div>`;
  }

  function eventCard(e) {
    const d = new Date(e.start_time);
    const seats = e.seats_left === 0 ? "Fully booked" : `${e.seats_left} ${e.seats_left === 1 ? "seat" : "seats"} left`;
    return `<a href="/events/${esc(e.id)}" class="ticket">
      <div class="stub py-4" aria-hidden="true">
        <span class="font-display font-extrabold text-3xl leading-none">${d.getDate()}</span>
        <span class="text-sm font-semibold mt-1">${esc(d.toLocaleString(undefined, { month: "short" }))}</span>
      </div>
      <div class="p-4 flex-1 min-w-0">
        <div class="flex items-center gap-2 text-sm"><span class="w-2 h-2 rounded-full ${CAT_DOT[e.category] || "bg-slate-400"}"></span>${esc(CAT[e.category] || e.category)}</div>
        <h3 class="font-display font-bold text-lg text-ink leading-snug mt-1 clamp-2">${esc(e.title)}</h3>
        <p class="text-sm mt-1">${esc(fmtRange(e.start_time, e.end_time))}</p>
        <div class="mt-3">${seatsMeter(e)}<p class="text-xs mt-1">${seats}</p></div>
      </div>
    </a>`;
  }

  const emptyState = (title, text) =>
    `<div class="col-span-full bg-white rounded-2xl p-8 text-center"><p class="font-display font-bold text-xl text-ink">${esc(title)}</p><p class="mt-1">${esc(text)}</p></div>`;
  const errorBox = (msg) =>
    `<div class="col-span-full rounded-2xl p-6 bg-red-50 text-red-700" role="alert">${esc(msg)}</div>`;

  function toast(message, type = "success") {
    const el = document.createElement("div");
    el.className = `toast rounded-xl px-4 py-3 text-sm font-semibold shadow-lg max-w-sm ${type === "error" ? "bg-coral text-white" : "bg-ink text-white"}`;
    el.textContent = message;
    document.getElementById("toasts").appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  const setBusy = (btn, busy) => { btn.disabled = busy; btn.setAttribute("aria-busy", busy); };

  // ---------- navigation ----------
  async function initNav() {
    const user = await currentUser();
    const box = document.getElementById("navAuth");
    if (user) {
      box.innerHTML = `<span class="hidden sm:inline text-sm text-white/80">${esc(user.full_name)}</span>
        <button id="logoutBtn" class="text-sm px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20">Log out</button>`;
      document.getElementById("logoutBtn").addEventListener("click", logout);
    } else {
      box.innerHTML = `<a href="/login" class="text-sm px-3 py-1.5 rounded-lg hover:bg-white/10">Log in</a>
        <a href="/register" class="text-sm px-3 py-1.5 rounded-lg bg-marigold text-ink font-semibold hover:brightness-95">Sign up</a>`;
    }
    document.querySelectorAll("[data-requires-login]").forEach((el) => el.classList.toggle("hidden", !user));
    document.querySelectorAll("[data-nav]").forEach((a) => {
      const href = a.getAttribute("href");
      if (location.pathname === href || (href !== "/" && location.pathname.startsWith(href))) a.setAttribute("aria-current", "page");
    });
    const toggle = document.getElementById("navToggle");
    toggle.addEventListener("click", () => {
      const menu = document.getElementById("mobileMenu");
      const open = menu.classList.toggle("hidden") === false;
      toggle.setAttribute("aria-expanded", open);
    });
  }

  window.CEMF = { api, download, esc, currentUser, requireLogin, setToken, logout, safeNext, toast, setBusy,
    fmtDateTime, fmtTime, fmtRange, statusBadge, seatsMeter, eventCard, emptyState, errorBox, CAT, CAT_DOT };
  document.addEventListener("DOMContentLoaded", initNav);
})();
