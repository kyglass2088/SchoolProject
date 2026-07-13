import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { pool } from "../../../../lib/db";

export const runtime = "nodejs";

const RegisterSchema = z.object({
  userId: z.string().uuid(),
  token: z.string().startsWith("ExponentPushToken[").or(z.string().startsWith("ExpoPushToken[")),
  platform: z.enum(["ios", "android"]),
});

export async function POST(request: NextRequest) {
  const parsed = RegisterSchema.safeParse(await request.json());
  if (!parsed.success) return NextResponse.json({ error: "invalid_push_registration" }, { status: 400 });

  const user = await pool.query("SELECT id FROM users WHERE id = $1", [parsed.data.userId]);
  if (user.rowCount === 0) return NextResponse.json({ error: "user_not_found" }, { status: 404 });

  await pool.query(
    `INSERT INTO push_tokens(token, user_id, platform) VALUES($1,$2,$3)
     ON CONFLICT(token) DO UPDATE SET user_id = EXCLUDED.user_id,
       platform = EXCLUDED.platform, updated_at = now()`,
    [parsed.data.token, parsed.data.userId, parsed.data.platform],
  );
  return NextResponse.json({ ok: true });
}

