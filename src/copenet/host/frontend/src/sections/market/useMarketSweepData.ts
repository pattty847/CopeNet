// Dashboard/brief readers never acquire data. Scans owns every broad-market run.
import { wsClient } from '../../lib/wsClient';
import { useStoredMarketResource } from './useStoredMarketResource';

const fetchDashboard = () => wsClient.marketDashboard();
const fetchBrief = () => wsClient.marketBriefGet();

export function useMarketDashboard() {
  const resource = useStoredMarketResource(fetchDashboard);
  return { ...resource, dashboard: resource.data };
}

export function useMorningBrief() {
  const resource = useStoredMarketResource(fetchBrief);
  return { ...resource, brief: resource.data };
}
