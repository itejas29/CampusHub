import { expect, test } from "@playwright/test";
import { ACCOUNTS, apiGet, signIn } from "./helpers";

type Dashboard = { stats: { key: string; value: number }[] };
// The total, not the preview list — the dashboard previews at most six of each kind.
const waiting = (d: Dashboard) => d.stats.find((s) => s.key === "pending_reviews")?.value ?? 0;

test("a mentor opens the longest-waiting submission from the dashboard and approves it", async ({ page }) => {
  await signIn(page, ACCOUNTS.summerMentor);
  const before = waiting(await apiGet<Dashboard>(page, "/dashboard/faculty"));
  expect(before, "the seed gives this mentor submissions to review").toBeGreaterThan(0);

  const queue = page.locator("section", { has: page.getByRole("heading", { name: "Review queue" }) });
  const first = queue.getByRole("link").filter({ hasText: "Review" }).first();
  const student = (await first.locator("span[title]").nth(1).getAttribute("title")) ?? "";
  await first.click();

  // The link lands on *that* student's record — it used to drop them and
  // redirect to the CSSI list, even for a Summer intern.
  await expect(page).toHaveURL(/\/internships\/review\?record=\d+/);
  if (student) await expect(page.getByText(student).first()).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Stage approved.")).toBeVisible();

  const after = waiting(await apiGet<Dashboard>(page, "/dashboard/faculty"));
  expect(after).toBe(before - 1);
});

test("closing the record drawer clears it from the URL, so Back works", async ({ page }) => {
  await signIn(page, ACCOUNTS.summerMentor);
  await page.goto("/internships/review");
  await page.getByRole("row").nth(1).click();
  await expect(page).toHaveURL(/record=\d+/);
  await page.keyboard.press("Escape");
  await expect(page).not.toHaveURL(/record=/);
});
