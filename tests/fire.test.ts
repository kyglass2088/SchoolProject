import assert from "node:assert/strict";
import test from "node:test";
import { decideFire } from "../lib/fire.ts";

const now = new Date("2026-07-15T00:01:00.000Z");

test("normal temperature stays normal", () => {
  const result = decideFire({ temperatureC: 25, outsideTemperatureC: 24 }, now, null);
  assert.equal(result.fire, false);
  assert.equal(result.reason, "normal");
  assert.equal(result.insideOutsideDeltaC, 1);
});

test("critical temperature always triggers fire", () => {
  const result = decideFire({ temperatureC: 70 }, now, null);
  assert.equal(result.fire, true);
  assert.equal(result.reason, "critical_temperature");
});

test("high temperature alone does not trigger without supporting evidence", () => {
  const result = decideFire({ temperatureC: 56 }, now, null);
  assert.equal(result.fire, false);
});

test("high temperature and rapid rise trigger fire", () => {
  const result = decideFire(
    { temperatureC: 60 },
    now,
    { temperatureC: 50, receivedAt: new Date("2026-07-15T00:00:00.000Z") },
  );
  assert.equal(result.fire, true);
  assert.equal(result.reason, "high_temperature_and_fast_rise");
  assert.equal(result.riseCPerMin, 10);
});

test("high temperature and large outside delta trigger fire", () => {
  const result = decideFire({ temperatureC: 56, outsideTemperatureC: 25 }, now, null);
  assert.equal(result.fire, true);
  assert.equal(result.reason, "high_temperature_and_outside_delta");
  assert.equal(result.insideOutsideDeltaC, 31);
});

test("reported delta is used when supplied by the ESP32", () => {
  const result = decideFire(
    { temperatureC: 56, outsideTemperatureC: 50, insideOutsideDeltaC: 22 },
    now,
    null,
  );
  assert.equal(result.fire, true);
  assert.equal(result.insideOutsideDeltaC, 22);
});
