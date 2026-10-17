import { expect, test } from "@playwright/test";
import { ACCOUNTS, apiGet, signIn } from "./helpers";

type MentorLoad = {
  faculty_id: number; department_code: string | null;
  assigned_count: number; max_capacity: number;
};

test("a CSSI coordinator re-allocates every student without overloading a mentor", async ({ page }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);

  // The dashboard's primary action carries the real programme id.
  const portfolio = page.getByRole("article").filter({ hasText: "CSSI coordination" });
  await portfolio.getByRole("link", { name: "Allocate mentors" }).click();
  await expect(page).toHaveURL(/\/internships\/mentor-assignment\?program_id=\d+/);
  const programId = new URL(page.url()).searchParams.get("program_id");

  // Start from nothing, through the confirmation dialog.
  await page.getByRole("button", { name: "Reset all" }).click();
  const confirm = page.getByRole("dialog", { name: /Remove every mentor allocation/ });
  await expect(confirm).toBeVisible();
  // A destructive dialog opens on Cancel, so a stray Enter cannot wipe data.
  await expect(confirm.getByRole("button", { name: "Cancel" })).toBeFocused();
  await confirm.getByRole("button", { name: "Remove all" }).click();
  await expect(page.getByText(/Cleared the mentor for \d+ students/)).toBeVisible();

  // One click: pick the mentors needed and allocate in roll-number blocks.
  await page.getByRole("button", { name: "Auto-allocate" }).click();
  await expect(page.getByText(/Allocated 203 students across \d+ mentors \(at most 10 each\)/))
    .toBeVisible();

  // What the server now holds — not just what the banner said.
  const loads = await apiGet<MentorLoad[]>(page, `/internships/programs/${programId}/mentors-capacity`);
  const carried = loads.filter((m) => m.assigned_count > 0);
  expect(carried.reduce((sum, m) => sum + m.assigned_count, 0)).toBe(203);
  for (const mentor of carried) {
    expect(mentor.assigned_count).toBeLessThanOrEqual(mentor.max_capacity);
  }
  // One click picked the mentors itself, and the panel shows exactly who.
  await expect(page.getByRole("checkbox", { name: /in the next run/, checked: true }))
    .toHaveCount(carried.length);
  // Mentors come from the programme's own department only.
  expect(new Set(loads.map((m) => m.department_code))).toEqual(new Set(["ICT"]));

  // Lock it: runs and resets go, and the panel lists only the allocated mentors.
  await page.getByRole("button", { name: "Lock", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Lock allocation" }).click();
  await expect(page.getByRole("heading", { name: /Allocation locked/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Auto-allocate" })).toHaveCount(0);
  await expect(page.getByText(`${carried.length} in the allocation`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Replace" })).toHaveCount(carried.length);

  // Unlock again, through its own audited confirmation.
  await page.getByRole("button", { name: "Unlock" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("button", { name: "Auto-allocate" })).toBeVisible();
});

test("a coordinator cannot open another module's allocation", async ({ page }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);
  const programs = await apiGet<{ id: number; type: string; department_id: number }[]>(
    page, "/internships/programs",
  );
  const summer = programs.find((p) => p.type === "SUMMER")!;
  const token = await page.evaluate(() => localStorage.getItem("campushub.access"));
  const response = await page.request.get(`/api/v1/internships/programs/${summer.id}/mentors-capacity`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(403);
});

test("an unconfirmed cap is flagged, and confirming it is what the allocator then uses", async ({ page }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);
  const portfolio = page.getByRole("article").filter({ hasText: "CSSI coordination" });
  await portfolio.getByRole("link", { name: "Allocate mentors" }).click();
  const programId = new URL(page.url()).searchParams.get("program_id");

  const notice = page.getByText(/students per mentor is not confirmed/);
  await expect(notice).toBeVisible();
  await page.getByLabel("Students per mentor").fill("12");
  await page.getByRole("button", { name: "Confirm cap" }).click();
  await expect(notice).toBeHidden();

  const loads = await apiGet<MentorLoad[]>(page, `/internships/programs/${programId}/mentors-capacity`);
  expect(new Set(loads.map((m) => m.max_capacity))).toEqual(new Set([12]));
});
