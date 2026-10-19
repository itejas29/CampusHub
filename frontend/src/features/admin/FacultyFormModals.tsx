import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, Input, Select } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";
import { emailError, personNameError, phoneError } from "@/lib/validation";
import type { DepartmentRow, FacultyRow } from "@/types";

export function AddFacultyModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [employeeCode, setEmployeeCode] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [designation, setDesignation] = useState("Assistant Professor");
  const [cabin, setCabin] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("Campus@123");
  const [error, setError] = useState<string | null>(null);

  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<DepartmentRow[]>("/departments"),
  });

  // Set default department once loaded
  useEffect(() => {
    if (departments.data?.length && !departmentId) {
      setDepartmentId(String(departments.data[0].id));
    }
  }, [departments.data, departmentId]);

  // Once demo accounts are off the server issues a one-time password instead
  // of the one typed here, and returns it once.
  const [issued, setIssued] = useState<string | null>(null);
  const addFaculty = useMutation({
    mutationFn: () =>
      api.post<{ temporary_password?: string | null }>("/faculty", {
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        employee_code: employeeCode.trim().toUpperCase(),
        department_id: Number(departmentId),
        designation,
        cabin: cabin.trim() || null,
        specialization: specialization.trim() || null,
        public_phone: phone.trim() || null,
        public_email: email.trim().toLowerCase(),
        password: password || null,
        is_mentor: true,
      }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["faculty-admin"] });
      void queryClient.invalidateQueries({ queryKey: ["faculty"] });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      if (created.temporary_password) setIssued(created.temporary_password);
      else onDone();
    },

    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to add faculty member.");
    },
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add New Teacher / Faculty"
      description="Create a faculty account with academic credentials and contact details."
      size="md"
      footer={issued ? (
        <Button size="sm" onClick={() => { setIssued(null); onDone(); }}>Done</Button>
      ) : (
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            loading={addFaculty.isPending}
            disabled={!fullName.trim() || !email.trim() || !employeeCode.trim() || !departmentId
              || Boolean(personNameError(fullName) || phoneError(phone) || emailError(email))}
            icon={<Plus className="h-4 w-4" />}
            onClick={() => addFaculty.mutate()}
          >
            Create Faculty
          </Button>
        </>
      )}
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        {issued && (
          <Alert variant="success" title="Account created — one-time password">
            <code className="font-semibold tracking-wider">{issued}</code> · shown once. Give it to
            {" "}{fullName.trim()} in person or by phone; they choose their own at first sign-in.
          </Alert>
        )}


        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Full Name" required error={personNameError(fullName)}>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Dr. Aryan Sharma"
              required
            />
          </FormField>
          <FormField label="Employee Code" required>
            <Input
              value={employeeCode}
              onChange={(e) => setEmployeeCode(e.target.value)}
              placeholder="e.g. ICT-F-108"
              required
            />
          </FormField>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="University Email" required error={emailError(email)}>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. aryan.sharma@campushub.example.com"
              required
            />
          </FormField>
          <FormField label="Department" required>
            <Select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              required
            >
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code} — {d.name}
                </option>
              ))}
            </Select>
          </FormField>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Designation" required>
            <Select value={designation} onChange={(e) => setDesignation(e.target.value)}>
              <option value="Assistant Professor">Assistant Professor</option>
              <option value="Associate Professor">Associate Professor</option>
              <option value="Professor">Professor</option>
              <option value="Visiting Faculty">Visiting Faculty</option>
              <option value="Lecturer">Lecturer</option>
            </Select>
          </FormField>
          <FormField label="Cabin / Office Room">
            <Input
              value={cabin}
              onChange={(e) => setCabin(e.target.value)}
              placeholder="e.g. 6-209"
            />
          </FormField>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Specialization / Research Area">
            <Input
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
              placeholder="e.g. Artificial Intelligence, Cloud"
            />
          </FormField>
          <FormField label="Contact Phone" error={phoneError(phone)}>
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="e.g. 98765 43210"
            />
          </FormField>
        </div>

        <FormField
          label="Temporary Password"
          hint="Used only while demo accounts are on. Otherwise the portal issues a one-time password the person replaces at first sign-in."
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Campus@123"
          />
        </FormField>
      </div>
    </Modal>
  );
}

export function EditFacultyModal({
  open,
  member,
  onClose,
  onDone,
}: {
  open: boolean;
  member: FacultyRow;
  onClose: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(member.full_name);
  const [designation, setDesignation] = useState(member.designation);
  const [cabin, setCabin] = useState(member.cabin ?? "");
  const [specialization, setSpecialization] = useState(member.specialization ?? "");
  const [phone, setPhone] = useState(member.public_phone ?? "");
  const [publicEmail, setPublicEmail] = useState(member.public_email ?? member.email);
  const [error, setError] = useState<string | null>(null);

  const updateFaculty = useMutation({
    mutationFn: () =>
      api.patch(`/faculty/${member.id}`, {
        full_name: fullName.trim(),
        designation,
        cabin: cabin.trim() || null,
        specialization: specialization.trim() || null,
        public_phone: phone.trim() || null,
        public_email: publicEmail.trim().toLowerCase() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["faculty-admin"] });
      void queryClient.invalidateQueries({ queryKey: ["faculty"] });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      onDone();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to update faculty member.");
    },
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit Faculty: ${member.full_name}`}
      description={`Update profile details for ${member.employee_code}.`}
      size="md"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            loading={updateFaculty.isPending}
            disabled={!fullName.trim() || Boolean(personNameError(fullName) || phoneError(phone) || emailError(publicEmail))}
            onClick={() => updateFaculty.mutate()}
          >
            Save Changes
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Full Name" required error={personNameError(fullName)}>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </FormField>
          <FormField label="Designation" required>
            <Select value={designation} onChange={(e) => setDesignation(e.target.value)}>
              <option value="Assistant Professor">Assistant Professor</option>
              <option value="Associate Professor">Associate Professor</option>
              <option value="Professor">Professor</option>
              <option value="Visiting Faculty">Visiting Faculty</option>
              <option value="Lecturer">Lecturer</option>
            </Select>
          </FormField>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Cabin / Office">
            <Input
              value={cabin}
              onChange={(e) => setCabin(e.target.value)}
              placeholder="e.g. 6-207"
            />
          </FormField>
          <FormField label="Contact Phone" error={phoneError(phone)}>
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="e.g. 98765 43210"
            />
          </FormField>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Specialization">
            <Input
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
              placeholder="e.g. Data Structures, Cloud Computing"
            />
          </FormField>
          <FormField label="Public Contact Email" error={emailError(publicEmail)}>
            <Input
              type="email"
              value={publicEmail}
              onChange={(e) => setPublicEmail(e.target.value)}
            />
          </FormField>
        </div>
      </div>
    </Modal>
  );
}

export function DeleteFacultyModal({
  open,
  member,
  onClose,
  onDone,
}: {
  open: boolean;
  member: FacultyRow;
  onClose: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const deleteFaculty = useMutation({
    mutationFn: () => api.delete(`/faculty/${member.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["faculty-admin"] });
      void queryClient.invalidateQueries({ queryKey: ["faculty"] });
      void queryClient.invalidateQueries({ queryKey: ["mentor-capacity"] });
      onDone();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to deactivate faculty.");
    },
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Deactivate Faculty Member"
      description="This will deactivate the faculty account and mark them inactive."
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            loading={deleteFaculty.isPending}
            icon={<Trash2 className="h-4 w-4" />}
            onClick={() => deleteFaculty.mutate()}
          >
            Deactivate Faculty
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <div className="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger-soft p-3.5 text-xs text-danger">
          <AlertTriangle className="h-4 w-4 shrink-0 text-danger" />
          <p>
            Are you sure you want to deactivate <strong>{member.full_name}</strong> ({member.employee_code})?
            Their portal login will be disabled.
          </p>
        </div>
      </div>
    </Modal>
  );
}
