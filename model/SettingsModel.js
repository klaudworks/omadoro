// Shared by QML and the Node fake-clock suite. No runtime imports.
var defaults = {
    workMinutes: 50, breakSeconds: 300, skipPolicy: "allow", skipWaitSeconds: 15,
    autoStart: true, idleThresholdSeconds: 60, warningEnabled: true,
    warningPostponeEnabled: true, lockOnBreak: false, respectIdleInhibitors: true
};
var bounds = { workMinutes: [1, 1440], breakSeconds: [1, 3600],
    skipWaitSeconds: [1, 3600], idleThresholdSeconds: [1, 3600] };

function valid(key, value) {
    if (bounds[key]) return typeof value === "number" && Number.isFinite(value)
        && Number.isInteger(value) && value >= bounds[key][0] && value <= bounds[key][1];
    if (key === "skipPolicy") return ["allow", "wait", "never"].indexOf(value) !== -1;
    return typeof value === "boolean";
}
function normalize(raw) {
    raw = raw || {};
    var value = {}, issues = [];
    Object.keys(defaults).forEach(function(key) {
        value[key] = valid(key, raw[key]) ? raw[key] : defaults[key];
        if (raw[key] !== undefined && !valid(key, raw[key])) issues.push(key);
    });
    return { value: value, issue: issues.length ? "Invalid settings: " + issues.join(", ") + ". Safe defaults applied." : "" };
}
function validate(raw) {
    var value = {}, issues = [];
    Object.keys(defaults).forEach(function(key) {
        var candidate = raw[key];
        if (bounds[key] && typeof candidate === "string" && /^\d+$/.test(candidate.trim()))
            candidate = Number(candidate.trim());
        if (!valid(key, candidate)) issues.push(key);
        value[key] = candidate;
    });
    return { ok: issues.length === 0, value: value, error: issues.length ? "Check " + issues.join(", ") : "" };
}
function merge(entry, value) {
    var merged = Object.assign({}, entry || {}, value);
    delete merged.meetingDetectionEnabled;
    delete merged.meetingGraceSeconds;
    return merged;
}
function minutesToSeconds(text) {
    if (typeof text !== "string" || !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())) return NaN;
    var seconds = Number(text.trim()) * 60;
    return Number.isFinite(seconds) && Math.abs(seconds - Math.round(seconds)) < 0.0000001
        ? Math.round(seconds) : NaN;
}
