import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, ErrorState, Icon, Skeleton } from '@click/ui';
import type { PartnerType } from '@click/api';
import { OnboardingLayout } from '../../components/OnboardingLayout';
import { StoryReel } from '../../components/StoryReel';
import { iconFor, visualFor } from '../../config/visuals';
import { api } from '../../lib/api';
import { apiMessage } from '../../lib/format';
import { useCatalog, useDraftPartner } from './useOnboarding';

function TypePreview({ type, categoryName, categoryDescription }: { type: PartnerType; categoryName?: string; categoryDescription?: string }) {
  const visual = visualFor(type.slug);
  return (
    <div className="preview" style={{ ['--accent' as string]: visual.accent }}>
      <StoryReel key={type.slug} scenes={visual.scenes} label={`${type.name} on Click`} sizes="(min-width: 960px) 40vw, 100vw" />
      <div className="preview__body">
        <p className="preview__type"><Icon name={iconFor(type.icon)} size={18} /> {type.name}</p>
        <h2>{categoryName ?? type.tagline}</h2>
        <p className="muted">{categoryName ? categoryDescription : type.description}</p>
      </div>
    </div>
  );
}

export function CategoryPage() {
  const navigate = useNavigate();
  const catalog = useCatalog();
  const { partner, setPartnerState } = useDraftPartner();
  const [typeSlug, setTypeSlug] = useState<string | undefined>(partner?.partnerType.slug);
  const [categorySlug, setCategorySlug] = useState<string | undefined>(partner?.category.slug);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const types = catalog.data?.types ?? [];
  const type = useMemo(() => types.find((t) => t.slug === typeSlug), [types, typeSlug]);
  const category = type?.categories.find((c) => c.slug === categorySlug);

  // A type with a single category needs no second choice.
  useEffect(() => {
    if (type && type.categories.length === 1) setCategorySlug(type.categories[0]!.slug);
  }, [type]);

  async function save() {
    if (!type || !category) return setError('Choose your partner category to continue.');
    setSaving(true);
    setError(null);
    try {
      setPartnerState(await api.partner.chooseCategory({ partnerType: type.slug, category: category.slug }));
      navigate('/onboarding/profile');
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <OnboardingLayout
      step="category"
      title="What do you provide through Click?"
      subtitle="Choose your partner type and category. This sets up your Partner profile and the tools you’ll see."
      aside={type ? <TypePreview type={type} categoryName={category?.name} categoryDescription={category?.description} /> : (
        <div className="preview preview--empty">
          <StoryReel scenes={visualFor(undefined).scenes} label="Partners on Click" sizes="40vw" />
          <div className="preview__body"><h2>Your business. Your services. Your Click.</h2><p className="muted">Pick a partner type to see how it works.</p></div>
        </div>
      )}
      footer={(
        <>
          {error && <p className="field__error" role="alert">{error}</p>}
          <Button block onClick={() => void save()} loading={saving} disabled={!category}>
            {category ? `Continue as ${category.name}` : 'Choose a category'}
          </Button>
        </>
      )}
    >
      {catalog.isPending && (
        <div className="type-grid" aria-busy="true">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} height={112} radius={18} />)}</div>
      )}
      {catalog.isError && <ErrorState error={new Error(apiMessage(catalog.error))} onRetry={() => void catalog.refetch()} />}
      {catalog.isSuccess && (
        <>
          <fieldset className="type-fieldset">
            <legend className="section-label">Partner type</legend>
            <div className="type-grid">
              {types.map((t) => {
                const checked = t.slug === typeSlug;
                return (
                  <label key={t.slug} className={`type-card ${checked ? 'is-checked' : ''}`} style={{ ['--accent' as string]: visualFor(t.slug).accent }}>
                    <input type="radio" name="partner-type" value={t.slug} checked={checked}
                      onChange={() => { setTypeSlug(t.slug); setCategorySlug(undefined); setError(null); }} />
                    <span className="type-card__icon" aria-hidden="true"><Icon name={iconFor(t.icon)} size={24} /></span>
                    <span className="type-card__name">{t.name}</span>
                    <span className="type-card__desc">{t.description}</span>
                    <span className="type-card__check" aria-hidden="true"><Icon name="check" size={14} /></span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {type && (
            <div className="category-step">
              <div className="preview-inline" aria-hidden="true">
                <TypePreview type={type} categoryName={category?.name} categoryDescription={category?.description} />
              </div>
              <fieldset className="type-fieldset" key={type.slug}>
                <legend className="section-label">Partner category · {type.name}</legend>
                <div className="cat-grid">
                  {type.categories.map((c) => {
                    const checked = c.slug === categorySlug;
                    return (
                      <label key={c.slug} className={`cat-card ${checked ? 'is-checked' : ''}`}>
                        <input type="radio" name="partner-category" value={c.slug} checked={checked}
                          onChange={() => { setCategorySlug(c.slug); setError(null); }} />
                        <span className="cat-card__icon" aria-hidden="true"><Icon name={iconFor(c.icon)} size={20} /></span>
                        <span className="cat-card__text">
                          <span className="cat-card__name">{c.name}</span>
                          <span className="cat-card__desc">{c.description}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            </div>
          )}
        </>
      )}
    </OnboardingLayout>
  );
}
