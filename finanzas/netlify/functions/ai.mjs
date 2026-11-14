// IA de Nuestro Nido: clasifica movimientos y responde como asesor.
// Solo atiende a quien tiene sesión iniciada en el Supabase del proyecto.
import Anthropic from "@anthropic-ai/sdk";

const MODEL = process.env.ANTHROPIC_MODEL || "claude-opus-5-5";
const client = new Anthropic(); // usa ANTHROPIC_API_KEY del entorno

async function signedIn(req) {
  const auth = req.headers.get("authorization") || "";
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_ANON_KEY;
  if (!auth.startsWith("Bearer ") || !url || !key) return false;
  // Modo abierto: no hay usuarios; basta la llave pública del proyecto (cualquiera con el enlace puede usar la IA).
  if (process.env.NIDO_ABIERTO === "1") return auth === "Bearer " + key;
  try {
    const r = await fetch(url.replace(/\/$/, "") + "/auth/v1/user", { headers: { authorization: auth, apikey: key } });
    return r.ok;
  } catch { return false; }
}

export default async (req) => {
  if (req.method !== "POST") return new Response("Método no permitido", { status: 405 });
  if (!(await signedIn(req))) return new Response("Sin sesión", { status: 401 });

  let body;
  try { body = await req.json(); } catch { return new Response("JSON inválido", { status: 400 }); }
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const ok = messages.length > 0 && messages.length <= 12 && messages[messages.length - 1].role === "user" &&
    messages.every((m) => (m.role === "user" || m.role === "assistant") && typeof m.content === "string" && m.content.length <= 60000);
  if (!ok) return new Response("Mensajes inválidos", { status: 400 });
  const quick = body.tier === "quick";

  const stream = client.beta.messages.stream({
    model: MODEL,
    max_tokens: quick ? 1024 : 4096,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    output_config: { effort: quick ? "low" : "medium" },
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
  });

  // Se espera el primer fragmento antes de responder: así una llave inválida, la falta de saldo o un límite de uso
  // llegan a la página como error (401/429/502) y no como una respuesta vacía con 200.
  const enc = new TextEncoder();
  const it = stream[Symbol.asyncIterator]();
  const nextText = async () => { for (;;) { const r = await it.next(); if (r.done) return null; const ev = r.value; if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") return ev.delta.text; } };
  let first;
  try { first = await nextText(); } catch (err) {
    if (err instanceof Anthropic.RateLimitError) return new Response("Límite de uso de la IA alcanzado", { status: 429 });
    if (err instanceof Anthropic.AuthenticationError || err instanceof Anthropic.PermissionDeniedError) { console.error("IA: la llave ANTHROPIC_API_KEY no es válida o no tiene permiso"); return new Response("La llave de la IA no es válida", { status: 502 }); }
    if (err instanceof Anthropic.APIError) { console.error("IA: error", err.status, err.message); return new Response("La IA no está disponible", { status: 502 }); }
    console.error("IA: error de red", err); return new Response("La IA no está disponible", { status: 502 });
  }
  if (first === null) return new Response("La IA no devolvió texto", { status: 502 });
  const out = new ReadableStream({
    async start(controller) {
      controller.enqueue(enc.encode(first));
      try { for (;;) { const text = await nextText(); if (text === null) break; controller.enqueue(enc.encode(text)); } }
      catch (err) { console.error("IA: se cortó la respuesta", err instanceof Anthropic.APIError ? err.status + " " + err.message : err); }
      controller.close();
    },
    cancel() { stream.abort(); },
  });
  return new Response(out, { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
};
