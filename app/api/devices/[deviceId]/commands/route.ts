import { NextRequest, NextResponse } from "next/server";
import { rejectUnauthorizedGateway } from "../../../../../lib/auth";
import { pool } from "../../../../../lib/db";

export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: { deviceId: string } },
) {
  const unauthorized = rejectUnauthorizedGateway(request);
  if (unauthorized) return unauthorized;

  const result = await pool.query(
    `SELECT id AS "commandId", action, reason, created_at AS "issuedAt"
     FROM commands WHERE device_id = $1 AND status = 'pending'
     ORDER BY created_at ASC LIMIT 10`,
    [params.deviceId],
  );
  return NextResponse.json({ commands: result.rows });
}

