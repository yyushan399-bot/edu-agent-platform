/** 404 页面 */
import { Link } from "react-router-dom";
import { useAuth } from "../api/auth";
import { roleHomePath } from "../utils/evaluation";

export default function NotFoundPage() {
  const { user } = useAuth();
  const home = user ? roleHomePath(user.role) : "/login";

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-6">
      <div className="text-center text-white">
        <p className="text-7xl font-bold text-blue-400 mb-2">404</p>
        <h1 className="text-xl font-semibold mb-2">页面不存在</h1>
        <p className="text-slate-400 text-sm mb-8">您访问的地址无效或已被移除</p>
        <Link
          to={home}
          className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          <i className="fa-solid fa-house" />
          {user ? "返回控制台" : "返回登录"}
        </Link>
      </div>
    </div>
  );
}
