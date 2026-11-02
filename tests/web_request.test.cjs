const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const { webcrypto } = require('node:crypto');

// Load the actual browser entry point. Keep the initial example fetch pending;
// these checks exercise submission IDs without a DOM library or network.
function browser(storage = new Map()) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      value: '', style: {}, listeners: {},
      addEventListener(name, callback) { this.listeners[name] = callback; },
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    crypto: webcrypto,
    sessionStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    document: {
      documentElement: { style: { setProperty() {} } },
      body: { classList: { toggle() {} } },
      getElementById: element,
      querySelectorAll: () => [],
    },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(fs.readFileSync('web/app.js', 'utf8'), context);
  return {
    submit: fields => { context.fields = fields; return vm.runInContext('taskRequest(fields)', context); },
    newTask: () => element('new-task').listeners.click(),
  };
}

const fields = { theme: '字幕活动', budget: 10, deadline: '2026-11-03T10:00:00Z', mode: 'mock' };

test('retries and page reload reuse the same task ID', () => {
  const storage = new Map();
  const app = browser(storage);
  const first = app.submit(fields);
  assert.equal(app.submit({ ...fields }).request_id, first.request_id);
  assert.equal(browser(storage).submit(fields).request_id, first.request_id);
});

test('changed input or explicit new task gets a different ID', () => {
  const app = browser();
  const first = app.submit(fields);
  const changed = app.submit({ ...fields, budget: 20 });
  assert.notEqual(changed.request_id, first.request_id);
  app.newTask();
  assert.notEqual(app.submit({ ...fields, budget: 20 }).request_id, changed.request_id);
});

test('switching to the real model starts a separate task', () => {
  const app = browser();
  assert.notEqual(app.submit(fields).request_id, app.submit({ ...fields, mode: 'online' }).request_id);
});
