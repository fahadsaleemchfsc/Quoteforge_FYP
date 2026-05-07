import { useState, useEffect } from 'react';
import { Plus, Sparkles, Play, Edit3, X, Save } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { AI_PROMPTS } from '@/constants/mockData';
import api from '@/services/api';
import clsx from 'clsx';

export default function Prompts() {
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [prompts, setPrompts] = useState(AI_PROMPTS);
  const [testOutput, setTestOutput] = useState('');
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.get('/prompts').then(res => setPrompts(res.data)).catch(() => {});
  }, []);

  const handleTest = async (promptId) => {
    setTesting(true);
    setTestOutput('');
    try {
      const res = await api.post(`/prompts/${promptId}/test`, {});
      setTestOutput(res.data.output || 'No output generated');
    } catch {
      setTestOutput('Test failed — check backend connection');
    }
    setTesting(false);
  };

  const handleSave = async (prompt) => {
    try {
      await api.put(`/prompts/${prompt.id}`, {
        name: prompt.name,
        section: prompt.section,
        prompt_text: prompt.prompt_text,
      });
      const res = await api.get('/prompts');
      setPrompts(res.data);
    } catch {}
  };

  return (
    <div className="page-enter">
      {/* ─── Header ──────────────────────────── */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-2.5 items-center">
          <div className="px-3.5 py-1.5 rounded bg-brand-50 text-sm font-semibold text-brand-700 inline-flex items-center gap-1.5">
            <Sparkles size={14} />
            {prompts.filter((p) => p.status === 'active').length} Active Prompts
          </div>
          <div className="px-3.5 py-1.5 rounded bg-warning-muted text-sm font-semibold text-warning">
            {prompts.filter((p) => p.status === 'testing').length} In Testing
          </div>
        </div>
        <button className="btn-primary">
          <Plus size={18} /> New Prompt
        </button>
      </div>

      {/* ─── Content ─────────────────────────── */}
      <div className={clsx('grid gap-4', selectedPrompt ? 'grid-cols-2' : 'grid-cols-1')}>
        {/* Prompt List */}
        <div className="flex flex-col gap-2.5">
          {prompts.map((prompt, i) => (
            <div
              key={prompt.id}
              onClick={() => setSelectedPrompt(prompt)}
              className={clsx(
                'card p-4 cursor-pointer  transition-all',
                selectedPrompt?.id === prompt.id
                  ? 'border-brand-500 ring-2 ring-brand-500/15'
                  : 'hover:border-brand-200'
              )}
              
            >
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h4 className="text-[13px] font-bold text-text-primary">{prompt.name}</h4>
                  <div className="flex gap-2.5 mt-1.5 text-xs text-text-secondary">
                    <span>{prompt.section}</span>
                    <span className="text-text-muted">•</span>
                    <span>{prompt.version}</span>
                    <span className="text-text-muted">•</span>
                    <span>{prompt.tokens} tokens</span>
                  </div>
                </div>
                <StatusBadge status={prompt.status} />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-text-muted">Last used: {prompt.lastUsed}</span>
                <div className="flex gap-1.5">
                  <button onClick={(e) => e.stopPropagation()} className="icon-btn w-[30px] h-[30px]">
                    <Play size={13} className="text-success" />
                  </button>
                  <button onClick={(e) => e.stopPropagation()} className="icon-btn w-[30px] h-[30px]">
                    <Edit3 size={13} className="text-text-secondary" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Editor Panel */}
        {selectedPrompt && (
          <div className="card p-5 sticky top-[72px] self-start">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-[13px] font-bold text-text-primary">Prompt Editor</h3>
              <button onClick={() => setSelectedPrompt(null)} className="icon-btn">
                <X size={16} className="text-text-secondary" />
              </button>
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-text-primary block mb-1.5">Prompt Name</label>
              <input defaultValue={selectedPrompt.name} className="input-field" />
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-text-primary block mb-1.5">Section Target</label>
              <select defaultValue={selectedPrompt.section} className="input-field bg-white">
                {['Cover Letter', 'Scope', 'Pricing', 'Deliverables', 'Terms', 'Summary'].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-text-primary block mb-1.5">Prompt Template</label>
              <textarea
                rows={10}
                defaultValue={selectedPrompt.prompt_text || `You are a professional sales document writer. Generate a ${selectedPrompt.section.toLowerCase()} section for the proposal.\n\nContext:\n- Client: {{client_name}}\n- Deal: {{deal_name}}\n- Amount: {{deal_amount}}\n- Products: {{line_items}}\n\nEnsure the content is:\n1. Professional and brand-consistent\n2. Accurate to the deal data\n\nOutput format: Structured text ready for document rendering.`}
                className="input-field font-mono text-sm resize-y leading-relaxed"
                onChange={(e) => setSelectedPrompt(prev => ({ ...prev, prompt_text: e.target.value }))}
              />
            </div>

            {testOutput && (
              <div className="mb-4 p-3 bg-subtle rounded border border-border max-h-48 overflow-y-auto">
                <label className="text-xs font-semibold text-text-secondary block mb-1">Test Output</label>
                <pre className="text-xs text-text-primary whitespace-pre-wrap">{testOutput}</pre>
              </div>
            )}

            <div className="flex gap-2.5">
              <button className="btn-primary flex-1 justify-center" onClick={() => handleSave(selectedPrompt)}>
                <Save size={16} /> Save Changes
              </button>
              <button className="btn-secondary" onClick={() => handleTest(selectedPrompt.id)} disabled={testing}>
                <Play size={16} /> {testing ? 'Testing...' : 'Test'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
