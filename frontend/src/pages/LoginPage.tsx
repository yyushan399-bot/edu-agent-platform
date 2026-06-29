/** 登录页 —— 左右分栏卡片风格 */
import { useState, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
import StudentRegisterModal from "../components/StudentRegisterModal";
import { roleHomePath } from "../utils/evaluation";

const ROLES = [
  { value: "group_member", label: "小组成员 (Student)" },
  { value: "group_leader", label: "项目组长 (Group Leader)" },
  { value: "teacher", label: "授课教师 (Teacher)" },
  { value: "admin", label: "系统管理员 (Administrator)" },
];

const ORBIT_ICONS = [
  { icon: "fa-users", color: "bg-emerald-400", style: { top: "8%", left: "18%" } },
  { icon: "fa-lightbulb", color: "bg-amber-400", style: { top: "6%", right: "16%" } },
  { icon: "fa-chart-line", color: "bg-sky-400", style: { bottom: "22%", left: "8%" } },
  { icon: "fa-book-open", color: "bg-violet-400", style: { bottom: "18%", right: "10%" } },
  { icon: "fa-robot", color: "bg-rose-400", style: { top: "42%", left: "4%" } },
  { icon: "fa-folder-open", color: "bg-teal-400", style: { top: "38%", right: "6%" } },
];

function LoginIllustration() {
  return (
    <div className="relative mx-auto my-6 h-52 w-full max-w-[280px]">
      <div className="absolute inset-0 rounded-full border border-white/20 bg-white/5" />
      <div className="absolute inset-6 rounded-full border border-dashed border-white/25" />

      {ORBIT_ICONS.map(({ icon, color, style }) => (
        <div
          key={icon}
          className={`absolute flex h-9 w-9 items-center justify-center rounded-full ${color} text-white text-sm shadow-lg`}
          style={style}
        >
          <i className={`fa-solid ${icon}`} />
        </div>
      ))}

      <div className="absolute left-1/2 top-1/2 w-[200px] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white p-4 shadow-2xl">
        <div className="mb-3 flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-rose-400" />
          <div className="h-2 w-2 rounded-full bg-amber-400" />
          <div className="h-2 w-2 rounded-full bg-emerald-400" />
        </div>
        <div className="mb-2 h-2 w-3/4 rounded bg-slate-100" />
        <div className="flex h-16 items-end gap-1.5">
          <div className="h-8 w-4 rounded-sm bg-indigo-300" />
          <div className="h-12 w-4 rounded-sm bg-indigo-400" />
          <div className="h-6 w-4 rounded-sm bg-indigo-300" />
          <div className="h-14 w-4 rounded-sm bg-indigo-500" />
          <div className="h-10 w-4 rounded-sm bg-indigo-400" />
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  const { login, user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [studentId, setStudentId] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerSuccess, setRegisterSuccess] = useState("");

  useEffect(() => {
    if (authLoading || !user) return;
    navigate(roleHomePath(user.role), { replace: true });
  }, [authLoading, user, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!studentId || !password || !role) {
      setError("请完整填写所有必填信息");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const loggedInUser = await login(studentId, password, role);
      navigate(roleHomePath(loggedInUser.role), { replace: true });
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax.response?.data?.detail || "学号或密码错误，请重试");
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    "w-full rounded-lg border border-slate-200 bg-slate-50 py-3 text-sm text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20";

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#eef1f7] p-4 md:p-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-indigo-200/40 blur-3xl" />
        <div className="absolute -bottom-24 -right-24 h-96 w-96 rounded-full bg-blue-200/35 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, #c7d2fe 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      <div className="relative z-10 flex w-full max-w-[980px] flex-col overflow-hidden rounded-2xl bg-white shadow-[0_24px_64px_rgba(99,102,241,0.14)] lg:min-h-[620px] lg:flex-row">
        {/* 左侧品牌区 */}
        <div className="relative hidden overflow-hidden bg-gradient-to-br from-indigo-600 via-indigo-500 to-blue-500 p-10 text-white lg:flex lg:w-[44%] lg:flex-col lg:justify-between">
          <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10" />
          <div className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-white/10" />

          <div className="relative">
            <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur-sm">
              <i className="fa-solid fa-graduation-cap text-xl" />
            </div>
            <h2 className="text-2xl font-bold leading-snug">
              项目化学习系统
            </h2>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-indigo-100/90">
              支持项目节点提交、团队协作与 AI 智能评价，助力 PBL 教学全流程管理。
            </p>
          </div>

          <LoginIllustration />

          <p className="relative text-xs tracking-[0.2em] text-indigo-200/80">
            智能评价 · 协作学习 · 数据驱动
          </p>
        </div>

        {/* 右侧登录表单 */}
        <div className="flex flex-1 flex-col justify-center px-8 py-10 md:px-12">
          <div className="mb-8">
            <div className="mb-1 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-lg text-indigo-600 lg:hidden">
                <i className="fa-solid fa-graduation-cap" />
              </div>
              <h1 className="text-2xl font-bold tracking-wide text-slate-800">
                项目化学习系统
              </h1>
            </div>
            <p className="text-sm text-slate-400 lg:ml-[52px]">Project-Based Learning Platform</p>
          </div>

          <div className="mb-6 border-b border-slate-100">
            <span className="inline-block border-b-2 border-indigo-600 pb-3 text-sm font-semibold text-indigo-600">
              账号登录
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                学号 / 工号
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value)}
                  placeholder="请输入唯一学工号账户"
                  className={`${inputClass} pl-10 pr-4`}
                  required
                />
                <i className="fa-solid fa-id-card absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                登录密码
              </label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入您的系统密码"
                  className={`${inputClass} pl-10 pr-10`}
                  required
                />
                <i className="fa-solid fa-lock absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-indigo-600"
                >
                  <i className={`fa-solid ${showPwd ? "fa-eye-slash" : "fa-eye"}`} />
                </button>
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600">
                系统访问权限角色
              </label>
              <div className="relative">
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className={`${inputClass} cursor-pointer appearance-none pl-10 pr-10`}
                  required
                >
                  <option value="" disabled>
                    请选择您的登录身份权限
                  </option>
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <i className="fa-solid fa-user-shield absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
                <i className="fa-solid fa-chevron-down pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
              </div>
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-center text-sm text-red-500">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 py-3 font-bold text-white shadow-lg shadow-indigo-500/25 transition-all hover:bg-indigo-700 hover:shadow-indigo-500/35 active:scale-[0.99] disabled:opacity-50"
            >
              <span>{loading ? "登录中..." : "进入控制台"}</span>
              <i className="fa-solid fa-arrow-right" />
            </button>

            <button
              type="button"
              onClick={() => {
                setRegisterSuccess("");
                setRegisterOpen(true);
              }}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 py-3 text-sm font-medium text-slate-600 transition-colors hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600"
            >
              <i className="fa-solid fa-user-plus" />
              注册学生账号
            </button>
          </form>

          {registerSuccess && (
            <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
              <i className="fa-solid fa-circle-check mr-2" />
              {registerSuccess}
            </div>
          )}
        </div>
      </div>

      <StudentRegisterModal
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        onSuccess={(studentId, userName) => {
          setStudentId(studentId);
          setRole("group_member");
          setRegisterSuccess(
            `注册成功！${userName}（学号 ${studentId}），请使用「小组成员」身份登录。`
          );
        }}
      />
    </div>
  );
}
