import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FINANCIAL_SERIES_CACHE_TTL_MS,
  isFinancialSeriesCacheEntryFresh,
} from '../src/sections/market/useFinancialSeries';

test('financial overlay cache expires so prices and newly filed facts can refresh', () => {
  const cachedAt = 1_000_000;
  const entry = { data: null, cachedAt };

  assert.equal(
    isFinancialSeriesCacheEntryFresh(entry, cachedAt + FINANCIAL_SERIES_CACHE_TTL_MS - 1),
    true,
  );
  assert.equal(
    isFinancialSeriesCacheEntryFresh(entry, cachedAt + FINANCIAL_SERIES_CACHE_TTL_MS),
    false,
  );
});
