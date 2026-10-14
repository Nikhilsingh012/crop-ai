import test from 'node:test';
import assert from 'node:assert/strict';
import { marketViewState } from '../src/marketViewState.js';

test('market displays loading, API error, empty and ready states', () => {
  assert.equal(marketViewState({ loading: true, error: false, items: [] }), 'loading');
  assert.equal(marketViewState({ loading: false, error: true, items: [] }), 'error');
  assert.equal(marketViewState({ loading: false, error: false, items: [] }), 'empty');
  assert.equal(marketViewState({ loading: false, error: false, items: [{ id: 1 }] }), 'ready');
});
