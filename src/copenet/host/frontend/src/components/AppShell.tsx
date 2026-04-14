import { useEffect } from 'react';
import { Activity, FlaskConical, Layers3, Wrench } from 'lucide-react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import { AgentsPage } from './AgentsPage';
import { ConnectionBanner } from './ConnectionBanner';
import { HomePage } from './HomePage';
import { SectionPage } from './SectionPage';
import { SidebarNav } from './SidebarNav';
import { TopCommandBar } from './TopCommandBar';

function AppSectionContent() {
  const currentSection = useAppStore((state) => state.currentSection);

  if (currentSection === 'home') {
    return <HomePage />;
  }

  if (currentSection === 'agents') {
    return <AgentsPage />;
  }

  if (currentSection === 'workflows') {
    return (
      <SectionPage
        title="Workflows"
        subtitle="Replayable work deserves its own home."
        accent="text-shell-accent"
        heroTitle="Turn repeatable effort into living playbooks."
        heroBody="Workflows are where useful sessions become reusable operations. This is where CopeNet can evolve from one-off prompts into repeatable, inspectable work."
        icon={Layers3}
        cards={[
          {
            title: 'Playbook Drafts',
            body: 'Promising chat sessions that want to become reusable multi-step flows.',
            eyebrow: 'Capture',
          },
          {
            title: 'Recurring Operations',
            body: 'Scheduled work, recurring data pulls, and repeatable operator checklists.',
            eyebrow: 'Repeat',
          },
          {
            title: 'Run Histories',
            body: 'A record of what was executed, when, and which runtime handled it.',
            eyebrow: 'Inspect',
          },
          {
            title: 'Workflow Starters',
            body: 'Templates for turning the next good prompt sequence into something replayable.',
            eyebrow: 'Inspire',
          },
        ]}
      />
    );
  }

  if (currentSection === 'data-tools') {
    return (
      <SectionPage
        title="Data & Tools"
        subtitle="Ground the workspace in real sources, not floating context."
        accent="text-shell-accent"
        heroTitle="Connect knowledge, feeds, and tools into one living context."
        heroBody="This is where files, datasets, knowledge bases, and operator tools become part of the workspace. The point is not just to store them. It is to make them useful."
        icon={Wrench}
        cards={[
          {
            title: 'Knowledge Bases',
            body: 'Curated context that can refresh, evolve, and stay anchored to the workspace.',
            eyebrow: 'Ground',
          },
          {
            title: 'Data Sources',
            body: 'Feed market streams, documents, APIs, and local files into the workbench.',
            eyebrow: 'Ingest',
          },
          {
            title: 'Tool Catalog',
            body: 'Inspectable tool surfaces with safety rules and visible execution history.',
            eyebrow: 'Operate',
          },
          {
            title: 'Workspace Context',
            body: 'Preset combinations of data, prompts, and runtimes for the jobs you repeat.',
            eyebrow: 'Shape',
          },
        ]}
      />
    );
  }

  if (currentSection === 'observability') {
    return (
      <SectionPage
        title="Observability"
        subtitle="Agent work should stay visible enough to debug and trust."
        accent="text-shell-accent"
        heroTitle="Trace the work, not just the answer."
        heroBody="Observability is where runs become legible. Tool blocks, provider drift, trace artifacts, and runtime health all belong here so the operator can understand what really happened."
        icon={Activity}
        cards={[
          {
            title: 'Run Traces',
            body: 'Structured traces that explain tool planning, provider turns, and final outcomes.',
            eyebrow: 'Trace',
          },
          {
            title: 'Tool Blocks',
            body: 'See what was denied, why it was denied, and how models reacted to the boundary.',
            eyebrow: 'Guardrails',
          },
          {
            title: 'System Health',
            body: 'Connection state, provider availability, and runtime drift all in one place.',
            eyebrow: 'Monitor',
          },
          {
            title: 'Debug Artifacts',
            body: 'The eventual home for prompt dumps, comparisons, and provider-specific diagnostics.',
            eyebrow: 'Investigate',
          },
        ]}
      />
    );
  }

  return (
    <SectionPage
      title="Experiments"
      subtitle="Compare, replay, and learn what each runtime actually does."
      accent="text-shell-accent"
      heroTitle="Run the same job across models and see what changes."
      heroBody="Experiments are how CopeNet can become more than a chat surface. Compare providers, inspect tool choices, and turn model behavior into something you can study instead of guess at."
      icon={FlaskConical}
      cards={[
        {
          title: 'Prompt Comparisons',
          body: 'Run one prompt across multiple models and inspect the differences side by side.',
          eyebrow: 'Compare',
        },
        {
          title: 'Tool Use Probes',
          body: 'See which runtimes follow tool instructions, drift, or improvise under pressure.',
          eyebrow: 'Probe',
        },
        {
          title: 'Saved Runs',
          body: 'Keep the best comparisons around so future work can build on them.',
          eyebrow: 'Remember',
        },
        {
          title: 'Ranking Ideas',
          body: 'A future home for synthesis, scoring, and selection workflows across providers.',
          eyebrow: 'Decide',
        },
      ]}
    />
  );
}

export function AppShell() {
  const themeMode = useAppStore((state) => state.themeMode);

  useEffect(() => {
    void wsClient.connect();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
  }, [themeMode]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-shell-bg text-shell-text">
      <div className="absolute inset-0 shell-backdrop pointer-events-none" />
      <div className="relative flex h-full w-full gap-4 p-4">
        <SidebarNav />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[32px] border border-shell-border bg-shell-canvas px-5 pb-5 pt-4 shadow-shell-xl backdrop-blur-sm">
          <ConnectionBanner />
          <div className="flex items-center gap-4 pb-4">
            <TopCommandBar />
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <AppSectionContent />
          </div>
        </div>
      </div>
    </div>
  );
}
