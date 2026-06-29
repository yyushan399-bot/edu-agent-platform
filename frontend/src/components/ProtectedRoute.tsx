/** 路由守卫：未登录跳转登录页，角色不匹配显示无权限 */
import { Navigate } from "react-router-dom";
import { useAuth } from "../api/auth";

interface Props {
  children: React.ReactNode;
  roles?: string[];
}

export default function ProtectedRoute({ children, roles }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900 text-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4" />
          <p className="text-slate-400">加载中...</p>
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900 text-white">
        <div className="text-center px-6">
          <h1 className="text-2xl font-bold text-red-400 mb-2">权限不足</h1>
          <p className="text-slate-400 mb-2">当前角色无权访问此页面</p>
          <p className="text-slate-500 text-sm">
            当前身份：{user.role} · 需要：{roles.join(" / ")}
          </p>
          <p className="text-slate-500 text-xs mt-4">
            请确认登录时选择的角色与账号一致，或先退出后重新登录
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
