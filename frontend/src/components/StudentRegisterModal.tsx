/** 学生自助注册弹窗 */
import { useState, type FormEvent } from "react";
import { authApi } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: (studentId: string, name: string) => void;
}

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-slate-50 py-3 pl-10 pr-4 text-sm text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20";

export default function StudentRegisterModal({ open, onClose, onSuccess }: Props) {
  const [studentId, setStudentId] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const resetForm = () => {
    setStudentId("");
    setName("");
    setPassword("");
    setConfirmPassword("");
    setError("");
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    const trimmedStudentId = studentId.trim();
    const trimmedName = name.trim();
    if (!trimmedStudentId) {
      setError("请输入学号");
      return;
    }
    if (!trimmedName) {
      setError("请输入姓名");
      return;
    }
    if (password.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    setLoading(true);
    try {
      const { data } = await authApi.registerStudent({
        student_id: trimmedStudentId,
        name: trimmedName,
        password,
      });
      onSuccess(data.user.student_id, data.user.name);
      resetForm();
      onClose();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax.response?.data?.detail || "注册失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-slate-100 bg-white p-8 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-800">学生账号注册</h2>
            <p className="mt-1 text-sm text-slate-400">
              请填写学号与个人信息，注册后管理员与教师可在后台查看
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 text-slate-400 hover:text-slate-600"
          >
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">学号</label>
            <div className="relative">
              <input
                type="text"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                placeholder="请输入您的学号"
                maxLength={32}
                className={inputClass}
                required
              />
              <i className="fa-solid fa-id-card absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">姓名</label>
            <div className="relative">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="请输入真实姓名"
                maxLength={64}
                className={inputClass}
                required
              />
              <i className="fa-solid fa-user absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">登录密码</label>
            <div className="relative">
              <input
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 位"
                minLength={6}
                className={`${inputClass} pr-10`}
                required
              />
              <i className="fa-solid fa-lock absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
              <button
                type="button"
                onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-indigo-600"
              >
                <i className={`fa-solid ${showPwd ? "fa-eye-slash" : "fa-eye"}`} />
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600">确认密码</label>
            <div className="relative">
              <input
                type={showPwd ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="再次输入密码"
                minLength={6}
                className={inputClass}
                required
              />
              <i className="fa-solid fa-lock absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-slate-400" />
            </div>
          </div>

          <p className="text-xs text-slate-400">
            注册身份固定为<strong className="text-slate-600">小组成员</strong>，学号请自行填写且不可重复。
          </p>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-center text-sm text-red-500">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={loading}
              className="flex-1 rounded-lg border border-slate-200 py-3 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 rounded-lg bg-indigo-600 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? "注册中..." : "确认注册"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
