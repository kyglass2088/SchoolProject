import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { rejectUnauthorizedGateway } from "../../../lib/auth";
import { pool, transaction } from "../../../lib/db";
import { decideFire } from "../../../lib/fire";
import { sendExpoPush } from "../../../lib/push";

export const runtime = "nodejs";

const TelemetrySchema = z.object({
  type: z.literal("telemetry"),
  deviceId: z.string().min(1).max(100),
  parkingSpotId: z.string().min(1).max(100),
  bootId: z.string().min(1).max(100),
  sequence: z.number().int().nonnegative(),
  sensorOk: z.boolean(),
  temperatureC: z.number().min(-50).max(200).optional(),
  humidityPct: z.number().min(0).max(100).optional(),
  outsideTemperatureC: z.number().min(-50).max(200).optional(),
  outsideObjectTemperatureC: z.number().min(-50).max(380).optional(),
  insideOutsideDeltaC: z.number().min(-250).max(250).optional(),
  emergencyActive: z.boolean().optional().default(false),
}).refine((value) => !value.sensorOk || value.temperatureC !== undefined, {
  message: "temperatureC is required when sensorOk is true",
});

type CommandDto = { commandId: string; action: string; reason: string; issuedAt: Date };

export async function POST(request: NextRequest) {
  const unauthorized = rejectUnauthorizedGateway(request);
  if (unauthorized) return unauthorized;

  const parsed = TelemetrySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_telemetry", details: parsed.error.flatten() }, { status: 400 });
  }
  const input = parsed.data;
  const receivedAt = new Date();

  const spot = await pool.query("SELECT owner_user_id FROM parking_spots WHERE id = $1", [input.parkingSpotId]);
  if (spot.rowCount === 0) {
    return NextResponse.json({ error: "unknown_parking_spot" }, { status: 404 });
  }

  const previousResult = await pool.query(
    `SELECT temperature_c, received_at FROM telemetry
     WHERE device_id = $1 AND sensor_ok = true ORDER BY received_at DESC LIMIT 1`,
    [input.deviceId],
  );

  await pool.query(
    `INSERT INTO devices(id, parking_spot_id, last_seen_at, last_temperature_c, last_humidity_pct)
     VALUES($1, $2, $3, $4, $5)
     ON CONFLICT(id) DO UPDATE SET parking_spot_id = EXCLUDED.parking_spot_id,
       last_seen_at = EXCLUDED.last_seen_at, last_temperature_c = EXCLUDED.last_temperature_c,
       last_humidity_pct = EXCLUDED.last_humidity_pct`,
    [input.deviceId, input.parkingSpotId, receivedAt, input.temperatureC ?? null, input.humidityPct ?? null],
  );

  await pool.query(
    `INSERT INTO telemetry(device_id, parking_spot_id, boot_id, sequence, temperature_c, humidity_pct, sensor_ok, emergency_active, received_at)
     VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(device_id, boot_id, sequence) DO NOTHING`,
    [input.deviceId, input.parkingSpotId, input.bootId, input.sequence, input.temperatureC ?? null,
      input.humidityPct ?? null, input.sensorOk, input.emergencyActive, receivedAt],
  );

  if (!input.sensorOk || input.temperatureC === undefined) {
    return NextResponse.json({ accepted: true, fireDecision: { fire: false, reason: "sensor_error" }, commands: [] });
  }

  const previous = previousResult.rows[0]
    ? { temperatureC: Number(previousResult.rows[0].temperature_c), receivedAt: new Date(previousResult.rows[0].received_at) }
    : null;
  const decision = decideFire(input.temperatureC, receivedAt, previous);
  let command: CommandDto | null = null;
  let notification: { tokens: string[]; eventId: string } | null = null;

  if (decision.fire) {
    const active = await pool.query(
      "SELECT id FROM fire_events WHERE parking_spot_id = $1 AND status = 'active' LIMIT 1",
      [input.parkingSpotId],
    );
    if (active.rowCount === 0) {
      try {
        const created = await transaction(async (client) => {
          const event = await client.query(
            `INSERT INTO fire_events(device_id, parking_spot_id, owner_user_id, status, reason, temperature_c, rise_c_per_min)
             VALUES($1,$2,$3,'active',$4,$5,$6) RETURNING id`,
            [input.deviceId, input.parkingSpotId, spot.rows[0].owner_user_id, decision.reason,
              input.temperatureC, decision.riseCPerMin],
          );
          const commandResult = await client.query(
            `INSERT INTO commands(device_id, fire_event_id, action, reason)
             VALUES($1,$2,'ACTIVATE_FIRE_RESPONSE',$3)
             RETURNING id AS "commandId", action, reason, created_at AS "issuedAt"`,
            [input.deviceId, event.rows[0].id, decision.reason],
          );
          let tokens: string[] = [];
          if (spot.rows[0].owner_user_id) {
            const tokenResult = await client.query<{ token: string }>(
              "SELECT token FROM push_tokens WHERE user_id = $1",
              [spot.rows[0].owner_user_id],
            );
            tokens = tokenResult.rows.map((row) => row.token);
          }
          return { eventId: event.rows[0].id, command: commandResult.rows[0], tokens };
        });
        command = created.command;
        notification = { tokens: created.tokens, eventId: created.eventId };
      } catch (error: unknown) {
        // 동시에 들어온 측정값이 활성 이벤트를 먼저 만든 경우 unique violation은 무시한다.
        if (!(typeof error === "object" && error !== null && "code" in error && error.code === "23505")) throw error;
      }
    }
  }

  if (notification) {
    try {
      await sendExpoPush(
        notification.tokens,
        "전기차 화재 위험 감지",
        `${input.parkingSpotId} 구역에서 ${input.temperatureC.toFixed(1)}°C가 감지되어 차단막과 펌프를 작동합니다.`,
        { eventId: notification.eventId, parkingSpotId: input.parkingSpotId, type: "FIRE_ALERT" },
      );
    } catch (error) {
      // 제어 명령은 유지하고 알림 실패를 Vercel 로그에 남긴다.
      console.error("push notification failed", error);
    }
  }

  return NextResponse.json({ accepted: true, fireDecision: decision, commands: command ? [command] : [] });
}
