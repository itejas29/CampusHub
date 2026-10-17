import { expect, test } from "@playwright/test";
import { ACCOUNTS, apiGet, signIn } from "./helpers";

type Assignment = { faculty_name: string; role: string; domain: string; is_active: boolean };

// The roles board: one card per role, "+ Add" appoints, × removes — and the
// server holds the result, not just the screen.
test("a role is given and taken away from its card", async ({ page }) => {
  await signIn(page, ACCOUNTS.registrar);
  await page.goto("/admin/roles");

  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: "Minor Specialisation Coordinator" }) });
  await card.getByRole("button", { name: "Add" }).click();
  const picker = page.getByRole("dialog", { name: /Give Minor Specialisation Coordinator/ });
  await picker.getByLabel("Search faculty").fill("Aarti");
  await picker.getByRole("button", { name: /Aarti Solanki/ }).click();
  await expect(page.getByText("Dr. Aarti Solanki is now Minor Specialisation Coordinator")).toBeVisible();

  const held = async () => (await apiGet<Assignment[]>(page, "/admin/roles"))
    .some((a) => a.faculty_name === "Dr. Aarti Solanki" && a.domain === "MINOR" && a.role === "COORDINATOR");
  expect(await held()).toBe(true);

  await card.getByRole("button", { name: /Remove Dr. Aarti Solanki/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove role" }).click();
  await expect(page.getByText(/no longer holds Minor Specialisation Coordinator/)).toBeVisible();
  expect(await held()).toBe(false);
});
