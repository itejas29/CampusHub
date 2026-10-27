import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/**
 * Regressions from the dashboard audit (22 Oct 2026): text too faint to read,
 * and one long unbroken string widening a phone page. Both are properties of
 * how the screen is drawn, so they are checked in a browser, on real data.
 */
const STUDENT = "aarav.desai.001@campushub.example.com";
const MENTOR = "anand.mehta@campushub.example.com";

/** Text elements under <main> whose contrast against their own background is
 *  below WCAG AA (4.5:1, or 3:1 for large text). Approximate by design: it walks
 *  up to the nearest opaque background and ignores gradients and images. */
async function faintText(page: Page) {
  return page.evaluate(() => {
    type Rgba = { r: number; g: number; b: number; a: number };
    const parse = (c: string): Rgba | null => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const [r, g, b, a = 1] = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return { r, g, b, a };
    };
    const channel = (v: number) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    };
    const luminance = ({ r, g, b }: Rgba) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    const backgroundOf = (el: Element): Rgba => {
      for (let e: Element | null = el; e; e = e.parentElement) {
        const c = parse(getComputedStyle(e).backgroundColor);
        if (c && c.a > 0.95) return c;
      }
      return { r: 255, g: 255, b: 255, a: 1 };
    };
    const found: string[] = [];
    const seen = new Set<string>();
    for (const el of document.querySelectorAll("main *")) {
      if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent?.trim())) continue;
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.opacity === "0") continue;
      const fg = parse(style.color);
      if (!fg) continue;
      const bg = backgroundOf(el);
      const mix = {
        r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a),
        b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1,
      };
      const [hi, lo] = [luminance(mix), luminance(bg)].sort((x, y) => y - x);
      const ratio = (hi + 0.05) / (lo + 0.05);
      const size = parseFloat(style.fontSize);
      const large = size >= 24 || (size >= 18.66 && parseInt(style.fontWeight) >= 700);
      if (ratio < (large ? 3 : 4.5)) {
        const label = `${(el.textContent ?? "").trim().slice(0, 36)} (${ratio.toFixed(2)}:1)`;
        if (!seen.has(label)) { seen.add(label); found.push(label); }
      }
    }
    return found;
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const [name, email] of [["student", STUDENT], ["mentor", MENTOR]] as const) {
    test(`the ${name} dashboard's text is readable in the ${theme} theme`, async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("campushub.theme", value), theme);
      await signIn(page, email);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      // Rings and count-ups settle, so what is measured is what is left on screen.
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(900);
      expect(await faintText(page), "text below WCAG AA contrast").toEqual([]);
    });
  }
}

test("one very long unbroken name does not widen a phone-sized dashboard", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, STUDENT);
  const long = "X".repeat(180);
  await page.route("**/api/v1/dashboard/student", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.action_items = [{
      title: long, due_at: "2026-11-01T10:00:00Z", context: long,
      link: "/internships/1", kind: "internship",
    }];
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(page.getByText(long.slice(0, 40)).first()).toBeVisible();
  const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(sideways, "pixels past the right edge").toBeLessThanOrEqual(0);
});
