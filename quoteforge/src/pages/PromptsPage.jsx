import { useState } from 'react';
import { Plus, Sparkles, X, Play, Edit3, Save } from 'lucide-react';
import { StatusBadge } from '@components/common';
import { aiPrompts } from '@data/mockData';
import { PROMPT_SECTIONS } from '@utils/constants';
import { cn } from '@utils/helpers';

export default function PromptsPage() {
  const [selectedPrompt, setSelectedPrompt] = useState(null);

  return (
    <div className="page-enter">
      {/* ─── Header Badges ─── */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex gap-3 items-center">
          <div className="badge bg-brand-50 text-brand-700 font-semibold px-3.5 py-1.5">
            <Sparkles size={14} /> {aiPrompts.filter((p) => p.status === 'active').length} Active Prompts
          </div>
          <div className="badge bg-amber-100 text-amber-800 font-semibold px-3.5 py-1.5">
            {aiPrompts.filter((p) => p.status === 'testing').length} In Testing
          </div>
        </div>
        <button className="btn-primary"><Plus size={18} /> New Prompt</button>
      </div>

      {/* ─── Layout: List + Editor ─── */}
      <div className={cn('grid gap-5', selectedPrompt ? 'grid-cols-2' : 'grid-cols-1')}>
        {/* Prompt List */}
        <div className="flex flex-col gap-3">
          {aiPrompts.map((prompt) => (
            <div
              key={prompt.id}
              onClick={() => setSelectedPrompt(prompt)}
              className={cn(
                'card cursor-pointer transition-all',
                selectedPrompt?.id === prompt.id
                  ? 'border-brand-500 ring-2 ring-brand-500/10'
                  : 'hover:border-brand-200'
              )}
            >
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h4 className="text-[15px] font-bold text-gray-900">{prompt.name}</h4>
                  <div className="flex gap-3 mt-1.5 text-xs text-gray-500">
                    <span>{prompt.section}</span>
                    <span className="text-gray-300">•</span>
                    <span>{prompt.version}</span>
                    <span className="text-gray-300">•</span>
                    <span>{prompt.tokens} tokens</span>
                  </div>
                </div>
                <StatusBadge status={prompt.status} />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-400">Last used: {prompt.lastUsed}</span>
                <div className="flex gap-1.5">
                  <button onClick={(e) => e.stopPropagation()} className="btn-ghost w-[30px] h-[30px]">
                    <Play size={13} className="text-emerald-500" />
                  </button>
                  <button onClick={(e) => e.stopPropagation()} className="btn-ghost w-[30px] h-[30px]">
                    <Edit3 size={13} className="text-gray-500" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Editor Panel */}
        {selectedPrompt && (
          <div className="card sticky top-24 self-start animate-slide-in-right">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-lg font-bold text-gray-900">Prompt Editor</h3>
              <button onClick={() => setSelectedPrompt(null)} className="btn-ghost">
                <X size={16} className="text-gray-500" />
              </button>
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-gray-700 block mb-1.5">Prompt Name</label>
              <input defaultValue={selectedPrompt.name} className="input" />
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-gray-700 block mb-1.5">Section Target</label>
              <select defaultValue={selectedPrompt.section} className="input bg-white">
                {PROMPT_SECTIONS.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-gray-700 block mb-1.5">Prompt Template</label>
              <textarea
                defaultValue={`You are a professional sales document writer. Generate a ${selectedPrompt.section.toLowerCase()} section for the proposal.\n\nContext:\n- Client: {{client_name}}\n- Deal: {{deal_name}}\n- Amount: {{deal_amount}}\n- Products: {{line_items}}\n\nEnsure the content is:\n1. Professional and brand-consistent\n2. Accurate to the deal data\n3. Compliant with {{compliance_framework}}\n\nOutput format: Structured text ready for document rendering.`}
                className="input h-[200px] resize-y font-mono text-sm leading-relaxed"
              />
            </div>

            <div className="flex gap-2.5">
              <button className="btn-primary flex-1 justify-center"><Save size={16} /> Save Changes</button>
              <button className="btn-secondary"><Play size={16} /> Test</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
