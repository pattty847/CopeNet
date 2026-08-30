// The "add an indicator" picker.
//
// Same grammar as the financial-series picker it sits beside: a search field over grouped
// rows, no descriptions in the list unless the name genuinely does not carry the meaning.
// Twenty-seven entries is small enough that grouping plus a filter beats any cleverer
// affordance, and an analyst who knows what they want types three letters and hits it.

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { INDICATOR_CATEGORIES } from './types';
import { searchIndicators } from './registry';

export function IndicatorPicker({
  onPick,
  disabled,
  disabledReason,
  atCapacity,
}: {
  onPick: (indicatorId: string) => void;
  disabled?: boolean;
  disabledReason?: string;
  atCapacity?: boolean;
}) {
  const [query, setQuery] = useState('');

  const groups = useMemo(() => {
    const matches = searchIndicators(query);
    return INDICATOR_CATEGORIES
      .map((category) => ({
        ...category,
        entries: matches.filter((definition) => definition.category === category.key),
      }))
      .filter((group) => group.entries.length > 0);
  }, [query]);

  if (disabled) return <p className="tw-pop__note">{disabledReason}</p>;
  if (atCapacity) {
    return <p className="tw-pop__note">Remove an indicator before adding another.</p>;
  }

  return (
    <div className="tw-series-picker__menu">
      <label className="tw-series-picker__search">
        <Search size={12} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search indicators"
          aria-label="Search technical indicators"
          spellCheck={false}
          autoComplete="off"
        />
      </label>
      <div className="tw-series-picker__list">
        {groups.map((group) => (
          <div key={group.key} className="tw-series-picker__group">
            <div className="tw-series-picker__group-label">{group.label}</div>
            {group.entries.map((definition) => (
              <button
                key={definition.id}
                type="button"
                className="tw-series-picker__option tw-ind-option"
                onClick={() => onPick(definition.id)}
                title={definition.description ?? definition.name}
              >
                <span>{definition.name}</span>
                <small>{definition.placement === 'pane' ? 'pane' : 'price'}</small>
              </button>
            ))}
          </div>
        ))}
        {groups.length === 0 && <div className="tw-series-picker__empty">No matching indicator</div>}
      </div>
    </div>
  );
}
