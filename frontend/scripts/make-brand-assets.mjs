// One-off asset generator: crops the shield emblem from the full LabelGuard AI logo
// and derives compact-mark / favicon PNGs. Safe to delete after use.
import sharp from "sharp";

const SRC = "public/labelguard-logo.png";

// Shield emblem occupies roughly the top ~55% of the 1254x1254 artwork, centered.
const EMBLEM = { left: 290, top: 120, width: 680, height: 680 };

await sharp(SRC)
  .extract(EMBLEM)
  .resize(480, 480)
  .png()
  .toFile("public/labelguard-mark.png");

await sharp(SRC)
  .extract(EMBLEM)
  .resize(64, 64)
  .png()
  .toFile("public/favicon.png");

console.log("brand assets written");
