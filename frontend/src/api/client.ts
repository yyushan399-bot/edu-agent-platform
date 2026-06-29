/** API 客户端封装 */
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截器：自动附加 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：401 仅对「当前 token」生效，避免旧请求误清会话
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const url = String(err.config?.url ?? "");
    const isLoginRequest = url.includes("/auth/login") || url.includes("/auth/register");

    if (status === 401 && !isLoginRequest) {
      const requestAuth = err.config?.headers?.Authorization as string | undefined;
      const requestToken = requestAuth?.replace(/^Bearer\s+/i, "") ?? "";
      const currentToken = localStorage.getItem("token") ?? "";

      // 旧 token 的 401 不应清掉刚登录的新会话
      if (currentToken && requestToken === currentToken) {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

export default api;

// ── 类型定义 ──────────────────────────────────────────

export interface User {
  id: number;
  student_id: string;
  name: string;
  role: "teacher" | "admin" | "group_leader" | "group_member";
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  student_id: string;
  password: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface StudentRegisterResponse {
  message: string;
  user: User;
}

export interface Project {
  id: number;
  title: string;
  description?: string;
  deadline?: string;
  group_size?: number;
  created_by: number;
  created_at: string;
  nodes: ProjectNode[];
}

export interface ProjectNode {
  id: number;
  name: string;
  deadline?: string;
  order: number;
}

export interface Group {
  id: number;
  name: string;
  project_id?: number;
  leader_id?: number;
  members: GroupMember[];
  created_at: string;
}

export interface GroupMember {
  id: number;
  user_id: number;
  user?: User;
}

export interface Submission {
  id: number;
  user_id: number;
  node_id: number;
  file_path?: string;
  text_content?: string;
  status: string;
  submitted_at: string;
  user?: User;
  node?: ProjectNode;
}

export interface Evaluation {
  id: number;
  dim_key: string;
  scores?: Record<string, number>;
  feedbacks?: Record<string, string>;
  summary?: string;
  dimension_score?: number;
}

export interface MetaReport {
  total_score?: number;
  report_content?: string;
}

export interface EvaluationDetail {
  submission: Submission;
  evaluations: Evaluation[];
  meta_report?: MetaReport;
}

// ── API 方法 ──────────────────────────────────────────

export interface ChatMessage {
  message_id: string;
  role: string;
  content: string;
  timestamp: string;
  session_id?: string;
  session_title?: string;
  meta?: Record<string, unknown>;
}

export interface StudentChatResponse {
  success: boolean;
  student_id: string;
  session_count: number;
  empty_session_count?: number;
  message_count: number;
  messages: ChatMessage[];
}

export const teacherChatApi = {
  getStudentMessages: (studentId: string, limit = 300) =>
    api.get<StudentChatResponse>(`/teacher/students/${encodeURIComponent(studentId)}/chat-messages`, {
      params: { limit },
    }),
};

export const authApi = {
  login: (data: LoginRequest) => api.post<LoginResponse>("/auth/login", data),
  registerStudent: (data: { student_id: string; name: string; password: string }) =>
    api.post<StudentRegisterResponse>("/auth/register-student", data),
  register: (data: { student_id: string; name: string; password: string; role: string }) =>
    api.post<User>("/auth/register", data),
  me: () => api.get<User>("/auth/me"),
};

export const usersApi = {
  list: () => api.get<User[]>("/users/"),
  create: (data: { student_id: string; name: string; password: string; role: string }) =>
    api.post<User>("/users/", data),
  update: (id: number, data: Record<string, unknown>) =>
    api.patch<User>(`/users/${id}`, data),
  delete: (id: number) => api.delete(`/users/${id}`),
  resetPassword: (id: number, password: string) =>
    api.post<User>(`/users/${id}/reset-password`, { new_password: password }),
};

export const projectsApi = {
  list: () => api.get<Project[]>("/projects/"),
  create: (data: {
    title: string;
    description?: string;
    deadline?: string;
    group_size?: number;
  }) => api.post<Project>("/projects/", data),
  get: (id: number) => api.get<Project>(`/projects/${id}`),
  createNode: (projectId: number, data: { name: string; deadline?: string; order: number }) =>
    api.post(`/projects/${projectId}/nodes`, null, { params: data }),
};

export const groupsApi = {
  list: (projectId?: number) =>
    api.get<Group[]>("/groups/", {
      params: projectId != null ? { project_id: projectId } : undefined,
    }),
  create: (data: {
    name: string;
    leader_student_id: string;
    member_student_ids: string[];
    project_id?: number;
  }) => api.post<Group>("/groups/", data),
  importSpreadsheet: (projectId: number, file: File, replaceExisting = true) => {
    const form = new FormData();
    form.append("project_id", String(projectId));
    form.append("replace_existing", String(replaceExisting));
    form.append("file", file);
    return api.post<{ created: number; message: string; groups: Group[] }>(
      "/groups/import-spreadsheet",
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
  },
  delete: (id: number) => api.delete(`/groups/${id}`),
  addMember: (groupId: number, userId: number) =>
    api.post(`/groups/${groupId}/members`, null, { params: { user_id: userId } }),
  removeMember: (groupId: number, userId: number) =>
    api.delete(`/groups/${groupId}/members/${userId}`),
};

// ── 互评 ──────────────────────────────────────────

export interface PeerAssessmentResult {
  id: number;
  reviewer_id: number;
  target_user_id: number;
  ai_analyze_submission_id?: number | null;
  score: number;
  comment: string | null;
  created_at: string | null;
}

export interface PeerReviewAssignment {
  item_type: "ai_analyze";
  ai_analyze_submission_id: number;
  target_user_id: number;
  student_name: string;
  node_name: string;
  has_file: boolean;
  file_name?: string | null;
  file_download_url?: string | null;
  text_preview?: string | null;
  self_score?: number | null;
  ai_total_score?: number | null;
  submit_time: string | null;
  my_review?: PeerAssessmentResult | null;
}

export interface SubmitPeerReviewResponse {
  success: boolean;
  peer_assessment: PeerAssessmentResult;
}

export interface PeerReviewAssignmentsResponse {
  count: number;
  items: PeerReviewAssignment[];
}

export const peerReviewApi = {
  listAssignments: (projectId: number) =>
    api.get<PeerReviewAssignmentsResponse>("/peer-review/assignments", {
      params: { project_id: projectId },
    }),
  submit: (data: { ai_analyze_submission_id: number; score: number; comment?: string }) =>
    api.post<SubmitPeerReviewResponse>("/peer-review/submit", data),
  listTeacher: (params?: { project_id?: number; group_id?: number; limit?: number }) =>
    api.get<TeacherPeerReviewListResponse>("/peer-review/teacher", { params }),
};

export interface TeacherPeerReviewRecord {
  id: number;
  reviewer_id: number;
  reviewer_name: string;
  reviewer_student_id: string;
  target_user_id: number;
  target_name: string;
  target_student_id: string;
  submission_id: number;
  node_name: string;
  project_id: number;
  project_title: string;
  group_id?: number | null;
  group_name?: string | null;
  score: number;
  comment?: string | null;
  file_name?: string | null;
  created_at: string;
}

export interface TeacherPeerReviewListResponse {
  count: number;
  items: TeacherPeerReviewRecord[];
}

export const submissionsApi = {
  list: (nodeId?: number) =>
    api.get<Submission[]>("/submissions/", { params: { node_id: nodeId } }),
  create: (data: FormData) =>
    api.post<Submission>("/submissions/", data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  delete: (id: number) => api.delete(`/submissions/${id}`),
  groupSubmissions: (groupId: number) =>
    api.get<Submission[]>(`/submissions/group/${groupId}`),
};

export const aiAnalyzeSubmissionsApi = {
  downloadFile: async (submissionId: number, filename: string) => {
    const { data } = await api.get<Blob>(`/ai-analyze-submissions/${submissionId}/file`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "作业文件";
    anchor.click();
    URL.revokeObjectURL(url);
  },
};

export const evaluationsApi = {
  getDetail: (submissionId: number) =>
    api.get<EvaluationDetail>(`/evaluations/submission/${submissionId}`),
  getReport: (submissionId: number) =>
    api.get<MetaReport>(`/evaluations/submission/${submissionId}/report`),
  run: (submissionId: number) =>
    api.post(`/evaluations/run/${submissionId}`),
};

export interface GroupPblDimension {
  dimension_key?: string;
  dimension_name?: string;
  primary_indicator?: string;
  agent_key?: string;
  mean?: number;
  summary_comment?: string;
  teacher_override?: boolean;
  audit_failed?: boolean;
}

export interface TeacherInterventionRecord {
  id: number;
  group_id?: number;
  group_name?: string;
  project_id?: number | null;
  project_title?: string | null;
  student_id: string;
  filename?: string;
  file_path?: string | null;
  has_document?: boolean;
  report_text_preview?: string | null;
  created_at?: string;
  audit_passed: boolean;
  max_review_rounds_reached: boolean;
  needs_teacher_intervention: boolean;
  teacher_reviewed: boolean;
  teacher_intervention_note?: string;
  final_score?: number;
  dimension_mean_score?: number;
  dimension_summary: GroupPblDimension[];
  failed_dimension_views?: GroupPblDimension[];
  primary_indicator_summary: Array<Record<string, unknown>>;
  final_comment?: string;
  teacher_modified?: boolean;
  internal_audit?: Record<string, unknown>;
}

export const teacherInterventionApi = {
  listPending: () => api.get<TeacherInterventionRecord[]>("/teacher/intervention/pending"),
  listEvaluations: () => api.get<TeacherInterventionRecord[]>("/teacher/intervention/evaluations"),
  approve: (evaluationId: number, data?: { note?: string }) =>
    api.post<{ success: boolean; message: string; record: TeacherInterventionRecord }>(
      `/teacher/intervention/${evaluationId}/approve`,
      data ?? {}
    ),
  patchScores: (
    evaluationId: number,
    data: { dimension_scores: { dimension_name: string; mean: number }[]; note?: string }
  ) => api.patch<TeacherInterventionRecord>(`/teacher/intervention/${evaluationId}/scores`, data),
};

export interface GroupPblLatestResponse {
  has_evaluation: boolean;
  scores_visible?: boolean;
  scores_hidden_reason?: string;
  [key: string]: unknown;
}


export const groupPblApi = {
  getMyLatest: (projectId: number) =>
    api.get<GroupPblLatestResponse>("/group-pbl/my-latest", { params: { project_id: projectId } }),
  downloadReportFile: async (evaluationId: number, filename: string) => {
    const { data } = await api.get<Blob>(`/group-pbl/evaluations/${evaluationId}/report-file`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "小组报告";
    anchor.click();
    URL.revokeObjectURL(url);
  },
};
