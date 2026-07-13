export type PreviousReading = { temperatureC: number; receivedAt: Date } | null;

export type FireDecision = {
  fire: boolean;
  reason: "critical_temperature" | "high_temperature_and_fast_rise" | "normal";
  riseCPerMin: number | null;
};

export function decideFire(
  temperatureC: number,
  now: Date,
  previous: PreviousReading,
): FireDecision {
  const critical = Number(process.env.FIRE_CRITICAL_TEMP_C ?? 70);
  const high = Number(process.env.FIRE_HIGH_TEMP_C ?? 55);
  const requiredRise = Number(process.env.FIRE_RISE_C_PER_MIN ?? 8);

  let riseCPerMin: number | null = null;
  if (previous) {
    const minutes = (now.getTime() - previous.receivedAt.getTime()) / 60_000;
    if (minutes > 0.01 && minutes < 10) {
      riseCPerMin = (temperatureC - previous.temperatureC) / minutes;
    }
  }

  if (temperatureC >= critical) {
    return { fire: true, reason: "critical_temperature", riseCPerMin };
  }
  if (temperatureC >= high && riseCPerMin !== null && riseCPerMin >= requiredRise) {
    return { fire: true, reason: "high_temperature_and_fast_rise", riseCPerMin };
  }
  return { fire: false, reason: "normal", riseCPerMin };
}

