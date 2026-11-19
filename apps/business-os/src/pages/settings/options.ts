export const TIMEZONES = [
  'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo', 'Europe/London', 'Europe/Berlin', 'America/New_York',
  'America/Los_Angeles', 'Australia/Sydney', 'UTC',
];

export const LANGUAGES = [
  { value: 'en', label: 'English' }, { value: 'hi', label: 'हिन्दी (Hindi)' }, { value: 'te', label: 'తెలుగు (Telugu)' },
  { value: 'ta', label: 'தமிழ் (Tamil)' }, { value: 'kn', label: 'ಕನ್ನಡ (Kannada)' },
];

/** Notification types people may mute. Security alerts and approval requests are essential and always delivered. */
export const MUTABLE_TYPES = [
  { value: 'approval_result', label: 'Decisions on my requests' },
  { value: 'task_assigned', label: 'Tasks assigned to me' },
  { value: 'deadline', label: 'Deadlines and escalations' },
  { value: 'workflow', label: 'Workflow updates' },
  { value: 'business', label: 'Business alerts' },
  { value: 'partner', label: 'Partner events' },
  { value: 'system', label: 'System alerts' },
  { value: 'announcement', label: 'Announcements' },
];
