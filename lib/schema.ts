import { pool } from "./db";

let sensorColumnsPromise: Promise<void> | null = null;

/**
 * Existing Neon projects were created before the outside I2C sensor was added.
 * IF NOT EXISTS makes this safe when several serverless instances start together.
 */
export function ensureSensorColumns(): Promise<void> {
  if (!sensorColumnsPromise) {
    sensorColumnsPromise = pool.query(`
      ALTER TABLE devices
        ADD COLUMN IF NOT EXISTS last_outside_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS last_outside_object_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS last_inside_outside_delta_c double precision;

      ALTER TABLE telemetry
        ADD COLUMN IF NOT EXISTS outside_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS outside_object_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS inside_outside_delta_c double precision;

      ALTER TABLE fire_events
        ADD COLUMN IF NOT EXISTS humidity_pct double precision,
        ADD COLUMN IF NOT EXISTS outside_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS outside_object_temperature_c double precision,
        ADD COLUMN IF NOT EXISTS inside_outside_delta_c double precision;
    `).then(() => undefined).catch((error) => {
      sensorColumnsPromise = null;
      throw error;
    });
  }
  return sensorColumnsPromise;
}
