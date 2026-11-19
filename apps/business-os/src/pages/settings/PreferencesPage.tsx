import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button, TextField, useToast } from '@click/ui';
import type { OSPreferences } from '@click/api';
import { api, apiMessage, fieldErrors } from '../../lib/api';
import { useOS, useOSSession } from '../../session/OSSession';
import { Alert, Card } from '../../components/ui';
import { LANGUAGES, MUTABLE_TYPES, TIMEZONES } from './options';

export function PreferencesPage() {
  const ctx = useOS();
  const { setContext } = useOSSession();
  const toast = useToast();
  const [name, setName] = useState(ctx.user.fullName);
  const [tz, setTz] = useState(ctx.account.timezone);
  const [lang, setLang] = useState(ctx.account.language);
  const profile = useMutation({
    mutationFn: () => api.me.updateProfile({ fullName: name, timezone: tz, language: lang }),
    onSuccess: (c) => { setContext(c); toast('Profile saved'); },
  });
  const prefs = useMutation({ mutationFn: (p: OSPreferences) => api.me.updatePreferences(p), onSuccess: (c) => { setContext(c); toast('Preferences saved'); } });
  const muted = ctx.account.preferences.notifications?.muted ?? [];
  const appearance = ctx.account.preferences.appearance ?? { theme: 'system', density: 'comfortable' };
  const errs = fieldErrors(profile.error);

  return (
    <div className="stack stack--lg">
      <Card title="Profile">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); profile.mutate(); }}>
          {profile.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(profile.error)}</Alert>}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} error={errs.fullName} />
          <div className="grid grid--2">
            <div className="field"><label className="field__label" htmlFor="ptz">Time zone</label>
              <select id="ptz" className="field__input" value={tz} onChange={(e) => setTz(e.target.value)}>{[...new Set([tz, ...TIMEZONES])].map((t) => <option key={t}>{t}</option>)}</select></div>
            <div className="field"><label className="field__label" htmlFor="plang">Language</label>
              <select id="plang" className="field__input" value={lang} onChange={(e) => setLang(e.target.value)}>{LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select></div>
          </div>
          <p className="xs muted">Designation, department, location and manager come from People & HR and can’t be edited here.</p>
          <div><Button type="submit" loading={profile.isPending}>Save profile</Button></div>
        </form>
      </Card>
      <Card title="Appearance">
        <div className="grid grid--2">
          <div className="field"><label className="field__label" htmlFor="theme">Theme</label>
            <select id="theme" className="field__input" value={appearance.theme} onChange={(e) => prefs.mutate({ appearance: { ...appearance, theme: e.target.value as 'light' } })}>
              <option value="system">Match my device</option><option value="light">Light</option><option value="dark">Dark</option></select></div>
        </div>
      </Card>
      <Card title="Notifications">
        <p className="small muted" style={{ marginBottom: 12 }}>In-app notifications. Security alerts and approval requests always reach you. Email, SMS and push follow these choices once those channels are connected.</p>
        <div className="stack" style={{ gap: 8 }}>
          {MUTABLE_TYPES.map((t) => (
            <label key={t.value} className="row small">
              <input type="checkbox" checked={!muted.includes(t.value)} disabled={prefs.isPending}
                onChange={(e) => prefs.mutate({ notifications: { muted: e.target.checked ? muted.filter((x) => x !== t.value) : [...muted, t.value] } })} />
              {t.label}
            </label>
          ))}
        </div>
      </Card>
    </div>
  );
}
