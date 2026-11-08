import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon } from '../../components/ui';

type State = 'starting' | 'scanning' | 'unsupported' | 'denied' | 'error' | 'found';

interface Detector { detect(source: CanvasImageSource): Promise<{ rawValue: string }[]> }
type DetectorCtor = new (opts: { formats: string[] }) => Detector;

/** Click. links scanned from a QR code open inside the app; anything else becomes a search. */
export function resolveScan(raw: string, origin = window.location.origin): string {
  const text = raw.trim();
  try {
    const url = new URL(text);
    if (url.origin === origin) return `${url.pathname}${url.search}`;
  } catch { /* not a URL */ }
  if (text.startsWith('/') && !text.startsWith('//')) return text;
  return `/search?q=${encodeURIComponent(text.slice(0, 100))}`;
}

/**
 * Camera search, foundation stage: scans QR codes on the device (BarcodeDetector, no image leaves the phone).
 * Image recognition ("snap a dish to find it") needs a visual-search provider and is not claimed here.
 */
export function CameraSearch({ onDone }: { onDone: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<State>('starting');
  const [found, setFound] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const Ctor = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector;
    if (!Ctor || !navigator.mediaDevices?.getUserMedia) { setState('unsupported'); return; }
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | undefined;
    let cancelled = false;
    const detector = new Ctor({ formats: ['qr_code'] });
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then(async (s) => {
      if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
      stream = s;
      if (video.current) { video.current.srcObject = s; await video.current.play().catch(() => {}); }
      setState('scanning');
      timer = setInterval(async () => {
        if (!video.current || video.current.readyState < 2) return;
        try {
          const codes = await detector.detect(video.current);
          if (codes[0]?.rawValue) {
            clearInterval(timer);
            stream?.getTracks().forEach((t) => t.stop());
            setFound(codes[0].rawValue);
            setState('found');
          }
        } catch { /* keep scanning */ }
      }, 350);
    }).catch((e) => setState(e instanceof DOMException && e.name === 'NotAllowedError' ? 'denied' : 'error'));
    return () => { cancelled = true; clearInterval(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, []);

  const open = (path: string) => { onDone(); navigate(path); };

  return (
    <div className="camera">
      {(state === 'starting' || state === 'scanning') && (
        <div className="camera__view">
          <video ref={video} playsInline muted aria-label="Camera preview" />
          <span className="camera__frame" aria-hidden="true" />
          <p className="camera__hint" role="status">{state === 'starting' ? 'Starting camera…' : 'Point at a Click. QR code'}</p>
        </div>
      )}
      {state === 'found' && (
        <div className="state">
          <div className="state__icon"><Icon name="check" /></div>
          <h3>Code scanned</h3>
          <p className="truncate" style={{ maxWidth: '100%' }}>{found}</p>
          <Button onClick={() => open(resolveScan(found))}>Open in Click.</Button>
        </div>
      )}
      {state === 'unsupported' && <Note icon="camera" title="Scanning isn’t supported here" text="This browser can’t scan codes. Try Click. in Chrome on Android, or search by typing." />}
      {state === 'denied' && <Note icon="camera" title="Camera access is blocked" text="Allow camera access in your browser settings to scan Click. QR codes." />}
      {state === 'error' && <Note icon="alert" title="Camera unavailable" text="We couldn’t start the camera. Check that no other app is using it." />}
      <p className="small muted camera__foot">Snap-to-search for dishes and products arrives with visual search. Scanning stays on your device.</p>
    </div>
  );
}

function Note({ icon, title, text }: { icon: 'camera' | 'alert'; title: string; text: string }) {
  return <div className="state"><div className="state__icon"><Icon name={icon} /></div><h3>{title}</h3><p>{text}</p></div>;
}
