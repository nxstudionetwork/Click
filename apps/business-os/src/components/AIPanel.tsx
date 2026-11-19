import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import type { OSAIAnswer } from '@click/api';
import { api, apiMessage } from '../lib/api';
import { Drawer } from './ui';

type Msg = { role: 'me' | 'ai'; text: string; answer?: OSAIAnswer };
const SUGGESTIONS = ['What’s waiting for my approval?', 'Show my overdue tasks', 'How is the business doing?', 'Find Priya'];

/** Click Business AI. Answers only through tools that run with the signed-in person’s own permissions. */
export function AIPanel({ onClose }: { onClose: () => void }) {
  const status = useQuery({ queryKey: ['os', 'ai'], queryFn: api.ai.status });
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: api.ai.ask,
    onSuccess: (answer) => setMsgs((m) => [...m, { role: 'ai', text: answer.answer, answer }]),
    onError: (e) => setMsgs((m) => [...m, { role: 'ai', text: apiMessage(e) }]),
  });
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [msgs]);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || ask.isPending) return;
    setMsgs((m) => [...m, { role: 'me', text: t }]);
    setQ('');
    ask.mutate(t);
  };

  return (
    <Drawer title={<span className="row"><Icon name="sparkle" size={18} />Click Business AI</span>} onClose={onClose} footer={
      <form className="row grow" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <input className="field__input grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your work…" aria-label="Ask Click Business AI"
               disabled={!status.data?.available} />
        <Button type="submit" loading={ask.isPending} disabled={!q.trim() || !status.data?.available}>Ask</Button>
      </form>
    }>
      <p className="xs muted">Answers come only from Business OS data you’re allowed to see. It never guesses figures.</p>
      {status.data && !status.data.available && <div className="alert alert--warning">Business AI isn’t available for your account or this environment.</div>}
      {msgs.length === 0 && status.data?.available && (
        <div className="stack">
          <span className="small muted">Try:</span>
          <div className="ai-suggest">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
          <span className="xs muted">Available to you: {status.data.tools.map((t) => t.label).join(', ')}</span>
        </div>
      )}
      <div className="stack" style={{ gap: 8 }}>
        {msgs.map((m, i) => (
          <div key={i} className={`ai-msg ${m.role === 'me' ? 'ai-msg--me' : m.answer?.denied ? 'ai-msg--ai ai-msg--denied' : 'ai-msg--ai'}`}>
            {m.text}
            {m.answer?.items && m.answer.items.length > 0 && (
              <ul className="list" style={{ marginTop: 8 }}>
                {m.answer.items.map((it, j) => (
                  <li key={j}><Link to={it.path} onClick={onClose} className="small">{it.title}</Link> <span className="xs muted">{it.subtitle}</span></li>
                ))}
              </ul>
            )}
            {m.answer?.note && <p className="xs muted" style={{ marginTop: 6 }}>{m.answer.note}</p>}
          </div>
        ))}
        {ask.isPending && <div className="ai-msg ai-msg--ai muted">Looking that up…</div>}
        <div ref={end} />
      </div>
    </Drawer>
  );
}
