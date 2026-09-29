import { CircleAlert } from 'lucide-react';
import { ProviderLanes } from '../../settings/ProviderLanes';
import { useProviderReadiness } from '../../settings/useProviderReadiness';
import { Card } from './Card';

/** First-run onboarding only. Once any provider is ready this card leaves Home for good;
 *  connecting the second provider, signing out and optional data keys live in Settings. */
export function ProviderSetup() {
  const { loaded, anyReady } = useProviderReadiness();
  // Wait for the catalog: a connected operator should never see onboarding flash on reload.
  if (!loaded || anyReady) return null;

  return (
    <Card title="Choose a model provider to begin" icon={CircleAlert} span={12} className="hd-provider-setup">
      <div className="hd-provider-setup__intro">
        You only need one ready provider. CopeNet keeps sessions and tools local; the selected provider supplies the model.
        Charts, quotes and screeners already work.
      </div>
      <div className="hd-provider-setup__body">
        <ProviderLanes />
      </div>
    </Card>
  );
}
