/** 组长/组员登录后：选择教师发布的项目 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
import { groupsApi, projectsApi, type Group, type Project } from "../api/client";
import { findUserGroupForProject, formatDateTime } from "../utils/dashboard";

interface Props {
  role: "group_leader" | "group_member";
}

export default function StudentProjectPortal({ role }: Props) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const basePath = role === "group_leader" ? "/leader" : "/member";
  const roleLabel = role === "group_leader" ? "组长" : "组员";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [{ data: projData }, { data: groupData }] = await Promise.all([
        projectsApi.list(),
        groupsApi.list(),
      ]);
      setProjects(projData);
      setGroups(groupData);
    } catch {
      setError("加载项目列表失败，请刷新重试");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const enriched = useMemo(
    () =>
      projects.map((p) => ({
        project: p,
        myGroup: user ? findUserGroupForProject(groups, user.id, p.id) : undefined,
      })),
    [projects, groups, user]
  );

  const enterProject = (projectId: number) => {
    navigate(`${basePath}/project/${projectId}`);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm px-8 py-4 border-b border-slate-200">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-blue-900 flex items-center gap-2">
            <i className="fa-solid fa-graduation-cap" />
            项目化学习系统
          </h1>
          <div className="flex items-center gap-4">
            <span className="bg-blue-50 text-blue-700 px-4 py-2 rounded-full text-sm font-semibold border border-blue-200">
              <i className="fa-solid fa-user mr-2" />
              {user?.name} · {roleLabel}
            </span>
            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="text-sm text-slate-500 hover:text-red-500"
            >
              <i className="fa-solid fa-right-from-bracket mr-1" />
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-blue-900">选择项目</h2>
          <p className="text-slate-500 text-sm mt-2">
            请选择教师发布的项目化学习任务，进入后即可查看节点、提交成果并使用 AI 评价功能。
          </p>
        </div>

        {loading && (
          <p className="text-center text-slate-500 py-16">
            <i className="fa-solid fa-spinner fa-spin mr-2" />
            加载项目列表...
          </p>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm mb-6">
            {error}
            <button type="button" onClick={() => void load()} className="ml-3 underline">
              重试
            </button>
          </div>
        )}

        {!loading && !error && enriched.length === 0 && (
          <div className="text-center py-16 bg-white rounded-xl border border-dashed border-slate-300">
            <i className="fa-solid fa-folder-open text-4xl text-slate-300 mb-4" />
            <p className="text-slate-500">暂无教师发布的项目</p>
            <p className="text-slate-400 text-sm mt-2">请等待授课教师发布项目后再进入</p>
          </div>
        )}

        {!loading && enriched.length > 0 && (
          <div className="space-y-4">
            {enriched.map(({ project, myGroup }) => (
              <article
                key={project.id}
                className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 hover:border-blue-200 transition-colors"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-bold text-slate-800">{project.title}</h3>
                    {project.description && (
                      <p className="text-sm text-slate-600 mt-2 line-clamp-3 whitespace-pre-wrap">
                        {project.description}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-3 mt-4 text-xs text-slate-500">
                      <span className="bg-slate-100 px-2.5 py-1 rounded-full">
                        <i className="fa-regular fa-clock mr-1" />
                        截止 {formatDateTime(project.deadline)}
                      </span>
                      {project.group_size ? (
                        <span className="bg-slate-100 px-2.5 py-1 rounded-full">
                          <i className="fa-solid fa-users mr-1" />
                          {project.group_size} 人/组
                        </span>
                      ) : null}
                      <span className="bg-slate-100 px-2.5 py-1 rounded-full">
                        <i className="fa-solid fa-list-check mr-1" />
                        {project.nodes.length} 个节点
                      </span>
                      {myGroup ? (
                        <span className="bg-green-50 text-green-700 px-2.5 py-1 rounded-full border border-green-100">
                          <i className="fa-solid fa-circle-check mr-1" />
                          已分组 · {myGroup.name}
                        </span>
                      ) : (
                        <span className="bg-amber-50 text-amber-700 px-2.5 py-1 rounded-full border border-amber-100">
                          <i className="fa-solid fa-circle-info mr-1" />
                          尚未加入该项目小组
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => enterProject(project.id)}
                    className="shrink-0 px-5 py-2.5 bg-blue-900 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                  >
                    进入项目
                    <i className="fa-solid fa-arrow-right ml-2" />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
