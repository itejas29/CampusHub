import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FormActions, FormField, Input, Textarea } from "@/components/ui/Form";
import { Avatar, DetailList, PageHeader } from "@/components/ui/Misc";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { formatDateTime } from "@/lib/format";
import { humanise, roman } from "@/lib/utils";
import { personNameError, phoneError, textError } from "@/lib/validation";

export function ProfilePage() {
  const { user, refresh } = useAuth();
  const { theme, toggle } = useTheme();
  const queryClient = useQueryClient();

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [cabin, setCabin] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [bio, setBio] = useState("");
  const [banner, setBanner] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<ApiError | null>(null);

  const problems = {
    fullName: personNameError(fullName),
    phone: phoneError(phone),
    cabin: textError(cabin),
    specialization: textError(specialization),
  };
  const hasProblem = Object.values(problems).some(Boolean);

  const saveProfile = useMutation({
    mutationFn: () =>
      api.patch("/me/profile", {
        full_name: fullName || undefined,
        phone: phone || undefined,
        ...(user?.faculty
          ? { cabin: cabin || undefined, specialization: specialization || undefined,
              bio: bio || undefined }
          : {}),
      }),
    onSuccess: async () => {
      setBanner({ tone: "success", text: "Profile updated." });
      await refresh();
      void queryClient.invalidateQueries();
    },
    onError: (err) => setBanner({
      tone: "danger",
      text: err instanceof ApiError ? err.message : "Could not save your profile.",
    }),
  });

  const changePassword = useMutation({
    mutationFn: () =>
      api.post("/auth/change-password", {
        current_password: currentPassword, new_password: newPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordError(null);
      setBanner({ tone: "success", text: "Password updated." });
    },
    onError: (err) => {
      setPasswordError(err instanceof ApiError ? err : null);
      setBanner({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not change your password.",
      });
    },
  });

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

  return (
    <div>
      <PageHeader
        title="Profile & settings"
        description="Your account details, contact information and portal preferences."
        breadcrumbs={[{ label: "Profile" }]}
      />

      {banner && (
        <Alert variant={banner.tone === "success" ? "success" : "danger"} className="mb-4"
               onDismiss={() => setBanner(null)}>
          {banner.text}
        </Alert>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader title="Personal details"
                        description="Editable fields are saved to your account." />
            <CardBody>
              <form
                className="space-y-4"
                onSubmit={(e) => { e.preventDefault(); saveProfile.mutate(); }}
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField label="Full name" error={problems.fullName}>
                    <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
                  </FormField>
                  <FormField label="Phone" error={problems.phone}>
                    <Input value={phone} onChange={(e) => setPhone(e.target.value)}
                           type="tel" inputMode="tel" maxLength={25} placeholder="98765 43210" />
                  </FormField>
                </div>

                {user?.faculty && (
                  <>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField label="Cabin" error={problems.cabin}
                                 hint="Shown to your mentees and internship students.">
                        <Input value={cabin} onChange={(e) => setCabin(e.target.value)}
                               placeholder={user.faculty.cabin ?? "e.g. 6-201 B"} />
                      </FormField>
                      <FormField label="Specialisation" error={problems.specialization}>
                        <Input value={specialization}
                               onChange={(e) => setSpecialization(e.target.value)}
                               placeholder="Research interests" />
                      </FormField>
                    </div>
                    <FormField label="Short bio">
                      <Textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3} />
                    </FormField>
                  </>
                )}

                <FormActions>
                  <Button type="submit" size="sm" loading={saveProfile.isPending} disabled={hasProblem}
                          icon={<Save className="h-3.5 w-3.5" aria-hidden />}>
                    Save changes
                  </Button>
                </FormActions>
              </form>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Change password"
                        icon={<KeyRound className="h-4 w-4 text-ink-subtle" aria-hidden />} />
            <CardBody>
              <form
                className="space-y-4"
                onSubmit={(e) => { e.preventDefault(); changePassword.mutate(); }}
              >
                <FormField label="Current password" required
                           error={passwordError?.fieldError("current_password")}>
                  <Input type="password" value={currentPassword}
                         onChange={(e) => setCurrentPassword(e.target.value)}
                         autoComplete="current-password" />
                </FormField>
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField label="New password" required hint="At least 8 characters."
                             error={passwordError?.fieldError("new_password")}>
                    <Input type="password" value={newPassword}
                           onChange={(e) => setNewPassword(e.target.value)}
                           autoComplete="new-password" />
                  </FormField>
                  <FormField label="Confirm new password" required
                             error={mismatch ? "Passwords do not match." : undefined}>
                    <Input type="password" value={confirmPassword}
                           onChange={(e) => setConfirmPassword(e.target.value)}
                           autoComplete="new-password" />
                  </FormField>
                </div>
                <FormActions>
                  <Button
                    type="submit" size="sm" loading={changePassword.isPending}
                    disabled={
                      !currentPassword || newPassword.length < 8 || mismatch
                    }
                  >
                    Update password
                  </Button>
                </FormActions>
              </form>
            </CardBody>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardBody className="flex flex-col items-center text-center">
              <Avatar name={user?.full_name} src={user?.avatar_url} size="lg" />
              <p className="mt-3 text-md font-semibold text-ink">{user?.full_name}</p>
              <p className="text-xs text-ink-muted">{user?.email}</p>
              <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                {user?.roles.map((role) => (
                  <Badge key={role} tone="brand">{humanise(role)}</Badge>
                ))}
              </div>
            </CardBody>
          </Card>

          {user?.student && (
            <Card>
              <CardHeader title="Academic record" />
              <CardBody>
                <DetailList
                  columns={1}
                  items={[
                    { label: "Roll number", value: <span className="tabular">{user.student.roll_number}</span> },
                    { label: "Programme", value: user.student.program_name },
                    { label: "Department", value: user.student.department_code },
                    { label: "Semester", value: roman(user.student.current_semester) },
                    { label: "Division", value: user.student.division },
                    { label: "Batch", value: user.student.batch },
                    { label: "CPI", value: user.student.cpi?.toFixed(2) },
                    { label: "Backlogs", value: user.student.backlog_count },
                  ]}
                />
                <p className="mt-4 text-2xs text-ink-subtle">
                  Academic records are maintained by the department and cannot be edited here.
                </p>
              </CardBody>
            </Card>
          )}

          {user?.faculty && (
            <Card>
              <CardHeader title="Faculty record" />
              <CardBody>
                <DetailList
                  columns={1}
                  items={[
                    { label: "Employee code", value: <span className="tabular">{user.faculty.employee_code}</span> },
                    { label: "Designation", value: user.faculty.designation },
                    { label: "Department", value: user.faculty.department_code },
                    { label: "Cabin", value: user.faculty.cabin },
                    { label: "Mentor", value: user.faculty.is_mentor ? "Yes" : "No" },
                  ]}
                />
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Preferences" />
            <CardBody className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-ink">Theme</p>
                  <p className="text-xs text-ink-subtle">
                    Currently using the {theme} theme.
                  </p>
                </div>
                <Button variant="secondary" size="sm" onClick={toggle}>
                  Switch to {theme === "dark" ? "light" : "dark"}
                </Button>
              </div>
              <hr className="border-line" />
              <div>
                <p className="flex items-center gap-1.5 text-sm text-ink">
                  <ShieldCheck className="h-3.5 w-3.5 text-success" aria-hidden />
                  Access
                </p>
                <p className="mt-1 text-xs text-ink-subtle">
                  {user?.permissions.length} permission
                  {user?.permissions.length === 1 ? "" : "s"} granted by your role.
                  Every request is checked on the server.
                </p>
                {user?.last_login_at && (
                  <p className="mt-1.5 text-2xs text-ink-subtle">
                    Last signed in {formatDateTime(user.last_login_at)}
                  </p>
                )}
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
