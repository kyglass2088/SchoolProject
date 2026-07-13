import { NextRequest, NextResponse } from "next/server";
import { rejectUnauthorizedGateway } from "../../../../../lib/auth";
import { transaction } from "../../../../../lib/db";

export const runtime = "nodejs";

// 현장 안전 확인 후 운영자 시스템이 호출하는 복구 API. 앱 사용자에게는 노출하지 않는다.
export async function POST(
  request: NextRequest,
  { params }: { params: { eventId: string } },
) {
  const unauthorized = rejectUnauthorizedGateway(request);
  if (unauthorized) return unauthorized;

  const command = await transaction(async (client) => {
    const event = await client.query(
      `UPDATE fire_events SET status = 'resolved', resolved_at = now()
       WHERE id = $1 AND status = 'active' RETURNING device_id`,
      [params.eventId],
    );
    if (event.rowCount === 0) return null;
    const result = await client.query(
      `INSERT INTO commands(device_id, fire_event_id, action, reason)
       VALUES($1,$2,'RESET_FIRE_RESPONSE','operator_confirmed_safe')
       RETURNING id AS "commandId", action, reason, created_at AS "issuedAt"`,
      [event.rows[0].device_id, params.eventId],
    );
    return result.rows[0];
  });
  if (!command) return NextResponse.json({ error: "active_event_not_found" }, { status: 404 });
  return NextResponse.json({ ok: true, command });
}

