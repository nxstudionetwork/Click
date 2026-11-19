import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon } from '../../components/ui';

type State = 'starting' | 'scanning' | 'unsupported' | 'denied' | 'error' | 'found';

interface Detector { detect(source: CanvasImageSource): Promise<{ rawValue: string }[]> }
type DetectorCtor = new (opts: { formats: string[] }) => Detector;

/** Click. links scanned from a QR code open inside the app; a product barcode looks the product up; anything else is a search. */
export function resolveScan(raw: string, origin = window.location.origin): string {
  const text = raw.trim();
  if (/^\d{8,14}$/.test(text)) return `/search?q=${text}`;
  try {
    const url = new URL(text);
    if (url.origin === origin) return `${url.pathname}${url.search}`;
  } catch { /* not a URL */ }
  if (text.startsWith('/') && !text.startsWith('//')) return text;
  return `/search?q=${encodeURIComponent(text.slice(0, 100))}`;
}

/**
 * Camera scan: QR codes (Click. links, store and table codes) and product barcodes (EAN / UPC on packs), decoded on the
 * device. Uses the browser's BarcodeDetector where it exists and the open-source ZXing decoder everywhere else, so it
 * works on desktop Chrome, Firefox and iPhone too. No image leaves the phone. Snap-to-recognise a dish would need a
 * visual-search model and is not claimed.
 */
export function CameraSearch({ onDone }: { onDone: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<State>('starting');
  const [found, setFound] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const Ctor = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector;
    if (!navigator.mediaDevices?.getUserMedia) { setState('unsupported'); return; }
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | undefined;
    let cancelled = false;
    let zx: { decode: (v: HTMLVideoElement) => string | null } | null = null;
    const native = Ctor ? new Ctor({ formats: ['qr_code', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'] }) : null;
    // ZXing is loaded only when the browser has no detector of its own.
    if (!native) {
      void Promise.all([import('@zxing/browser'), import('@zxing/library')]).then(([b, lib]) => {
        const hints = new Map<import("@zxing/library").DecodeHintType, unknown>([[lib.DecodeHintType.POSSIBLE_FORMATS, [lib.BarcodeFormat.QR_CODE, lib.BarcodeFormat.EAN_13, lib.BarcodeFormat.EAN_8,
          lib.BarcodeFormat.UPC_A, lib.BarcodeFormat.UPC_E, lib.BarcodeFormat.CODE_128]], [lib.DecodeHintType.TRY_HARDER, true]]);
        const reader = new b.BrowserMultiFormatReader(hints);
        zx = { decode: (v) => { try { return reader.decode(v).getText(); } catch { return null; } } };
      }).catch(() => setState('unsupported'));
    }
    const detector = { detect: async (v: HTMLVideoElement) => (native ? (await native.detect(v)).map((c) => c.rawValue) : zx ? [zx.decode(v)].filter(Boolean) as string[] : []) };
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then(async (s) => {
      if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
      stream = s;
      if (video.current) { video.current.srcObject = s; await video.current.play().catch(() => {}); }
      setState('scanning');
      timer = setInterval(async () => {
        if (!video.current || video.current.readyState < 2) return;
        try {
          const codes = await detector.detect(video.current);
          if (codes[0]) {
            clearInterval(timer);
            stream?.getTracks().forEach((t) => t.stop());
            navigator.vibrate?.(40);
            setFound(codes[0]);
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
          <p className="camera__hint" role="status">{state === 'starting' ? 'Starting camera…' : 'Point at a QR code or a product barcode'}</p>
        </div>
      )}
      {state === 'found' && (
        <div className="state">
          <div className="state__icon"><Icon name="check" /></div>
          <h3>{/^\d{8,14}$/.test(found.trim()) ? 'Barcode scanned' : 'Code scanned'}</h3>
          <p className="truncate" style={{ maxWidth: '100%' }}>{found}</p>
          <Button onClick={() => open(resolveScan(found))}>{/^\d{8,14}$/.test(found.trim()) ? 'Find this product' : 'Open in Click.'}</Button>
        </div>
      )}
      {state === 'unsupported' && <Note icon="camera" title="Camera not available" text="This browser can’t open the camera. Search by typing instead." />}
      {state === 'denied' && <Note icon="camera" title="Camera access is blocked" text="Allow camera access in your browser settings to scan Click. QR codes." />}
      {state === 'error' && <Note icon="alert" title="Camera unavailable" text="We couldn’t start the camera. Check that no other app is using it." />}
      <p className="small muted camera__foot">Scans QR codes and the barcode on packs. Everything is read on your device.</p>
    </div>
  );
}

function Note({ icon, title, text }: { icon: 'camera' | 'alert'; title: string; text: string }) {
  return <div className="state"><div className="state__icon"><Icon name={icon} /></div><h3>{title}</h3><p>{text}</p></div>;
}
