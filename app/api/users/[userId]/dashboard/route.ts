import { NextResponse } from "next/server";
import { z } from "zod";
import { pool } from "../../../../../lib/db";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: { userId: string } },
) {
  if (!z.string().uuid().safeParse(params.userId).success) {
    return NextResponse.json({ error: "invalid_user_id" }, { status: 400 });
  }

  const userResult = await pool.query("SELECT id, name FROM users WHERE id = $1", [params.userId]);
  if (userResult.rowCount === 0) return NextResponse.json({ error: "user_not_found" }, { status: 404 });

  const spots = await pool.query(
    `SELECT p.id, p.label, p.vehicle_number AS "vehicleNumber",
            d.id AS "deviceId", d.last_seen_at AS "lastSeenAt",
            d.last_temperature_c AS "temperatureC", d.last_humidity_pct AS "humidityPct"
     FROM parking_spots p LEFT JOIN devices d ON d.parking_spot_id = p.id
     WHERE p.owner_user_id = $1 ORDER BY p.id`,
    [params.userId],
  );
  const alerts = await pool.query(
    `SELECT id, parking_spot_id AS "parkingSpotId", reason,
            temperature_c AS "temperatureC", started_at AS "startedAt", status
     FROM fire_events WHERE owner_user_id = $1 AND status = 'active'
     ORDER BY started_at DESC`,
    [params.userId],
  );
  return NextResponse.json({ user: userResult.rows[0], spots: spots.rows, activeAlerts: alerts.rows });
}

