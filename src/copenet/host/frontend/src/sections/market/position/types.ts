export interface HeldPosition {
  symbol: string;
  quantity: number;
  avg_cost: number | null;
  last_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  allocation_pct: number | null;
  price_source: string;
  synced_at: string;
  currency: string | null;
  warnings: string[];
}
export interface PositionFill {
  id: string; side: string; quantity: number; price: number | null;
  filledAt: string; sessionDate: string; priceSource: string;
}
export interface PositionPayload {
  symbol: string; position: HeldPosition | null; syncedAt: string | null;
  fillsSyncedAt: string | null; fills: PositionFill[]; fillCount: number;
  warnings: string[]; historyNote: string;
}
export interface PositionPreferences { visible: boolean; shading: boolean; fills: boolean; cursor: boolean }
