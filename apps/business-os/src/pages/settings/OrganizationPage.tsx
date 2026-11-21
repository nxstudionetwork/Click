import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextField, useToast } from '@click/ui';
import type { OSOrgUnit } from '@click/api';
import { api, apiMessage, fieldErrors } from '../../lib/api';
import { Alert, Card, Dialog, LoadingRows, QueryError, Status, Tabs } from '../../components/ui';

export function OrganizationPage() {
  const q = useQuery({ queryKey: ['os', 'org', 'tree'], queryFn: api.org.tree });
  const [params] = useSearchParams();
  const [tab, setTab] = useState<'units' | 'departments'>('units');
  const [editing, setEditing] = useState<OSOrgUnit | 'new' | null>(null);
  const [newDept, setNewDept] = useState(false);
  const highlight = params.get('unit');
  if (q.isPending) return <Card><LoadingRows rows={8} /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  const t = q.data;

  return (
    <div className="stack">
      <div className="row row--between row--wrap">
        <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>{t.organization.name} structure</h2>
          <p className="muted small">Business units, regions, states, cities and sites (branches, offices, warehouses). Permission scopes resolve against this tree.</p></div>
        {t.canManage && <div className="row">
          {tab === 'units' ? <Button onClick={() => setEditing('new')}><Icon name="plus" size={16} />Add unit</Button> : <Button onClick={() => setNewDept(true)}><Icon name="plus" size={16} />Add department</Button>}
        </div>}
      </div>
      <Tabs value={tab} onChange={setTab} items={[{ value: 'units', label: 'Locations & units', count: t.units.length }, { value: 'departments', label: 'Departments & teams', count: t.departments.length }]} />
      {tab === 'units' ? (
        <Card flush>
          <ul className="tree">
            {t.units.map((u) => (
              <li key={u.id} className="tree-row" style={{ paddingLeft: 12 + u.depth * 22, background: u.id === highlight ? 'var(--c-brand-soft)' : undefined }}>
                <Icon name={['branch', 'office', 'warehouse', 'service_center', 'facility'].includes(u.type) ? 'building' : 'pin'} size={15} />
                <strong className="grow ellipsis">{u.name}</strong>
                <span className="mono xs muted">{u.code}</span>
                <Status value={u.type} tone="neutral" label={u.typeLabel} />
                <span className="xs muted" style={{ minWidth: 80, textAlign: 'right' }}>{u.employees} people</span>
                {!u.isActive && <Status value="inactive" tone="neutral" label="Inactive" />}
                {t.canManage && <button className="icon-btn" aria-label={`Edit ${u.name}`} onClick={() => setEditing(u)}><Icon name="edit" size={15} /></button>}
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <div className="grid grid--2">
          {t.departments.map((d) => (
            <Card key={d.id} title={<div><h2>{d.name}</h2><span className="xs muted mono">{d.code}</span></div>}>
              <div className="small muted">{d.orgUnitId ? `At ${t.units.find((u) => u.id === d.orgUnitId)?.name ?? 'a location'}` : 'Shared corporate function'}{d.head ? ` · Head: ${d.head}` : ''}</div>
              {d.teams.length > 0 && <div className="pill-list" style={{ marginTop: 10 }}>{d.teams.map((tm) => <span key={tm.id} className="pill">{tm.name}</span>)}</div>}
            </Card>
          ))}
          {!t.departments.length && <p className="muted small">You don’t have access to departments.</p>}
        </div>
      )}
      {editing && <UnitDialog unit={editing === 'new' ? null : editing} units={t.units} types={t.unitTypes} onClose={() => setEditing(null)} />}
      {newDept && <DepartmentDialog units={t.units} onClose={() => setNewDept(false)} />}
    </div>
  );
}

function UnitDialog({ unit, units, types, onClose }: { unit: OSOrgUnit | null; units: OSOrgUnit[]; types: { key: string; label: string }[]; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(unit?.name ?? '');
  const [code, setCode] = useState(unit?.code ?? '');
  const [type, setType] = useState(unit?.type ?? 'branch');
  const [parentId, setParentId] = useState(unit?.parentId ?? '');
  const [city, setCity] = useState(unit?.city ?? '');
  const [active, setActive] = useState(unit?.isActive ?? true);
  const save = useMutation({
    mutationFn: () => unit ? api.org.updateUnit(unit.id, { name, code, unitType: type, parentId: parentId || null, city, isActive: active })
      : api.org.createUnit({ name, code, unitType: type, parentId: parentId || null, city }),
    onSuccess: () => { toast('Saved'); void qc.invalidateQueries({ queryKey: ['os', 'org'] }); onClose(); },
  });
  const errs = fieldErrors(save.error);
  const invalidParents = new Set(unit ? units.filter((u) => u.id === unit.id || isDescendant(units, u, unit.id)).map((u) => u.id) : []);
  return (
    <Dialog title={unit ? `Edit ${unit.name}` : 'Add unit'} onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      {save.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(save.error)}</Alert>}
      <div className="grid grid--2">
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errs.name} />
        <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} error={errs.code} />
      </div>
      <div className="grid grid--2">
        <div className="field"><label className="field__label" htmlFor="ut">Type</label>
          <select id="ut" className="field__input" value={type} onChange={(e) => setType(e.target.value)}>{types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></div>
        <TextField label="City" value={city} onChange={(e) => setCity(e.target.value)} />
      </div>
      <div className="field"><label className="field__label" htmlFor="up">Parent</label>
        <select id="up" className="field__input" value={parentId} onChange={(e) => setParentId(e.target.value)}>
          <option value="">Top level (directly under the organization)</option>
          {units.filter((u) => !invalidParents.has(u.id)).map((u) => <option key={u.id} value={u.id}>{'  '.repeat(u.depth)}{u.name}</option>)}
        </select>
        {errs.parent && <span className="field__error">{errs.parent}</span>}</div>
      {unit && <label className="row small"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Active</label>}
      {unit && <p className="xs muted">Moving a unit moves everything under it; scopes anchored there move with it.</p>}
    </Dialog>
  );
}

function isDescendant(units: OSOrgUnit[], u: OSOrgUnit, ancestorId: string): boolean {
  let cur: OSOrgUnit | undefined = u;
  const seen = new Set<string>();
  while (cur?.parentId && !seen.has(cur.id)) {
    seen.add(cur.id);
    if (cur.parentId === ancestorId) return true;
    cur = units.find((x) => x.id === cur!.parentId);
  }
  return false;
}

function DepartmentDialog({ units, onClose }: { units: OSOrgUnit[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [unitId, setUnitId] = useState('');
  const save = useMutation({ mutationFn: () => api.org.createDepartment({ name, code, orgUnitId: unitId || null }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['os', 'org'] }); onClose(); } });
  const errs = fieldErrors(save.error);
  return (
    <Dialog title="Add department" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      {save.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(save.error)}</Alert>}
      <div className="grid grid--2">
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errs.name} />
        <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} error={errs.code} />
      </div>
      <div className="field"><label className="field__label" htmlFor="du">Location</label>
        <select id="du" className="field__input" value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">Shared corporate function (no single location)</option>
          {units.map((u) => <option key={u.id} value={u.id}>{'  '.repeat(u.depth)}{u.name}</option>)}
        </select></div>
    </Dialog>
  );
}
