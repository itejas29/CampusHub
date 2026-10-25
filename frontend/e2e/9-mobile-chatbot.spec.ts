import { expect, test, type Page } from "@playwright/test";
import { ACCOUNTS, signIn } from "./helpers";

// QA-22: on a phone the floating chatbot button sat on top of the last card's
// buttons and links. Scrolled to the bottom, nothing a person taps may lie
// under it, and the page must not scroll sideways.
test.use({ viewport: { width: 390, height: 844 } });

async function coveredByChatbot(page: Page) {
  return page.evaluate(() => {
    const dock = document.querySelector("[data-testid=chatbot-dock]");
    if (!dock) return ["(no chatbot)"];
    const d = dock.getBoundingClientRect();
    const hits: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(
      "#main-content a, #main-content button, #main-content input, #main-content select, #main-content textarea",
    )) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.right > d.left && r.left < d.right && r.bottom > d.top && r.top < d.bottom) {
        hits.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 40)}"`);
      }
    }
    return hits;
  });
}

for (const [who, email, path] of [
  ["student", "riya.chauhan.031@campushub.example.com", "/"],
  ["coordinator", ACCOUNTS.cssiCoordinator, "/internships/students"],
] as const) {
  test(`the chatbot covers nothing a ${who} taps at phone width`, async ({ page }) => {
    await signIn(page, email);
    await page.goto(path);
    await expect(page.getByRole("button", { name: "Open CampusBot Assistant" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(300);

    expect(await coveredByChatbot(page)).toEqual([]);
    const sideways = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sideways).toBeLessThanOrEqual(0);
  });
}
