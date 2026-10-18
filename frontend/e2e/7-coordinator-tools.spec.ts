import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

// The coordinator re-weights a placeholder rubric and confirms it.
test("a coordinator edits the rubric and confirms it", async ({ page }) => {
  await signIn(page, "rakesh.bhatt@campushub.example.com");
  await page.goto("/internships/programs");
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: "Minor Project (Semester VII)" }) });
  await card.getByRole("button", { name: "Edit rubric" }).click();
  const editor = page.getByRole("dialog", { name: /Rubric/ });
  await editor.getByLabel("Criterion 1 maximum marks").fill("20");
  await editor.getByLabel("Criterion 2 maximum marks").fill("20");
  await expect(editor.getByText("Total")).toContainText("100");
  await editor.getByRole("button", { name: "Save rubric" }).click();
  await expect(editor).toHaveCount(0);
  await expect(card.getByRole("cell", { name: "20", exact: true }).first()).toBeVisible();
  await card.getByRole("button", { name: "Confirm rubric" }).click();
  await expect(card.getByRole("button", { name: "Confirm rubric" })).toHaveCount(0);
});

// A student registers for the Minor Project, forms a team and ranks guides.
test("a student forms a team and ranks guides", async ({ page }) => {
  await signIn(page, "arjun.verma.021@campushub.example.com");
  await page.goto("/internships");
  // The card nearest the heading (the list around it is a <section> too).
  const open = page.getByRole("heading", { name: "Minor Project (Semester VII)" }).locator("xpath=ancestor::section[1]");
  await open.getByRole("button", { name: "Fill in my details" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("You are enrolled.")).toBeVisible();
  await page.getByRole("link", { name: /Open workflow/ }).last().click();

  await page.getByLabel("Team name").fill("Crop Vision");
  await page.getByRole("button", { name: "Form a team" }).click();
  await expect(page.getByText("Leader")).toBeVisible();
  await page.getByLabel("Choice 1").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Preferences saved for the whole team.")).toBeVisible();
});
