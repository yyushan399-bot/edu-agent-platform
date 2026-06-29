# 🤖 Cursor 接管提示词

## 项目概述

这是一个**教育智能体评价系统**，名叫「智能学伴系统」。同济大学教育技术学研究生小杨的项目。

项目已经搭好了完整的 **FastAPI 后端 + React 前端骨架**，需要用 Cursor 继续完善功能细节。

---

## 项目位置

```
C:\Users\35778\.cursor\projects\empty-window\
```

## 如何启动

```bash
# 终端 1：启动后端
cd C:\Users\35778\.cursor\projects\empty-window
python -m uvicorn backend.main:app --reload --port 8391

# 终端 2：启动前端
cd C:\Users\35778\.cursor\projects\empty-window\frontend
npm run dev
```

前端运行在 http://localhost:5173，Vite 已配置 `/api` 代理到后端 8391 端口。

---

## 后端现状（已完成 ✅）

| 文件 | 说明 |
|------|------|
| `backend/main.py` | FastAPI 入口 |
| `backend/config.py` | 配置加载 |
| `backend/database.py` | 数据库（SQLite，一行改 PostgreSQL） |
| `backend/models.py` | 8 张表：users/projects/project_nodes/groups/group_members/submissions/evaluations/meta_reports |
| `backend/auth.py` | JWT + bcrypt |
| `backend/dependencies.py` | 认证 + 角色守卫（require_role） |
| `backend/schemas.py` | Pydantic 模型 |
| `backend/routers/auth_router.py` | POST /api/auth/login, /register, /me |
| `backend/routers/users_router.py` | CRUD 用户 + 重置密码 |
| `backend/routers/projects_router.py` | CRUD 项目 + 节点管理 + 文件上传 |
| `backend/routers/groups_router.py` | CRUD 小组 + 成员管理 |
| `backend/routers/submissions_router.py` | 提交成果 + 小组提交查询 |
| `backend/routers/evaluations_router.py` | 评估结果查询 + 触发评估 |
| `backend/services/llm_client.py` | LLM 调用（支持 Mock 模式，无 API Key 时返回假数据） |
| `backend/services/evaluation_pipeline.py` | 评分流水线编排 |
| `backend/prompts/` | 小杨已有的 prompt 模板（副本） |
| `backend/rubrics/` | 小杨已有的量规文件（副本） |

### 所有 API 已通过测试（10/10）

## 前端现状（已完成骨架 ✅）

| 文件 | 说明 |
|------|------|
| `frontend/src/api/client.ts` | 全部 API 方法封装 + 类型定义 |
| `frontend/src/api/auth.tsx` | AuthContext（登录/登出/状态） |
| `frontend/src/components/ProtectedRoute.tsx` | 路由守卫 |
| `frontend/src/App.tsx` | React Router 路由，5 个角色页面 |
| `frontend/src/pages/LoginPage.tsx` | 深色毛玻璃登录页 |
| `frontend/src/pages/TeacherDashboard.tsx` | 教师端：项目发布 + 分组管理 + 概览 |
| `frontend/src/pages/AdminDashboard.tsx` | 管理员端：用户管理 |
| `frontend/src/pages/LeaderDashboard.tsx` | 组长端：组员分工 + 时间轴提交 + 报告上传 |
| `frontend/src/pages/MemberDashboard.tsx` | 组员端：时间轴节点提交（文件+文本） |
| `frontend/vite.config.ts` | Vite + Tailwind CSS v4 + API 代理 |

页面风格：
- 登录页：深色毛玻璃（radial gradient + backdrop-blur）
- 教师/管理员端：亮色主题（白 + 蓝）
- 组长/组员端：亮色主题（白 + 时间轴）

---

## 需要完善的地方

### 1. 后端 — 初始数据种子脚本

创建 `backend/seed.py`，提供一键初始化测试数据的命令，包含：

```python
# python -m backend.seed
```

插入的数据：
- 1 个管理员（A001 / admin123）
- 1 个教师（T001 / 12345）
- 3 个学生（组长张华 + 组员李雷、韩梅梅）
- 1 个项目 + 2 个节点
- 1 个小组

### 2. 前端 — 每个页面接入真实数据

目前页面大多还是 Mock 数据，需要接入真实的 API 调用：

#### LoginPage ✅ 已完成（已接 API）
#### TeacherDashboard
- [ ] 项目发布后显示成功提示和刷新列表
- [ ] 分组管理接入 groupsApi
- [ ] 节点管理 UI（目前缺少可视化添加节点）
- [ ] 右侧智能体介入中心接入 evaluationsApi
- [ ] 可以查看已提交的成果列表

#### AdminDashboard
- [ ] 用户管理 ✅ 已完成
- [ ] 添加「分组分工与节点追踪」面板
- [ ] 添加「最终项目报告终审库」面板
- [ ] 添加「形成性评价中心」面板

#### LeaderDashboard
- [ ] 组员列表从 API 获取（groupsApi）
- [ ] 添加节点分工的 UI 完善
- [ ] 成果提交接入 submissionsApi
- [ ] 最终报告上传接入 API

#### MemberDashboard
- [ ] 时间轴节点从 API 获取（projectsApi）
- [ ] 文件上传接入 submissionsApi（FormData）
- [ ] 文本提交接入 submissionsApi
- [ ] 已提交成果列表从 API 获取

### 3. 前端 — 复用原有 HTML 的 CSS 细节

小杨在 `D:\wechat\chat data\xwechat_files\wxid_khek11ihsw7822_14cd\msg\file\2026-06\前端汇总(1)\前端汇总\` 有 5 个 HTML 页面，CSS 写得很精致。建议参考里面的一些细节：

- 教师.html 里的「异常介入中心」卡片交互（接受/修改按钮）
- 管理员.html 里四面板侧边栏切换
- 组长.html 里的自定义节点名称输入
- 组员.html 里的文件列表展示（可删除）

### 4. 评估结果展示

新建 `frontend/src/pages/EvaluationResultPage.tsx`（或作为子路由）：

- 多维度雷达图（用 Chart.js 或 recharts）
- 各维度分数卡片
- 形成性反馈展示
- 元评估综合报告 Markdown 渲染

### 5. 用户体验改进

- 全局 loading 状态（已封装在 ProtectedRoute，但页面内也需要）
- Toast 通知（成功/失败提示）
- 表格分页（如果用户多）
- 404 页面

---

## 技术约束

- **前端**：React 19 + TypeScript + Tailwind CSS v4 + Axios
- **后端**：Python 3.14 + FastAPI + SQLAlchemy 2.0
- **数据库**：开发用 SQLite，上线换 PostgreSQL（改 .env 的 DATABASE_URL）
- **Node.js 路径问题**：npm cache 在 `D:\nodejs\node_cache\` 可能有权限问题，如需安装新 npm 包请设置缓存路径 `npm config set cache "C:\Users\35778\.npm-cache"`
- **后端端口**：开发用 8391（不占用常见端口）

## 代码风格

- 前端组件用函数式 + TypeScript
- Tailwind 原子类，不写自定义 CSS（除非动画等特殊需求）
- API 调用统一走 `src/api/client.ts` 里的封装方法
- 页面文件名用 PascalCase

---

## 小杨的原始前端文件（风格参考）

位置：`D:\wechat\chat data\xwechat_files\wxid_khek11ihsw7822_14cd\msg\file\2026-06\前端汇总(1)\前端汇总\`

这些 HTML 页面有精致的 CSS，React 版本应保留其视觉风格：
- 登录页：深色毛玻璃
- 教师页：亮色 + 左侧两栏布局 + 异常卡片交互
- 管理员页：暗色侧边栏 + 四面板视图
- 组长页：时间轴 + 分工表格 + 文件上传
- 组员页：时间轴 + 选项卡（文件/文本）

---

## 启动后的手工操作

首次启动后端后，需要先注册用户才能登录。可以用 `python -m backend.seed`（写完 seed 脚本后），或者手动调用：

```bash
# 注册管理员
curl -X POST http://127.0.0.1:8391/api/auth/register -H "Content-Type: application/json" -d "{\"student_id\":\"A001\",\"name\":\"管理员\",\"password\":\"admin123\",\"role\":\"admin\"}"
```

---

## 优先级建议

1. 🔥 写 seed.py 数据初始化脚本
2. 🔥 组长端/组员端接入真实 API（核心用户流程）
3. 🔥 教师端接入真实 API
4. 评估结果展示页
5. 管理员端补全剩余面板
6. 改进体验（Toast、Loading、动画）
