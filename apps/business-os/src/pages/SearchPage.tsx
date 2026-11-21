import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon } from '@click/ui';
import { api } from '../lib/api';
import { Card, Empty, LoadingRows, PageHeader, QueryError } from '../components/ui';

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get('q') ?? '');
  const q = params.get('q') ?? '';
  const type = params.get('type') ?? '';
  useEffect(() => { const t = setTimeout(() => { if (text !== q) setParams((p) => { p.set('q', text); return p; }, { replace: true }); }, 250); return () => clearTimeout(t); }, [text, q, setParams]);
  const res = useQuery({ queryKey: ['os', 'search-page', q, type], queryFn: ({ signal }) => api.search(q, type || undefined, signal), enabled: q.trim().length >= 2 });
  const types = useQuery({ queryKey: ['os', 'search-types'], queryFn: () => api.search('', undefined), staleTime: Infinity });

  return (
    <>
      <PageHeader title="Search" description="One search across Business OS. You only ever see records your role and scope allow." />
      <Card flush>
        <div className="toolbar">
          <div className="search-input grow"><Icon name="search" size={16} /><input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, employee ID, reference…" aria-label="Search" /></div>
          <select className="field__input" aria-label="Type" value={type} onChange={(e) => setParams((p) => { if (e.target.value) p.set('type', e.target.value); else p.delete('type'); return p; })}>
            <option value="">Everything</option>
            {types.data?.types.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
          </select>
        </div>
        {q.trim().length < 2 ? <Empty icon="search" title="Start typing to search" message="At least 2 characters." /> :
          res.isPending ? <LoadingRows /> : res.error ? <QueryError error={res.error} /> : !res.data.groups.length ? (
            <Empty icon="search" title="No results" message="Nothing you have access to matches that search." />
          ) : res.data.groups.map((g) => (
            <div key={g.type}>
              <div className="palette__group" style={{ padding: '14px 16px 4px' }}>{g.label}</div>
              <ul className="list">{g.results.map((r) => (
                <li key={r.id}><Link to={r.path} className="list-row"><span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{r.title}</span><span className="list-row__sub" style={{ display: 'block' }}>{r.subtitle}</span></span><Icon name="right" size={16} /></Link></li>
              ))}</ul>
            </div>
          ))}
      </Card>
    </>
  );
}
