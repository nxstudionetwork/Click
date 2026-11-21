import { Link } from 'react-router-dom';
import { useOS } from '../session/OSSession';
import { Card, PageHeader } from '../components/ui';

export function HelpPage() {
  const ctx = useOS();
  return (
    <>
      <PageHeader title="Help" description="How Click Business OS works and where to go when something isn’t right." />
      <div className="grid grid--2">
        <Card title="Getting around">
          <ul className="stack small" style={{ paddingLeft: 18, margin: 0 }}>
            <li><strong>Ctrl/⌘ + K</strong> opens search from anywhere.</li>
            <li><Link to="/my-work">My Work</Link> collects decisions, tasks and your open requests.</li>
            <li>The sidebar shows only the areas your role grants. Areas marked <em>SOON</em> are registered but still being built.</li>
            <li>The <strong>✦</strong> button opens Click Business AI. It can only see what you can see.</li>
          </ul>
        </Card>
        <Card title="Access & security">
          <ul className="stack small" style={{ paddingLeft: 18, margin: 0 }}>
            <li>What you can do is decided by your roles and their scope (for example “Finance · approve · your region”). See it on your <Link to="/profile">profile</Link>.</li>
            <li>Need more access? Ask your manager or a Business OS administrator. You can’t grant access to yourself.</li>
            <li>Turn on <Link to="/settings/security">two-step verification</Link>; sensitive areas require it.</li>
            <li>Sessions end after {ctx.security.idleMinutes} minutes of inactivity. You can sign out other devices from Security.</li>
          </ul>
        </Card>
        <Card title="Wrong details?">
          <p className="small">Your department, designation, location and manager come from People & HR. Ask HR to correct them; changes appear here automatically.</p>
        </Card>
        <Card title="Click is a platform">
          <p className="small">Click connects customers with participating partners, merchants and service providers. Click isn’t automatically the seller of what’s listed. Every financial record in Business OS carries the commercial model of the relationship (marketplace, commission partner, agency, Click-operated, Click-owned inventory, third-party fulfillment).</p>
        </Card>
      </div>
    </>
  );
}
