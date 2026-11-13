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

  const enc = new TextEncoder();
  const out = new ReadableStream({
    async start(controller) {
      try {
        for await (const event of stream) {
          if (event.type === "content_block_delta" && event.delta.type === "text_delta") controller.enqueue(enc.encode(event.delta.text));
        }
      } catch (err) {
        if (err instanceof Anthropic.RateLimitError) console.error("IA: límite de uso alcanzado");
        else if (err instanceof Anthropic.AuthenticationError) console.error("IA: la llave ANTHROPIC_API_KEY no es válida");
        else if (err instanceof Anthropic.APIError) console.error("IA: error", err.status, err.message);
        else console.error("IA: error de red", err);
      }
      controller.close();
    },
    cancel() { stream.abort(); },
  });
  return new Response(out, { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
};
