import type { OnboardingStep } from '@click/api';

export const STEP_ORDER: OnboardingStep[] = ['category', 'profile', 'location', 'review', 'complete'];

export const STEP_ROUTE: Record<OnboardingStep, string> = {
  category: '/onboarding/category',
  profile: '/onboarding/profile',
  location: '/onboarding/location',
  review: '/onboarding/review',
  complete: '/home',
};

export const ONBOARDING_STEPS: { step: OnboardingStep; label: string }[] = [
  { step: 'category', label: 'Category' },
  { step: 'profile', label: 'Profile' },
  { step: 'location', label: 'Location' },
  { step: 'review', label: 'Partner ID' },
];

/** A partner may revisit earlier steps, never skip ahead of the server's onboarding step. */
export function canVisit(requested: OnboardingStep, current: OnboardingStep): boolean {
  return STEP_ORDER.indexOf(requested) <= STEP_ORDER.indexOf(current);
}
