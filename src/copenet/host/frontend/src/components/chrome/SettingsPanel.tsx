import { Settings } from 'lucide-react';
import { GatewayTokenForm } from '../settings/GatewayTokenForm';
import { IntegrationList } from '../settings/IntegrationList';
import { ProviderLanes } from '../settings/ProviderLanes';
import { ChromeDrawer, ChromeSection } from './ChromeDrawer';

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  return (
    <ChromeDrawer eyebrow="CopeNet" title="Settings" icon={Settings} onClose={onClose}>
      <ChromeSection title="Model providers" hint="One ready provider is enough to chat. Connect both to use Fleet rooms.">
        <ProviderLanes columns={1} />
      </ChromeSection>
      <ChromeSection
        title="Data integrations"
        hint="All optional. Add a key to .env (or .copenet.env) and restart CopeNet. Values never reach the browser."
      >
        <IntegrationList />
      </ChromeSection>
      <ChromeSection title="Gateway token" hint="The token this browser uses to reach the host.">
        <GatewayTokenForm />
      </ChromeSection>
    </ChromeDrawer>
  );
}
