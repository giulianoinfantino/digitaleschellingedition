import { next } from "@vercel/edge";

export const config = {
  // Auf alles anwenden außer interne Vercel-Pfade.
  matcher: "/((?!_next|_vercel|favicon.ico).*)",
};

const REALM = "Schelling-Edition";
const USERNAME = "schelling";

function unauthorized(): Response {
  return new Response("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "Cache-Control": "no-store",
    },
  });
}

export default function middleware(req: Request): Response | undefined {
  const expected = (globalThis as unknown as { process?: { env: Record<string, string | undefined> } })
    .process?.env?.SITE_PASSWORD;
  if (!expected) {
    return new Response(
      "SITE_PASSWORD env var ist nicht gesetzt. `vercel env add SITE_PASSWORD` ausführen, dann redeployen.",
      { status: 503 },
    );
  }

  const header = req.headers.get("authorization");
  if (!header || !header.toLowerCase().startsWith("basic ")) {
    return unauthorized();
  }

  const encoded = header.slice(6).trim();
  let decoded: string;
  try {
    decoded = atob(encoded);
  } catch {
    return unauthorized();
  }

  const sep = decoded.indexOf(":");
  if (sep < 0) return unauthorized();

  const user = decoded.slice(0, sep);
  const pass = decoded.slice(sep + 1);

  if (user !== USERNAME || pass !== expected) {
    return unauthorized();
  }

  return next();
}
