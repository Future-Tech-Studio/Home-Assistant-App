const fs = require('node:fs');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const source = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const html = source.replace('      async function watchLiveStateRevisions()', '      window.testRoomStateRefresh = scheduleLiveStateRefresh;\n      async function watchLiveStateRevisions()');
  const bedroomCatalog = JSON.parse(execFileSync(process.env.FHT_PYTHON || 'python3', ['-B', 'tests/action_catalog_fixture.py'], { encoding: 'utf8' }));
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const requests = [];
      const saves = [];
      const errors = [];
      let failUnassigned = true;
      let failSave = false;
      const aliases = { 'Bedroom 2': 'Bailey’s Bedoom', 'Bedroom 6': "Chloe's Bedroom", Kitchen: 'Kitchen Display Name' };
      const entities = [
        { entity_id: 'binary_sensor.pantry_door', domain: 'binary_sensor', friendly_name: 'Pantry Door Sensor', area: 'Pantry', state: 'off' },
        { entity_id: 'binary_sensor.bedroom_window', domain: 'binary_sensor', friendly_name: 'Bedroom 6 Window Sensor', area: 'Bedroom 6', state: 'on' },
        { entity_id: 'binary_sensor.unassigned_door', domain: 'binary_sensor', friendly_name: 'Garage Door Sensor', area: '', state: 'off' },
        ...[1, 2, 3].map(number => ({ entity_id: `switch.bedroom_2_${number}`, domain: 'switch', friendly_name: `Bedroom 2 Switch ${number}`, original_name: `Switch ${number}`, device_name: 'Bedroom 2 Switch', device_id: 'bedroom-wall', area: 'Bedroom 2', state: 'off' })),
        { entity_id: 'switch.dining_room_switch', domain: 'switch', friendly_name: 'Dining Room Switch', device_name: 'Dining Room Switch', area: 'Dining Room', state: 'off' },
        ...[1, 2, 3].map(number => ({ entity_id: `switch.kitchen_${number}`, domain: 'switch', friendly_name: `Kitchen Switch ${number}`, original_name: `Switch ${number}`, device_name: 'Kitchen Switch', device_id: 'wall', area: 'Kitchen', state: 'off', hidden_by: number === 3 ? 'integration' : null })),
        ...['up', 'down', 'config'].map(name => ({ entity_id: `event.kitchen_button_${name}`, domain: 'event', friendly_name: `Kitchen Switch Button ${name}`, device_name: 'Kitchen Switch', device_id: 'wall', area: 'Kitchen', event_types: ['multi_press_1', 'multi_press_2', 'long_press', 'long_release'] })),
        { entity_id: 'switch.floor_fan', domain: 'switch', friendly_name: 'Bedroom 6 Switch', device_name: "Chloe's Floor Fan", device_id: 'fan', area: 'Bedroom 6', state: 'on' },
        { entity_id: 'event.fan_button_up', domain: 'event', device_name: "Chloe's Floor Fan", device_id: 'fan', area: 'Bedroom 6', event_types: ['multi_press_1'] },
        { entity_id: 'switch.kitchen_camera', domain: 'switch', device_name: 'Kitchen Camera Switch', area: 'Kitchen', state: 'on' },
        { entity_id: 'light.kitchen_indicator', domain: 'light', device_name: 'Kitchen Switch RGB Indicator', area: 'Kitchen', state: 'on' },
        { entity_id: 'switch.office', domain: 'switch', device_name: 'Office Switch', friendly_name: 'Office Switch', area: 'Office', state: 'off' },
      ];
      const action = 'light_group:light.fht_pantry_all_lights';
      const pantryId = 'door:binary_sensor.pantry_door';
      const dayId = `${pantryId}|day`;
      const nightId = `${pantryId}|night`;
      const doorModes = [{ id: 'day', label: 'Day' }, { id: 'night', label: 'Night' }, { id: 'sleep', label: 'Whole Home Sleep' }];
      const assignments = {
        'switch.dining_room_switch': ['light_group:light.dining_room_lights'],
        'switch.bedroom_2_2': ['light_group:light.bedroom_2_fan_lights'],
        'switch.bedroom_2_3': ['light_group:light.fht_bedroom_2_all_lights', 'light_group:light.bedroom_2_all_lights', 'light_group:light.bedroom_2_fan_lights'],
        'switch.kitchen_3': [action],
        'event.kitchen_button_up|long_press': [action],
        [pantryId]: [action],
      };
      const settings = {
        [dayId]: { enabled: true, brightness_pct: 80, color_mode: 'kelvin', color_kelvin: 3000 },
        [nightId]: { enabled: true, brightness_pct: 25, color_mode: 'adaptive' },
      };
      const catalog = {
        ...bedroomCatalog,
        light_groups: [...bedroomCatalog.light_groups, { entity_id: 'light.fht_pantry_all_lights', domain: 'light', friendly_name: 'Pantry All Lights', area: 'Pantry' }],
        individual_lights: [...bedroomCatalog.individual_lights, ...[1, 2].map(number => ({ entity_id: `light.pantry_${number}`, domain: 'light', friendly_name: `Pantry Light ${number}`, area: 'Pantry' }))],
      };
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        const pathname = url.pathname;
        requests.push(pathname + url.search);
        if (pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        const payload = { ok: true, entities: [], settings: {}, rooms: [], floors: [], changed: false };
        if (pathname === '/api/room-controls') {
          const kind = url.searchParams.get('kind');
          const room = url.searchParams.get('room');
          if (room === '' && failUnassigned) {
            failUnassigned = false;
            return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'Test unavailable room' }) });
          }
          payload.entities = entities.filter(entity => (kind === 'doors' ? entity.domain === 'binary_sensor' : ['switch', 'event'].includes(entity.domain)) && (room === null || entity.area === room))
            .map(entity => ({ ...entity, original_area: entity.area, area: aliases[entity.area] || entity.area }));
          if (room === null) payload.aliases = aliases;
          else Object.assign(payload, { room, display_name: aliases[room] || room || 'Unassigned', catalog_revision: 'one', door_sensors: kind === 'doors' ? payload.entities : [], door_mode_options: kind === 'doors' ? doorModes : [], control_settings: { action_assignments: assignments, action_settings: settings } });
        }
        if (pathname === '/api/home-configurator/catalog') Object.assign(payload, { revision: 'one', action_catalog: catalog });
        if (pathname === '/api/home-configurator/index') payload.floors = [{ name: 'First Floor', rooms: [{ name: 'Kitchen' }, { name: 'Pantry' }] }];
        if (pathname === '/api/home-configurator/room') Object.assign(payload, { room: 'Kitchen', entities: entities.filter(entity => entity.area === 'Kitchen'), door_sensors: [entities[0]] });
        if (request.method() === 'POST') {
          const data = request.postDataJSON();
          saves.push({ pathname, ...data });
          if (failSave) {
            failSave = false;
            return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'Test save failure' }) });
          }
          if (pathname === '/api/switch-light-groups') {
            assignments[data.assignment_id] = data.actions;
            if (data.action_setting) settings[data.assignment_id] = data.action_setting;
            for (const [mode, setting] of Object.entries(data.door_modes || {})) settings[`${data.assignment_id}|${mode}`] = setting;
          }
        }
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
      });
      const navigate = view => page.locator(`[data-view="${view}"]`).evaluate(button => button.click());
      const selectActions = async (selector, values) => {
        const picker = page.locator(selector).locator('..');
        await picker.locator(':scope > summary').click();
        if (!values.length) {
          await picker.locator('.action-multi-clear').click();
          await page.waitForFunction(selector => !document.querySelector(selector).disabled, selector);
        } else {
          const changes = await picker.locator('[data-action-option]').evaluateAll((checkboxes, selectedValues) => checkboxes.filter(checkbox => checkbox.value && checkbox.checked !== selectedValues.includes(checkbox.value)).map(checkbox => checkbox.value), values);
          for (const value of changes) {
            await picker.locator(`[data-action-option][value="${value}"]`).click();
            await page.waitForFunction(selector => !document.querySelector(selector).disabled, selector);
          }
        }
        await picker.locator(':scope > summary').click();
      };
      await page.goto('http://fht.test/');
      await page.waitForSelector('.page-actions-primary #doors-toolbar', { state: 'attached' });
      assert.equal(requests.some(path => path.startsWith('/api/room-controls')), false);
      await navigate('doors');
      await page.waitForSelector('#doors-list [data-control-room]');
      assert.deepEqual(await page.locator('#doors-list h2').allTextContents(), ["Chloe's Bedroom", 'Pantry', 'Unassigned']);
      assert.equal(requests.some(path => path.startsWith('/api/room-controls') && path.includes('&room=')), false);
      assert.equal(await page.locator('.page-actions-primary #doors-toolbar').isVisible(), true);
      // Every door, the Pantry included, uses the same mode rows with a tone picker per mode.
      const settled = async (check, label) => { for (let tries = 0; tries < 50 && !check(); tries += 1) await page.waitForTimeout(100); assert.ok(check(), label); };
      await page.locator('[data-control-room="Pantry"] > summary').click();
      const pantryCard = `[data-door-presence-card="${pantryId}"]`;
      const day = `${pantryCard} [data-door-rule="day"]`;
      const night = `${pantryCard} [data-door-rule="night"]`;
      await page.waitForSelector(`${day} .door-rule-brightness`);
      assert.equal(await page.locator(`${pantryCard} [data-door-rule]`).count(), 3);
      assert.equal(await page.locator(`${day} .door-rule-brightness`).inputValue(), '80');
      assert.equal(await page.locator(`${night} .door-rule-brightness`).inputValue(), '25');
      assert.equal(await page.locator(`${day} .presence-mode-tone`).inputValue(), 'custom', 'A saved 3000 K tone shows as Custom');
      assert.equal(await page.locator(`${night} .presence-mode-tone`).inputValue(), 'adaptive');
      assert.equal(await page.locator('#doors-list .home-configurator-door-actions').count(), 0);
      assert.equal(requests.filter(path => path.startsWith('/api/room-controls') && path.includes('&room=')).length, 1);
      const originalEditor = await page.locator(`${day} .door-rule-brightness`).elementHandle();
      await page.locator(`${day} .door-rule-brightness`).evaluate(input => { input.value = '41'; input.dispatchEvent(new Event('input', { bubbles: true })); });
      entities[0].state = 'on';
      await page.evaluate(() => window.testRoomStateRefresh(['security'], ['Pantry']));
      await page.waitForTimeout(400);
      assert.equal(await originalEditor.evaluate(input => input.isConnected && input.value === '41'), true, 'A live refresh keeps the edited row');
      assert.equal(await page.locator('#doors-list [data-control-room="Pantry"]').getAttribute('open'), '');
      await page.locator(`${day} .door-rule-brightness`).dispatchEvent('change');
      await settled(() => settings[dayId]?.brightness_pct === 41, 'Brightness saves with the door card');
      assert.equal(settings[dayId].color_mode, 'kelvin');
      assert.equal(settings[dayId].color_kelvin, 3000);
      assert.deepEqual(assignments[pantryId], [action]);
      await page.selectOption(`${day} .presence-mode-tone`, 'adaptive');
      await settled(() => settings[dayId]?.color_mode === 'adaptive', 'The tone picker saves color_mode');
      await page.selectOption(`${day} .presence-mode-tone`, '2700');
      await settled(() => settings[dayId]?.color_mode === 'kelvin' && settings[dayId]?.color_kelvin === 2700, 'A preset saves its Kelvin');
      await selectActions(`${pantryCard} .door-action-group-select`, [action, 'light_group:light.pantry_1']);
      await settled(() => assignments[pantryId]?.length === 2, 'Door actions save');
      assert.deepEqual(assignments[pantryId], [action, 'light_group:light.pantry_1']);
      await page.locator('[data-control-room="Bedroom 6"] > summary').click();
      const windowCard = '[data-door-presence-card="door:binary_sensor.bedroom_window"]';
      await page.waitForSelector(`${windowCard} .door-action-group-select`, { state: 'attached' });
      await selectActions(`${windowCard} .door-action-group-select`, [action]);
      await settled(() => assignments['door:binary_sensor.bedroom_window']?.length === 1, 'Bedroom door actions save');
      assert.deepEqual(assignments['door:binary_sensor.bedroom_window'], [action]);
      await page.locator('[data-control-room=""] > summary').click();
      await page.waitForFunction(() => document.querySelector('[data-control-room=""] .room-controls-body').textContent.includes('Close and reopen'));
      await page.locator('[data-control-room=""] > summary').click();
      await page.locator('[data-control-room=""] > summary').click();
      await page.waitForSelector('[data-door-presence-card="door:binary_sensor.unassigned_door"]');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Doors overflow at ${width}px`);
      if (process.env.FHT_SCREENSHOTS) await page.screenshot({ path: `/tmp/fht-doors-${width}.png` });
      await navigate('switches');
      await page.waitForSelector('#switches-list [data-control-room]');
      assert.deepEqual(await page.locator('#switches-list h2').allTextContents(), ['Bailey’s Bedoom', 'Dining Room', 'Kitchen Display Name', 'Office']);
      assert.equal(await page.locator('#doors-toolbar').isVisible(), false);
      assert.equal(await page.locator('.page-actions-primary #switches-toolbar').isVisible(), true);
      await page.locator('#switches-list [data-control-room="Bedroom 2"] > summary').click();
      const bedroomSelect = number => `#switches-list select[data-assignment-id="switch.bedroom_2_${number}"]`;
      await page.waitForSelector(bedroomSelect(1), { state: 'attached' });
      const localNames = await page.locator(`${bedroomSelect(1)} optgroup`).first().locator('option').evaluateAll(options => options.map(option => option.dataset.actionName));
      assert.deepEqual(localNames, ['All Lights', 'Closet Lights', 'Fan Lights', 'Headboard Light']);
      assert.equal(await page.locator(`${bedroomSelect(2)} optgroup[label="Unavailable Saved Targets"]`).count(), 0);
      assert.equal(await page.locator(`${bedroomSelect(3)} option:checked`).count(), 2);
      const fan = 'light_group:light.fht_bedroom_2_fan_lights';
      const allLights = 'light_group:light.fht_bedroom_2_all_lights';
      const closet = 'light_group:light.fht_bedroom_2_closet_lights';
      await selectActions(bedroomSelect(1), [allLights, fan]);
      assert.deepEqual(assignments['switch.bedroom_2_1'], [allLights, fan]);
      await selectActions(bedroomSelect(2), [closet, fan]);
      assert.deepEqual(assignments['switch.bedroom_2_2'], [closet, 'light_group:light.bedroom_2_fan_lights']);
      await selectActions(bedroomSelect(3), [allLights, closet, fan]);
      assert.deepEqual(assignments['switch.bedroom_2_3'], [allLights, 'light_group:light.bedroom_2_all_lights', closet, 'light_group:light.bedroom_2_fan_lights']);
      await selectActions(bedroomSelect(2), []);
      assert.deepEqual(assignments['switch.bedroom_2_2'], []);
      await selectActions(bedroomSelect(2), [fan]);
      assert.deepEqual(assignments['switch.bedroom_2_2'], [fan]);
      if (process.env.FHT_SCREENSHOTS) {
        await page.locator(bedroomSelect(1)).locator('..').locator(':scope > summary').click();
        await page.screenshot({ path: `/tmp/fht-action-groups-${width}.png` });
        await page.locator(bedroomSelect(1)).locator('..').locator(':scope > summary').click();
      }
      await page.locator('#switches-list [data-control-room="Bedroom 2"] > summary').click();
      await page.locator('#switches-list [data-control-room="Dining Room"] > summary').click();
      const diningSelect = '#switches-list select[data-assignment-id="switch.dining_room_switch"]';
      await page.waitForSelector(diningSelect, { state: 'attached' });
      assert.deepEqual(await page.locator(`${diningSelect} optgroup`).first().locator('option').evaluateAll(options => options.map(option => option.dataset.actionName)), ['All Lights']);
      assert.equal(await page.locator(`${diningSelect} option:checked`).count(), 1);
      const diningAll = 'light_group:light.fht_dining_room_all_lights';
      await selectActions(diningSelect, [diningAll, action]);
      assert.deepEqual(assignments['switch.dining_room_switch'], ['light_group:light.dining_room_lights', action]);
      await selectActions(diningSelect, []);
      await selectActions(diningSelect, [diningAll]);
      assert.deepEqual(assignments['switch.dining_room_switch'], [diningAll]);
      await page.locator('#switches-list [data-control-room="Dining Room"] > summary').click();
      await page.locator('#switches-list [data-control-room="Kitchen"] > summary').click();
      await page.waitForSelector('#switches-list [data-control-room="Kitchen"] .control-device-card');
      assert.equal(await page.locator('#switches-list [data-control-room="Kitchen"] .control-status-button').count(), 3);
      assert.deepEqual(await page.locator('#switches-list [data-control-room="Kitchen"] .control-channel-name').allTextContents(), ['Button 1', 'Button 2', 'Button 3']);
      assert.equal(await page.locator('#switches-list .inovelli-button-card').count(), 3);
      const third = '#switches-list select[data-assignment-id="switch.kitchen_3"]';
      assert.deepEqual(await page.locator(third).evaluate(select => [...select.selectedOptions].map(option => option.value)), [action]);
      const eventSelect = '#switches-list select[data-assignment-id="event.kitchen_button_up|long_press"]';
      await selectActions(eventSelect, []);
      assert.deepEqual(assignments['event.kitchen_button_up|long_press'], []);
      failSave = true;
      await selectActions(third, []);
      assert.match(await page.locator('#switches-state').textContent(), /Test save failure/);
      await selectActions(third, [action]);
      assert.match(await page.locator('#switches-state').textContent(), /saved/);
      await page.locator('[data-control-entity-id="switch.kitchen_3"]').click();
      await page.waitForFunction(() => !document.querySelector('[data-control-entity-id="switch.kitchen_3"]').disabled);
      assert.equal(saves.at(-1).pathname, '/api/controls/toggle');
      assert.equal(saves.at(-1).entity_id, 'switch.kitchen_3');
      entities.find(entity => entity.entity_id === 'switch.kitchen_1').state = 'on';
      const originalSelect = await page.locator(third).elementHandle();
      await page.evaluate(() => window.testRoomStateRefresh(['controls'], ['Kitchen']));
      await page.waitForSelector('[data-control-entity-id="switch.kitchen_1"] .group-status.on');
      assert.equal(await originalSelect.evaluate(select => select.isConnected), true);
      assert.equal(requests.some(path => path === '/api/room-controls?kind=switches&room=Office'), false);
      assert.equal(requests.filter(path => path === '/api/home-configurator/catalog').length, 1);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      assert.ok(overflow <= 1, `Page overflow at ${width}px: ${overflow}`);
      if (process.env.FHT_SCREENSHOTS) await page.screenshot({ path: `/tmp/fht-switches-${width}.png` });
      for (let index = entities.length - 1; index >= 0; index -= 1) {
        if (/^switch\.kitchen_\d+$/.test(entities[index].entity_id)) entities.splice(index, 1);
      }
      await page.reload();
      await page.waitForSelector('.page-actions-primary #switches-toolbar', { state: 'attached' });
      await navigate('switches');
      await page.locator('#switches-list [data-control-room="Kitchen"] > summary').click();
      await page.waitForSelector('#switches-list .inovelli-button-card');
      assert.equal(await page.locator('#switches-list .inovelli-button-card').count(), 3);
      assert.equal(await page.locator('#switches-list [data-control-room="Kitchen"] .control-status-button').count(), 0);
      assert.equal(await page.locator('#switches-list [data-control-room="Bedroom 6"]').count(), 0);
      await selectActions(eventSelect, [action]);
      assert.deepEqual(assignments['event.kitchen_button_up|long_press'], [action]);
      await navigate('rooms');
      await page.waitForSelector('#home-floor-picker:not(:disabled)');
      await page.locator('#room-configurator-list [data-room="Kitchen"] > summary').evaluate(summary => summary.click());
      await page.waitForSelector('#room-configurator-list .room-alias-input');
      assert.equal(await page.locator('#room-configurator-list .home-configurator-controls, #room-configurator-list .home-configurator-door-actions').count(), 0);
      assert.equal(await page.locator('#switches-toolbar').isVisible(), false);
      const settingsLabels = await page.locator('#settings-submenu > button').allTextContents();
      assert.deepEqual(settingsLabels, [...settingsLabels].sort((left, right) => left.localeCompare(right)));
      assert.deepEqual(errors, []);
      console.log(`Doors and Switches: lazy loading, existing assignments, mode settings, events, live status, and navigation passed at ${width}px`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
