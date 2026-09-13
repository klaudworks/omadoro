const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function makeService() {
    const settings = vm.createContext({});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../model/SettingsModel.js'), 'utf8'), settings);
    const source = fs.readFileSync(path.join(__dirname, '../Service.qml'), 'utf8');
    // Exercise the production save handler without a running Quickshell desktop.
    const handler = source.match(/^    function saveSettings\(draft\): var \{[\s\S]*?^    \}/m);
    assert.ok(handler, 'Service.qml saveSettings handler exists');
    const writes = [];
    let verifications = 0;
    const service = vm.createContext({
        SettingsModel: settings,
        saved: { ...settings.defaults },
        entry: { id: 'klaudworks.omadoro', ...settings.defaults },
        pluginId: 'klaudworks.omadoro',
        settingsIssue: '', saveStatus: '', pendingSave: null,
        // Keep the host snapshot stale until asynchronous confirmation, as can
        // happen when two UI edits arrive before the 500 ms verification timer.
        shell: { updateEntryInline: (_id, value) => { writes.push(value); return true; } },
        verifySave: { restart: () => { verifications++; } }
    });
    vm.runInContext(handler[0].replace('): var', ')'), service);
    return { service, writes, verifications: () => verifications };
}

test('reverting a pending setting writes and verifies the latest value', () => {
    const { service, writes, verifications } = makeService();
    const original = { ...service.saved };
    assert.equal(service.saveSettings({ ...original, lockOnBreak: true }).ok, true);
    const result = service.saveSettings(original);
    assert.equal(result.ok, true);
    assert.equal(result.value.lockOnBreak, false);
    assert.equal(writes.length, 2);
    assert.equal(writes[0].lockOnBreak, true);
    assert.equal(writes[1].lockOnBreak, false);
    assert.equal(service.pendingSave.lockOnBreak, false);
    assert.equal(verifications(), 2);
    assert.equal(service.saveStatus, 'Checking saved settings…');
});

test('unchanged confirmed settings do not trigger a write', () => {
    const { service, writes, verifications } = makeService();
    assert.equal(service.saveSettings({ ...service.saved }).ok, true);
    assert.equal(writes.length, 0);
    assert.equal(verifications(), 0);
    assert.equal(service.pendingSave, null);
    assert.equal(service.saveStatus, 'No changes');
});
