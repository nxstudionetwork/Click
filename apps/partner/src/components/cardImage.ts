import { CLICK_BRAND } from '@click/ui';
import { visualFor } from '../config/visuals';
import { initials, type CardData } from './PartnerCard';

/**
 * Draws the Partner card to a PNG for "Save" / file sharing. Uses only the
 * public-safe CardData fields, so a saved or shared image can't leak private data.
 */
export async function renderCardImage(data: CardData, scale = 2): Promise<Blob> {
  const W = 600, H = 375;
  const canvas = document.createElement('canvas');
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas is not supported.');
  ctx.scale(scale, scale);
  const font = (weight: number, size: number) => `${weight} ${size}px Inter, system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif`;

  // Background: deep navy -> electric blue -> cyan, with a category-accent glow.
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#0b1b44');
  bg.addColorStop(0.52, '#163a9a');
  bg.addColorStop(1, '#0f7fa8');
  roundRect(ctx, 0, 0, W, H, 28);
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.save();
  ctx.clip();
  const glow = ctx.createRadialGradient(W * 0.9, H * 0.05, 10, W * 0.9, H * 0.05, 280);
  glow.addColorStop(0, hexA(visualFor(data.typeSlug).accent, 0.65));
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1.5;
  for (let r = 120; r < 420; r += 60) { ctx.beginPath(); ctx.arc(W + 20, H + 40, r, 0, Math.PI * 2); ctx.stroke(); }
  ctx.restore();

  // Click logo mark (fixed brand colours) + product label.
  roundRect(ctx, 32, 30, 34, 34, 10);
  ctx.fillStyle = CLICK_BRAND.mark;
  ctx.fill();
  ctx.beginPath(); ctx.arc(49, 47, 8, 0, Math.PI * 2); ctx.strokeStyle = CLICK_BRAND.ring; ctx.lineWidth = 3.2; ctx.stroke();
  ctx.beginPath(); ctx.arc(49, 47, 2.8, 0, Math.PI * 2); ctx.fillStyle = CLICK_BRAND.dot; ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.font = font(800, 15);
  ctx.textBaseline = 'middle';
  ctx.fillText('CLICK PARTNER', 78, 48);

  // Avatar monogram + name.
  roundRect(ctx, 32, 100, 64, 64, 18);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.font = font(800, 24);
  ctx.textAlign = 'center';
  ctx.fillText(initials(data.businessName), 64, 133);
  ctx.textAlign = 'left';
  ctx.font = font(800, 26);
  ctx.fillText(fit(ctx, data.businessName, W - 150), 112, 122);
  ctx.font = font(500, 15);
  ctx.fillStyle = 'rgba(255,255,255,0.75)';
  ctx.fillText(data.typeName, 112, 150);

  // Partner ID.
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.font = font(600, 12);
  ctx.fillText('PARTNER ID', 32, 205);
  ctx.fillStyle = '#fff';
  ctx.font = `700 34px ui-monospace, 'SF Mono', Menlo, Consolas, monospace`;
  ctx.fillText(data.partnerCode, 32, 240);

  // Category + status.
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.font = font(600, 12);
  ctx.fillText('PARTNER CATEGORY', 32, 300);
  ctx.fillText('STATUS', 320, 300);
  ctx.fillStyle = '#fff';
  ctx.font = font(700, 18);
  ctx.fillText(fit(ctx, data.categoryName, 260), 32, 326);
  ctx.fillText(fit(ctx, data.statusLabel, 240), 320, 326);

  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not create image.'))), 'image/png'));
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function fit(ctx: CanvasRenderingContext2D, text: string, max: number) {
  if (ctx.measureText(text).width <= max) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(`${t}…`).width > max) t = t.slice(0, -1);
  return `${t}…`;
}

function hexA(hex: string, alpha: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
