import { useEffect, useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

/** Colleague picker (active employee accounts in your organization: name and designation only). */
export function PersonPicker({ label, value, onChange }: {
  label: string; value: { id: string; fullName: string } | null; onChange: (p: { id: string; fullName: string } | null) => void;
}) {
  const id = useId();
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  useEffect(() => { const t = setTimeout(() => setTerm(q), 200); return () => clearTimeout(t); }, [q]);
  const people = useQuery({ queryKey: ['os', 'picker', term], queryFn: () => api.people.picker(term), enabled: open });
  if (value) {
    return (
      <div className="field"><span className="field__label">{label}</span>
        <div className="identity-chip"><span>{value.fullName}</span><button type="button" className="btn btn--ghost btn--sm" onClick={() => onChange(null)}>Change</button></div>
      </div>
    );
  }
  return (
    <div className="field" style={{ position: 'relative' }}>
      <label className="field__label" htmlFor={id}>{label}</label>
      <input id={id} className="field__input" value={q} placeholder="Search by name or employee ID" autoComplete="off"
             onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} onChange={(e) => setQ(e.target.value)} />
      {open && (
        <div className="popover" style={{ left: 0, right: 0, maxHeight: 240, overflowY: 'auto' }}>
          {people.data?.results.length ? people.data.results.map((p) => (
            <button key={p.id} type="button" className="menu-item" onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange({ id: p.id, fullName: p.fullName }); setOpen(false); }}>
              <span className="grow">{p.fullName}<br /><span className="xs muted">{p.designation ?? ''}</span></span>
            </button>
          )) : <p className="small muted" style={{ padding: 10 }}>{people.isFetching ? 'Searching…' : 'No one found.'}</p>}
        </div>
      )}
    </div>
  );
}
