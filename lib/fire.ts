export type PreviousReading = { temperatureC: number; receivedAt: Date } | null;

export type FireReading = {
  temperatureC: number;
  humidityPct?: number;
  outsideTemperatureC?: number;
  outsideObjectTemperatureC?: number;
  insideOutsideDeltaC?: number;
};

export type FireDecision = {
  fire: boolean;
  reason:
    | "critical_temperature"
    | "high_temperature_and_fast_rise"
    | "high_temperature_and_outside_delta"
    | "normal";
  riseCPerMin: number | null;
  insideOutsideDeltaC: number | null;
};

export function decideFire(
  reading: FireReading,
  now: Date,
  previous: PreviousReading,
): FireDecision {
  const critical = Number(process.env.FIRE_CRITICAL_TEMP_C ?? 70);
  const high = Number(process.env.FIRE_HIGH_TEMP_C ?? 55);
  const requiredRise = Number(process.env.FIRE_RISE_C_PER_MIN ?? 8);
  const requiredOutsideDelta = Number(process.env.FIRE_OUTSIDE_DELTA_C ?? 20);
  const temperatureC = reading.temperatureC;

  const referenceOutsideC = reading.outsideTemperatureC ?? reading.outsideObjectTemperatureC;
  const insideOutsideDeltaC = reading.insideOutsideDeltaC
    ?? (referenceOutsideC === undefined ? null : temperatureC - referenceOutsideC);

  let riseCPerMin: number | null = null;
  if (previous) {
    const minutes = (now.getTime() - previous.receivedAt.getTime()) / 60_000;
    if (minutes > 0.01 && minutes < 10) {
      riseCPerMin = (temperatureC - previous.temperatureC) / minutes;
    }
  }

  if (temperatureC >= critical) {
    return { fire: true, reason: "critical_temperature", riseCPerMin, insideOutsideDeltaC };
  }
  if (temperatureC >= high && riseCPerMin !== null && riseCPerMin >= requiredRise) {
    return { fire: true, reason: "high_temperature_and_fast_rise", riseCPerMin, insideOutsideDeltaC };
  }
  if (temperatureC >= high && insideOutsideDeltaC !== null && insideOutsideDeltaC >= requiredOutsideDelta) {
    return { fire: true, reason: "high_temperature_and_outside_delta", riseCPerMin, insideOutsideDeltaC };
  }
  return { fire: false, reason: "normal", riseCPerMin, insideOutsideDeltaC };
}
