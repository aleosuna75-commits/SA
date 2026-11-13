/* Nuestro Nido fuera de Claude: le da a la página la misma interfaz (datos compartidos, IA, usuario)
   pero con Supabase para los datos y una función de Netlify para la IA. */
(function () {
  "use strict";
  var cfg = window.NIDO_CONFIG || {};
  if (!cfg.supabaseUrl || !cfg.supabaseAnonKey || !window.supabase) return; // sin configuración: la página avisa "sin conexión"
  var sb = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey);

  /* ---- sesión ---- */
  var resolveReady, ready = new Promise(function (r) { resolveReady = r; });
  function showLogin() {
    if (document.getElementById("nido-login")) return;
    var v = document.createElement("div"); v.className = "veil"; v.id = "nido-login"; v.style.zIndex = 90;
    v.innerHTML = '<form class="sheet in" id="nido-form" novalidate><div class="sheet-h"><h2>Entrar al nido</h2></div>' +
      '<p style="margin:0;color:var(--fg-2)">Esta página es solo para ustedes dos. Entra con el correo y la contraseña que les dieron.</p>' +
      '<div class="fld"><label for="nido-mail">Correo</label><input class="inp" id="nido-mail" type="email" autocomplete="username" inputmode="email" required></div>' +
      '<div class="fld"><label for="nido-pass">Contraseña</label><input class="inp" id="nido-pass" type="password" autocomplete="current-password" required></div>' +
      '<div class="err" id="nido-err" hidden></div><div class="sheet-acts"><button class="btn main" type="submit" id="nido-go">Entrar</button></div></form>';
    document.body.appendChild(v);
    document.getElementById("nido-form").addEventListener("submit", function (e) {
      e.preventDefault(); e.stopPropagation();
      var err = document.getElementById("nido-err"), go = document.getElementById("nido-go");
      go.disabled = true; err.hidden = true;
      sb.auth.signInWithPassword({ email: document.getElementById("nido-mail").value.trim(), password: document.getElementById("nido-pass").value })
        .then(function (r) { go.disabled = false; if (r.error) { err.textContent = "Correo o contraseña incorrectos."; err.hidden = false; } });
    });
  }
  function hideLogin() { var v = document.getElementById("nido-login"); if (v) v.remove(); }
  sb.auth.onAuthStateChange(function (_e, session) { if (session) { hideLogin(); resolveReady(); } else if (document.body) showLogin(); });
  function boot() { sb.auth.getSession().then(function (r) { if (r.data && r.data.session) { hideLogin(); resolveReady(); } else showLogin(); }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();

  /* ---- datos: una tabla docs(col, id, data) ---- */
  var subs = new Set(), timers = {};
  function fail(error) { return { code: error && (error.code === "42501" || error.status === 401 || error.status === 403) ? "invalid_argument" : "unavailable", message: (error && error.message) || "" }; }
  function fetchCol(q) {
    var r = sb.from("docs").select("id,data").eq("col", q.col);
    if (q.where) r = r.eq("data->>" + q.where[0], String(q.where[2]));
    if (q.order) r = r.order("data->>" + q.order[0], { ascending: q.order[1] !== "desc" });
    return r.limit(q.limit || 1000).then(function (res) {
      if (res.error) throw fail(res.error);
      var docs = (res.data || []).map(function (d) { return { id: d.id, exists: true, data: function () { return d.data; } }; });
      return { docs: docs, size: docs.length, empty: !docs.length };
    });
  }
  function run(s) { fetchCol(s).then(function (snap) { if (subs.has(s)) s.cb(snap); }, function (e) { if (subs.has(s) && s.err && !s.started) s.err(e); }).then(function () { s.started = true; }); }
  function refresh(col) { clearTimeout(timers[col]); timers[col] = setTimeout(function () { subs.forEach(function (s) { if (!col || s.col === col) run(s); }); }, 60); }
  function query(col, st) {
    return {
      where: function (f, op, v) { return query(col, Object.assign({}, st, { where: [f, op, v] })); },
      orderBy: function (f, d) { return query(col, Object.assign({}, st, { order: [f, d] })); },
      limit: function (n) { return query(col, Object.assign({}, st, { limit: n })); },
      get: function () { return fetchCol(Object.assign({ col: col }, st)); },
      onSnapshot: function (cb, err) { var s = Object.assign({ col: col, cb: cb, err: err }, st); subs.add(s); run(s); return function () { subs.delete(s); }; },
      doc: function (id) {
        return {
          set: function (data) { return sb.from("docs").upsert({ col: col, id: id, data: data, updated_at: new Date().toISOString() }).then(function (r) { if (r.error) throw fail(r.error); refresh(col); }); },
          delete: function () { return sb.from("docs").delete().eq("col", col).eq("id", id).then(function (r) { if (r.error) throw fail(r.error); refresh(col); }); }
        };
      }
    };
  }
  var db = { collection: function (col) { return query(col, {}); } };
  ready.then(function () {
    sb.channel("docs").on("postgres_changes", { event: "*", schema: "public", table: "docs" }, function (p) { refresh((p.new && p.new.col) || (p.old && p.old.col) || ""); }).subscribe();
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(""); });
  });

  /* ---- IA: función de Netlify ---- */
  function ask(input, opts) {
    opts = opts || {};
    return sb.auth.getSession().then(function (r) {
      var s = r.data && r.data.session; if (!s) throw { code: "not_granted", message: "sin sesión" };
      return fetch("/.netlify/functions/ai", { method: "POST", signal: opts.signal, headers: { "content-type": "application/json", authorization: "Bearer " + s.access_token },
        body: JSON.stringify({ messages: typeof input === "string" ? [{ role: "user", content: input }] : input, tier: opts.modelTier || "default" }) });
    }).then(function (res) {
      if (!res.ok || !res.body) throw { code: res.status === 429 ? "rate_limited" : res.status === 401 ? "not_granted" : "unavailable", message: "IA no disponible" };
      var reader = res.body.getReader(), dec = new TextDecoder(), text = "";
      function pump() { return reader.read().then(function (c) {
        if (c.done) { if (!text.trim()) throw { code: "unavailable", message: "respuesta vacía" }; return text; }
        var delta = dec.decode(c.value, { stream: true }); text += delta; if (opts.onText && delta) opts.onText({ text: text, delta: delta }); return pump(); }); }
      return pump();
    });
  }
  function sample(input, opts) { return ask(input, opts).then(function (t) { return { text: t, truncated: false }; }); }
  sample.json = function (input, opts) {
    return ask(input, opts).then(function (t) {
      try { return JSON.parse(t); } catch (e) {}
      var a = t.search(/[{[]/), b = Math.max(t.lastIndexOf("}"), t.lastIndexOf("]"));
      try { if (a >= 0 && b > a) return JSON.parse(t.slice(a, b + 1)); } catch (e) {}
      throw { code: "invalid_json", message: "sin JSON", text: t };
    });
  };
  sample.limits = function () { return Promise.resolve({ maxPromptBytes: 60000 }); };

  var user = { can: function () { return Promise.resolve(true); }, isOwner: function () { return Promise.resolve(false); }, canEdit: function () { return Promise.resolve(true); },
    id: function () { return sb.auth.getSession().then(function (r) { return r.data && r.data.session ? r.data.session.user.id : null; }); } };

  window.claude = { use: function (name) {
    if (name === "db") return ready.then(function () { return db; });
    if (name === "sample") return Promise.resolve(sample);
    if (name === "user") return Promise.resolve(user);
    return Promise.resolve(null);
  } };
  window.nidoSalir = function () { return sb.auth.signOut().then(function () { location.reload(); }); };
})();
