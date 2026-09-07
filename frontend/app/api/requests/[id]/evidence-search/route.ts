import { NextResponse } from "next/server";
import { DEMO } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

/** Keyword scoring, not embeddings -- the hosted demo has no embedding model.
 *  The UI labels this so it is not mistaken for semantic retrieval. */
export async function GET(req: Request) {
  const q = (new URL(req.url).searchParams.get("q") || "").toLowerCase().trim();
  const terms = q.split(/\s+/).filter((t) => t.length > 2);

  const scored = DEMO.chunks.map((chunk) => {
    const text = chunk.content.toLowerCase();
    const hits = terms.reduce((n, t) => n + (text.split(t).length - 1), 0);
    return { chunk, score: terms.length ? hits / (terms.length * 3) : 0 };
  });

  scored.sort((a, b) => b.score - a.score);
  return NextResponse.json(
    scored.map(({ chunk, score }) => ({ ...chunk, score: Math.min(score, 1) }))
  );
}
