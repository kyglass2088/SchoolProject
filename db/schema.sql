CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY,
  name text NOT NULL,
  phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parking_spots (
  id text PRIMARY KEY,
  label text NOT NULL,
  owner_user_id uuid REFERENCES users(id),
  vehicle_number text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS devices (
  id text PRIMARY KEY,
  parking_spot_id text NOT NULL REFERENCES parking_spots(id),
  last_seen_at timestamptz,
  last_temperature_c double precision,
  last_humidity_pct double precision,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry (
  id bigserial PRIMARY KEY,
  device_id text NOT NULL REFERENCES devices(id),
  parking_spot_id text NOT NULL REFERENCES parking_spots(id),
  boot_id text NOT NULL,
  sequence bigint NOT NULL,
  temperature_c double precision,
  humidity_pct double precision,
  sensor_ok boolean NOT NULL,
  emergency_active boolean NOT NULL DEFAULT false,
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(device_id, boot_id, sequence)
);
CREATE INDEX IF NOT EXISTS telemetry_device_time_idx
  ON telemetry(device_id, received_at DESC);

CREATE TABLE IF NOT EXISTS fire_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL REFERENCES devices(id),
  parking_spot_id text NOT NULL REFERENCES parking_spots(id),
  owner_user_id uuid REFERENCES users(id),
  status text NOT NULL CHECK (status IN ('active', 'resolved')),
  reason text NOT NULL,
  temperature_c double precision NOT NULL,
  rise_c_per_min double precision,
  started_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_fire_per_spot_idx
  ON fire_events(parking_spot_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS commands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id text NOT NULL REFERENCES devices(id),
  fire_event_id uuid REFERENCES fire_events(id),
  action text NOT NULL CHECK (action IN ('ACTIVATE_FIRE_RESPONSE', 'RESET_FIRE_RESPONSE')),
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'executed', 'failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  executed_at timestamptz
);
CREATE INDEX IF NOT EXISTS commands_pending_idx
  ON commands(device_id, created_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS push_tokens (
  token text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  platform text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- 시연용 데이터: 앱 .env의 EXPO_PUBLIC_USER_ID와 동일해야 한다.
INSERT INTO users(id, name, phone)
VALUES ('11111111-1111-4111-8111-111111111111', '홍길동', '010-0000-0000')
ON CONFLICT (id) DO NOTHING;

INSERT INTO parking_spots(id, label, owner_user_id, vehicle_number)
VALUES ('A-01', 'A구역 01번', '11111111-1111-4111-8111-111111111111', '12가 3456')
ON CONFLICT (id) DO NOTHING;
