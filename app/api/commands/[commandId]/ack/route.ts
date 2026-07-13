import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { rejectUnauthorizedGateway } from "../../../../../lib/auth";
import { pool } from "../../../../../lib/db";

export const runtime = "nodejs";

const AckSchema = z.object({
  deviceId: z.string().min(1),
  status: z.string().min(1),
});

export async function POST(
  request: NextRequest,
  { params }: { params: { commandId: string } },
) {
  const unauthorized = rejectUnauthorizedGateway(request);
  if (unauthorized) return unauthorized;
  const parsed = AckSchema.safeParse(await request.json());
  if (!parsed.success) return NextResponse.json({ error: "invalid_ack" }, { status: 400 });

  const serverStatus = parsed.data.status === "executed" ? "executed" : "failed";
  const result = await pool.query(
    `UPDATE commands SET status = $1, executed_at = now()
     WHERE id = $2 AND device_id = $3 AND status = 'pending' RETURNING id`,
    [serverStatus, params.commandId, parsed.data.deviceId],
  );
  if (result.rowCount === 0) {
    // 이미 ACK된 명령도 멱등 성공으로 처리한다.
    const existing = await pool.query("SELECT id FROM commands WHERE id = $1 AND device_id = $2", [params.commandId, parsed.data.deviceId]);
    if (existing.rowCount === 0) return NextResponse.json({ error: "command_not_found" }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}

