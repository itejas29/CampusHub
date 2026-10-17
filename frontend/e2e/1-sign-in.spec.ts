import { expect, test } from "@playwright/test";
import { ACCOUNTS, signIn } from "./helpers";

test("a wrong password is refused with a message, and the user stays on sign-in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("University email").fill(ACCOUNTS.cssiCoordinator);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("an empty form explains what is missing instead of doing nothing", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("email and password");
});

test("a coordinator signs in and sees their own module's live figures", async ({ page }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);

  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
  const portfolio = page.getByRole("article").filter({ hasText: "CSSI coordination" });
  await expect(portfolio).toBeVisible();
  // The seeded ICT CSSI cohort — a real count from the API, not a placeholder.
  await expect(portfolio).toContainText("203");
});

test("there is no fake single-sign-on button on the sign-in page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /google|sso|workspace/i })).toHaveCount(0);
});
