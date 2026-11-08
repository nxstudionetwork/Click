import { useEffect, useState } from 'react';
import { Icon } from '@click/ui';
import type { Scene } from '../config/visuals';
import { Photo } from './Photo';
import { useReducedMotion } from './useReducedMotion';

/**
 * An animated sequence of real partner-work photographs (crossfade + slow zoom).
 * Lighter than video on low-end phones and slow networks: only the current and
 * next frames are loaded. Pausable (WCAG 2.2.2), static under reduced motion,
 * and paused while the tab is hidden.
 */
export function StoryReel({ scenes, interval = 3400, label, sizes, showCaption = true, eagerFirst = false, className = '' }: {
  scenes: (Scene & { label?: string })[];
  interval?: number;
  label: string;
  sizes?: string;
  showCaption?: boolean;
  eagerFirst?: boolean;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const playing = !reduced && !paused && scenes.length > 1;

  useEffect(() => { setIndex(0); }, [scenes]);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => { if (!document.hidden) setIndex((i) => (i + 1) % scenes.length); }, interval);
    return () => window.clearInterval(id);
  }, [playing, interval, scenes.length]);

  const current = scenes[index] ?? scenes[0];
  if (!current) return null;
  const next = (index + 1) % scenes.length;

  return (
    <section className={`reel ${className}`} aria-roledescription="carousel" aria-label={label}>
      <div className="reel__frames">
        {scenes.map((scene, i) => (i === index || i === next) && (
          <div
            key={`${scene.photo}-${i}`}
            className={`reel__frame ${i === index ? 'is-active' : ''} ${playing ? 'is-moving' : ''}`}
            aria-hidden={i !== index}
            role="group" aria-roledescription="slide" aria-label={`${i + 1} of ${scenes.length}`}
          >
            <Photo photo={scene.photo} alt={scene.alt} sizes={sizes} eager={eagerFirst && i === 0} />
          </div>
        ))}
        <div className="reel__shade" aria-hidden="true" />
      </div>
      {showCaption && (
        <div className="reel__caption" key={index}>
          <span className="reel__stage">{current.label ?? current.stage}</span>
          <span className="reel__text">{current.caption}</span>
        </div>
      )}
      {scenes.length > 1 && (
        <div className="reel__controls">
          <div className="reel__dots" role="group" aria-label="Choose a scene">
            {scenes.map((scene, i) => (
              <button
                key={i} type="button" className={`reel__dot ${i === index ? 'is-active' : ''}`}
                aria-label={`Show ${scene.label ?? scene.stage}`} aria-current={i === index}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>
          {!reduced && (
            <button type="button" className="reel__pause" onClick={() => setPaused((p) => !p)} aria-label={paused ? 'Play the story' : 'Pause the story'}>
              {paused ? <Icon name="right" size={16} /> : <span className="reel__pause-bars" aria-hidden="true" />}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
