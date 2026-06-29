/** 管理员端：选择教师发布的项目后进入各功能模块 */
import { type Project } from "../api/client";
import { formatDateTime } from "../utils/dashboard";

interface Props {
  projects: Project[];
  loading?: boolean;
  groupCountByProject?: Map<number, number>;
  onSelect: (projectId: number) => void;
  hint?: string;
}

export default function AdminProjectPortal({
  projects,
  loading,
  groupCountByProject,
  onSelect,
  hint = "请选择教师发布的项目，进入后可查看该项目下的分组、报告与评价数据。",
}: Props) {
  if (loading) {
    return (
      <p className="text-center text-slate-500 py-16">
        <i className="fa-solid fa-spinner fa-spin mr-2" />
        加载项目列表...
      </p>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="text-center py-16 bg-white rounded-xl border border-dashed border-slate-300">
        <i className="fa-solid fa-folder-open text-4xl text-slate-300 mb-4" />
        <p className="text-slate-500">暂无教师发布的项目</p>
        <p className="text-slate-400 text-sm mt-2">请等待授课教师在教师端创建并发布项目</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-xl font-bold text-slate-800">选择项目</h2>
        <p className="text-slate-500 text-sm mt-2">{hint}</p>
      </div>
      <div className="space-y-4">
        {projects.map((project) => {
          const groupCount = groupCountByProject?.get(project.id) ?? 0;
          return (
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
                    <span
                      className={`px-2.5 py-1 rounded-full border ${
                        groupCount > 0
                          ? "bg-green-50 text-green-700 border-green-100"
                          : "bg-amber-50 text-amber-700 border-amber-100"
                      }`}
                    >
                      <i className="fa-solid fa-diagram-project mr-1" />
                      {groupCount > 0 ? `已导入 ${groupCount} 个小组` : "尚未导入分组"}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelect(project.id)}
                  className="shrink-0 bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
                >
                  进入项目
                  <i className="fa-solid fa-arrow-right ml-2" />
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
