import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { home } from '../lib/api';
import { AlertList } from '../components/home/renderers';
import { Card, LoadingRows, PageHeader, QueryError, Tabs } from '../components/ui';

export function AlertsPage() {
  const [params] = useSearchParams();
  const [sev, setSev] = useState<string>('');
  const risk = params.get('risk') === 'true';
  const q = useQuery({ queryKey: ['os', 'alerts', sev, risk], queryFn: () => home.alerts({ severity: sev || undefined, risk: risk ? 'true' : undefined }) });
  return (
    <>
      <PageHeader title={risk ? 'Risk watch' : 'Alerts & exceptions'}
        description="Exceptions detected in live data — payments, operations, partners, people, security and systems. You see only alerts whose source data you’re allowed to see." />
      <Tabs value={sev} onChange={setSev} items={[{ value: '', label: 'All' }, { value: 'critical', label: 'Critical' }, { value: 'high', label: 'High' },
        { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }]} />
      <Card flush>{q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <AlertList items={q.data.results} />}</Card>
    </>
  );
}
