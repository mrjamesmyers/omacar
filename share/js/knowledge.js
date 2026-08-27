// What a trouble code means, and what to do about it.
//
// `data/dtc.json` carries the deep entries — ranked causes, the live values
// that prove each one, test procedures. It cannot carry every code, because
// there are thousands and most of them nobody ever sees. So anything not in
// the file falls through to the decoder below, which reads the code's own
// structure and produces something honest and useful rather than "unknown".
//
// That fallback is why this tool works on a car it has never met, which is the
// difference between a demo and a scan tool.

const FAMILY = {
  P: "Powertrain", C: "Chassis", B: "Body", U: "Network",
};

// The second character: 0 and 2 are the generic OBD-II set every manufacturer
// shares; 1 and 3 are the manufacturer's own. Knowing which you are looking at
// tells you whether a generic tool can be trusted about it at all.
const SCOPE = {
  0: "generic (SAE)", 1: "manufacturer-specific", 2: "generic (SAE)", 3: "manufacturer-specific",
};

// The third character of a P code: which subsystem set it.
const P_SUBSYSTEM = {
  0: "Fuel and air metering, auxiliary emission controls",
  1: "Fuel and air metering",
  2: "Fuel and air metering — injector circuit",
  3: "Ignition system or misfire",
  4: "Auxiliary emission controls",
  5: "Vehicle speed control, idle control, auxiliary inputs",
  6: "Computer output circuit",
  7: "Transmission",
  8: "Transmission",
  9: "Transmission, gear ratios",
  A: "Hybrid propulsion",
  B: "Hybrid propulsion",
  C: "Hybrid propulsion",
};

export function decode(code) {
  const c = String(code || "").toUpperCase().trim();
  const m = /^([PCBU])([0-3])([0-9A-C])([0-9A-F]{2})$/.exec(c);
  if (!m) return { code: c, title: c, system: "Unknown", scope: "", generic: false };
  const [, fam, scope, sub, rest] = m;
  const family = FAMILY[fam] || "Unknown";
  const subsystem = fam === "P" ? (P_SUBSYSTEM[sub] || "Powertrain") : family;
  return {
    code: c,
    title: `${family} code ${c}`,
    system: subsystem,
    scope: SCOPE[scope] || "",
    generic: scope === "0" || scope === "2",
    decoded: true,
    meaning:
      `${c} is a ${SCOPE[scope] || "manufacturer"} ${family.toLowerCase()} code. ` +
      (fam === "P"
        ? `The third character puts it in: ${subsystem.toLowerCase()}.`
        : `${family} codes are set by modules a generic OBD-II adapter cannot usually read, so the detail has to come from the module itself.`) +
      (scope === "1" || scope === "3"
        ? " Because it is manufacturer-specific, its meaning is defined by the carmaker rather than by the OBD-II standard — check the service information for this model before acting on it."
        : ""),
    fault: rest,
  };
}

// The knowledge file plus the decoder, in that order.
export function lookup(kb, code) {
  const entry = (kb || {})[String(code || "").toUpperCase()];
  if (entry) return Object.assign({ code, known: true }, entry);
  return Object.assign(decode(code), { known: false, causes: [], smart: [], tests: [] });
}

// The live values worth watching for this code, resolved against what the car
// is actually reporting. This is the piece that turns a code into a diagnosis:
// the tool picks the channels rather than making the technician remember them.
export const PID_META = {
  RPM: { label: "Engine speed", unit: "rpm", get: (v) => v.RPM, dp: 0 },
  SPEED: { label: "Vehicle speed", unit: "speed", get: (v) => v.SPEED, dp: 0 },
  ENGINE_LOAD: { label: "Calculated load", unit: "%", get: (v) => v.ENGINE_LOAD, dp: 0 },
  THROTTLE_POS: { label: "Throttle position", unit: "%", get: (v) => v.THROTTLE_POS, dp: 0 },
  COOLANT_TEMP: { label: "Coolant temperature", unit: "temp", get: (v) => v.COOLANT_TEMP, dp: 0 },
  INTAKE_TEMP: { label: "Intake air temperature", unit: "temp", get: (v) => v.INTAKE_TEMP, dp: 0 },
  MAF: { label: "Mass air flow", unit: "g/s", get: (v) => v.MAF, dp: 2 },
  SHORT_FUEL_TRIM_1: { label: "Short fuel trim", unit: "%", get: (v) => v.SHORT_FUEL_TRIM_1, dp: 1 },
  LONG_FUEL_TRIM_1: { label: "Long fuel trim", unit: "%", get: (v) => v.LONG_FUEL_TRIM_1, dp: 1 },
  TIMING_ADVANCE: { label: "Timing advance", unit: "°", get: (v) => v.TIMING_ADVANCE, dp: 1 },
  CONTROL_MODULE_VOLTAGE: { label: "System voltage", unit: "V", get: (v) => v.CONTROL_MODULE_VOLTAGE, dp: 2 },
  FUEL_LEVEL: { label: "Fuel level", unit: "%", get: (v) => v.FUEL_LEVEL, dp: 0 },
};

// A smart-data entry either names a live PID or a Mode 06 test. Both resolve
// to "here is the number, here is the window it should be in".
export function resolveSmart(item, car) {
  const ref = String(item.pid || "");
  if (ref.startsWith("MODE06:")) {
    const mid = ref.slice(7);
    const test = (car.mode06 || []).find((m) => m.mid === mid);
    if (!test) return null;
    return {
      label: item.label || test.name,
      value: test.value,
      display: `${test.value} ${test.unit}`,
      expect: item.expect,
      why: item.why,
      pass: test.pass,
      source: `Mode 06 ${mid}`,
      headroom: test.headroom,
    };
  }
  const meta = PID_META[ref];
  if (!meta) return null;
  const v = meta.get((car.live && car.live.values) || {});
  return {
    label: item.label || meta.label,
    value: v,
    display: v === null || v === undefined ? "—" : `${Number(v).toFixed(meta.dp)}`,
    unitKind: meta.unit,
    expect: item.expect,
    why: item.why,
    pass: null,
    source: `live · ${ref}`,
    pid: ref,
  };
}
