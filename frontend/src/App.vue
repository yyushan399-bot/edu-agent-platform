<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { formatAxiosError, getHealth, postAnalyze } from "./api/analyze";
import { postAssignmentSubmit } from "./api/assignment";
import {
  formatAxiosError as formatPeerError,
  getPeerReviewAssignments,
  submitPeerReview,
} from "./api/peerReview";
import { createSession, getSession, listSessions } from "./api/session";

const STORAGE_KEY = "edu-copilot-active-session";
const STORAGE_USER_ID = "edu-copilot-user-id";
const STORAGE_ASSIGNMENT_ID = "edu-copilot-assignment-id";

const backendOk = ref(null);
const llmConfigured = ref(true);
const deepResearchAvailable = ref(false);

const sessions = ref([]);
const activeSessionId = ref("");
const messages = ref([]);
const sessionsLoading = ref(false);

const fileList = ref([]);
const studentText = ref("");
const studentId = ref("");
const userId = ref("");
const assignmentId = ref("");
const selfScore = ref(75);
const selfComment = ref("");
const routes = ref("");
const enableDeepResearch = ref(false);
const loading = ref(false);
const errorMsg = ref("");
const chatScrollRef = ref(null);
const showSettings = ref(false);
const isDragging = ref(false);

const activeTab = ref("chat");
const peerItems = ref([]);
const peerLoading = ref(false);
const peerDialogVisible = ref(false);
const peerSubmitLoading = ref(false);
const peerForm = ref({
  targetUserId: null,
  assignmentId: null,
  studentName: "",
  score: 80,
  comment: "",
});

const ACCEPT_EXTS = [".pdf", ".docx", ".png", ".jpg", ".jpeg"];
const acceptTypes = ACCEPT_EXTS.join(",");

const activeSession = computed(() =>
  sessions.value.find((s) => s.session_id === activeSessionId.value)
);

const hasFiles = computed(() => fileList.value.length > 0);
const useAssignmentSubmit = computed(
  () => Boolean(userId.value?.toString().trim() && assignmentId.value?.toString().trim())
);
const canSubmit = computed(
  () =>
    activeTab.value === "chat" &&
    activeSessionId.value &&
    (hasFiles.value || studentText.value.trim()) &&
    !loading.value &&
    (!useAssignmentSubmit.value || selfScore.value != null)
);
const canLoadPeer = computed(() => Boolean(userId.value?.toString().trim()));

function formatTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

async function scrollChatToBottom() {
  await nextTick();
  const el = chatScrollRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function mapMessages(rawMessages = []) {
  return rawMessages.map((msg) => ({
    id: msg.message_id || `${msg.timestamp}-${msg.role}`,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp,
    meta: msg.meta || {},
  }));
}

async function refreshSessionList() {
  sessionsLoading.value = true;
  try {
    const data = await listSessions();
    sessions.value = data.sessions || [];
  } catch {
    sessions.value = [];
  } finally {
    sessionsLoading.value = false;
  }
}

async function loadSessionMessages(sessionId) {
  if (!sessionId) {
    messages.value = [];
    return;
  }
  try {
    const data = await getSession(sessionId);
    messages.value = mapMessages(data.messages || []);
    if (data.session?.student_id) {
      studentId.value = data.session.student_id;
    }
    await scrollChatToBottom();
  } catch (err) {
    messages.value = [];
    ElMessage.error(formatAxiosError(err));
  }
}

async function selectSession(sessionId) {
  if (activeSessionId.value === sessionId) return;
  activeSessionId.value = sessionId;
  localStorage.setItem(STORAGE_KEY, sessionId);
  errorMsg.value = "";
  await loadSessionMessages(sessionId);
}

async function handleNewSession() {
  try {
    const data = await createSession({
      studentId: studentId.value,
      title: "新会话",
    });
    const session = data.session;
    if (!session?.session_id) throw new Error("创建会话失败");
    await refreshSessionList();
    activeSessionId.value = session.session_id;
    localStorage.setItem(STORAGE_KEY, session.session_id);
    messages.value = [];
    fileList.value = [];
    studentText.value = "";
    errorMsg.value = "";
    showSettings.value = false;
    ElMessage.success("已新建会话");
  } catch (err) {
    ElMessage.error(formatAxiosError(err));
  }
}

async function bootstrapSessions() {
  await refreshSessionList();
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && sessions.value.some((s) => s.session_id === saved)) {
    await selectSession(saved);
    return;
  }
  if (sessions.value.length > 0) {
    await selectSession(sessions.value[0].session_id);
    return;
  }
  await handleNewSession();
}

function onUploadChange(_uploadFile, uploadFiles) {
  fileList.value = uploadFiles;
}

function onUploadRemove(_file, uploadFiles) {
  fileList.value = uploadFiles;
}

function isAllowedFile(file) {
  const name = (file?.name || "").toLowerCase();
  return ACCEPT_EXTS.some((ext) => name.endsWith(ext));
}

function addRawFiles(files) {
  const incoming = Array.from(files || []);
  if (!incoming.length) return;

  const existing = new Set(
    fileList.value.map((item) => `${item.name}-${item.raw?.size}`)
  );
  let added = 0;

  for (const raw of incoming) {
    if (!isAllowedFile(raw)) {
      ElMessage.warning(`不支持的文件类型: ${raw.name}`);
      continue;
    }
    const key = `${raw.name}-${raw.size}`;
    if (existing.has(key)) continue;
    existing.add(key);
    fileList.value.push({
      name: raw.name,
      raw,
      uid: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      status: "ready",
    });
    added += 1;
  }

  if (added > 0) {
    ElMessage.success(`已添加 ${added} 个文件`);
  }
}

function onDragEnter(e) {
  if (loading.value) return;
  if (!e.dataTransfer?.types?.includes("Files")) return;
  isDragging.value = true;
}

function onDragLeave(e) {
  if (loading.value) return;
  const related = e.relatedTarget;
  const current = e.currentTarget;
  if (related && current instanceof Node && current.contains(related)) {
    return;
  }
  isDragging.value = false;
}

function onDragOver(e) {
  if (loading.value) return;
  if (!e.dataTransfer?.types?.includes("Files")) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
  isDragging.value = true;
}

function onDrop(e) {
  e.preventDefault();
  isDragging.value = false;
  if (loading.value) return;
  addRawFiles(e.dataTransfer?.files);
}

function removeFile(file) {
  fileList.value = fileList.value.filter((item) => item.uid !== file.uid);
}

function clearComposer() {
  fileList.value = [];
  studentText.value = "";
  errorMsg.value = "";
}

function resolveFileUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return url.startsWith("/") ? url : `/${url}`;
}

async function loadPeerAssignments() {
  if (!canLoadPeer.value) {
    ElMessage.warning("请先在设置中填写用户 ID");
    showSettings.value = true;
    return;
  }
  peerLoading.value = true;
  try {
    const data = await getPeerReviewAssignments(Number(userId.value));
    peerItems.value = data.items || [];
    if (!peerItems.value.length) {
      ElMessage.info("暂无同组成员待互评作业");
    }
  } catch (err) {
    ElMessage.error(formatPeerError(err));
    peerItems.value = [];
  } finally {
    peerLoading.value = false;
  }
}

function openPeerDialog(item) {
  peerForm.value = {
    targetUserId: item.target_user_id,
    assignmentId: item.assignment_id,
    studentName: item.student_name,
    score: 80,
    comment: "",
  };
  peerDialogVisible.value = true;
}

async function handlePeerSubmit() {
  if (!canLoadPeer.value) return;
  peerSubmitLoading.value = true;
  try {
    await submitPeerReview({
      reviewerId: Number(userId.value),
      targetUserId: peerForm.value.targetUserId,
      assignmentId: peerForm.value.assignmentId,
      score: peerForm.value.score,
      comment: peerForm.value.comment,
    });
    ElMessage.success("互评提交成功");
    peerDialogVisible.value = false;
    await loadPeerAssignments();
  } catch (err) {
    ElMessage.error(formatPeerError(err));
  } finally {
    peerSubmitLoading.value = false;
  }
}

function switchTab(tab) {
  activeTab.value = tab;
  errorMsg.value = "";
  if (tab === "peer") {
    loadPeerAssignments();
  }
}

async function handleSubmit() {
  if (!canSubmit.value) {
    if (useAssignmentSubmit.value && !userId.value) {
      ElMessage.warning("作业提交模式需填写用户 ID 与作业 ID");
      showSettings.value = true;
      return;
    }
    ElMessage.warning("请选择会话并上传文件或输入内容");
    return;
  }

  loading.value = true;
  errorMsg.value = "";

  try {
    const files = fileList.value
      .map((item) => item.raw)
      .filter((f) => f instanceof File);

    const payload = {
      files,
      text: studentText.value,
      studentId: studentId.value,
      sessionId: activeSessionId.value,
      routes: routes.value,
      memoryK: 3,
      enableDeepResearch: enableDeepResearch.value,
    };

    let data;
    if (useAssignmentSubmit.value) {
      data = await postAssignmentSubmit(Number(assignmentId.value), {
        ...payload,
        userId: Number(userId.value),
        selfScore: Number(selfScore.value),
        selfComment: selfComment.value,
      });
      ElMessage.success(
        `作业提交成功（自评 ${data.self_assessment?.score ?? selfScore.value} 分）`
      );
    } else {
      data = await postAnalyze(payload);
      ElMessage.success("分析完成");
    }

    await refreshSessionList();
    await loadSessionMessages(activeSessionId.value);
    clearComposer();
  } catch (err) {
    errorMsg.value = formatAxiosError(err);
    ElMessage.error(useAssignmentSubmit.value ? "作业提交失败" : "分析失败");
  } finally {
    loading.value = false;
  }
}

watch(messages, () => scrollChatToBottom(), { deep: true });

onMounted(async () => {
  userId.value = localStorage.getItem(STORAGE_USER_ID) || "";
  assignmentId.value = localStorage.getItem(STORAGE_ASSIGNMENT_ID) || "";

  try {
    const health = await getHealth();
    backendOk.value = true;
    llmConfigured.value = health.llm_configured !== false;
    deepResearchAvailable.value = health.deep_research_available === true;
    await bootstrapSessions();
  } catch {
    backendOk.value = false;
    llmConfigured.value = false;
    deepResearchAvailable.value = false;
  }
});

watch(userId, (v) => localStorage.setItem(STORAGE_USER_ID, v || ""));
watch(assignmentId, (v) => localStorage.setItem(STORAGE_ASSIGNMENT_ID, v || ""));
</script>

<template>
  <div class="chat-app">
    <!-- 左侧会话栏 -->
    <aside class="chat-sidebar">
      <div class="chat-sidebar-top">
        <button class="chat-new-btn" type="button" @click="handleNewSession">
          <el-icon><Plus /></el-icon>
          <span>新建会话</span>
        </button>
      </div>

      <div v-loading="sessionsLoading" class="chat-session-list">
        <button
          v-for="item in sessions"
          :key="item.session_id"
          type="button"
          class="chat-session-item"
          :class="{ active: item.session_id === activeSessionId }"
          @click="selectSession(item.session_id)"
        >
          <el-icon class="chat-session-icon"><ChatDotRound /></el-icon>
          <div class="chat-session-text">
            <div class="chat-session-title">{{ item.title || "新会话" }}</div>
            <div class="chat-session-preview">
              {{ item.preview || "暂无消息" }}
            </div>
          </div>
        </button>
        <div v-if="!sessionsLoading && sessions.length === 0" class="chat-empty">
          暂无会话，点击上方新建
        </div>
      </div>

      <div class="chat-sidebar-footer">
        <div class="chat-sidebar-status">
          <span
            class="status-dot"
            :class="{
              ok: backendOk === true,
              warn: backendOk === true && !llmConfigured,
              err: backendOk === false,
            }"
          />
          {{
            backendOk === false
              ? "后端未连接"
              : !llmConfigured
                ? "未配置 API Key"
                : "后端已连接"
          }}
        </div>
      </div>
    </aside>

    <!-- 主聊天区 -->
    <main
      class="chat-main"
      :class="{ 'is-dragover': isDragging }"
      @dragenter.prevent="onDragEnter"
      @dragleave="onDragLeave"
      @dragover.prevent="onDragOver"
      @drop.prevent="onDrop"
    >
      <header class="chat-header">
        <div>
          <h1 class="chat-header-title">
            {{ activeSession?.title || "教育智能体 Copilot" }}
          </h1>
          <p class="chat-header-sub">
            上传 PDF / Word / 图片，获取理论 · 实践 · 数据 · 文献多维度评估
          </p>
        </div>
        <el-button text @click="showSettings = !showSettings">
          <el-icon><Setting /></el-icon>
          设置
        </el-button>
      </header>

      <div class="chat-tabs">
        <button
          type="button"
          class="chat-tab"
          :class="{ active: activeTab === 'chat' }"
          @click="switchTab('chat')"
        >
          AI 分析与自评提交
        </button>
        <button
          type="button"
          class="chat-tab"
          :class="{ active: activeTab === 'peer' }"
          @click="switchTab('peer')"
        >
          同伴互评
        </button>
      </div>

      <!-- 消息区 -->
      <div v-show="activeTab === 'chat'" ref="chatScrollRef" class="chat-messages">
        <div v-if="messages.length === 0 && !loading" class="chat-welcome">
          <div class="chat-welcome-icon">
            <el-icon :size="36"><MagicStick /></el-icon>
          </div>
          <h2>开始一次新的作业分析</h2>
          <p>在下方输入或<strong>拖入 PDF / Word / 图片</strong>，系统将自动生成形成性评价。</p>
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="chat-message"
          :class="msg.role === 'user' ? 'is-user' : 'is-assistant'"
        >
          <div class="chat-avatar">
            <el-icon v-if="msg.role === 'user'"><User /></el-icon>
            <el-icon v-else><MagicStick /></el-icon>
          </div>
          <div class="chat-bubble">
            <div class="chat-bubble-meta">
              {{ msg.role === "user" ? "你" : "教育智能体" }}
              <span v-if="msg.timestamp">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="chat-bubble-content">{{ msg.content }}</div>
            <div
              v-if="msg.role === 'assistant' && msg.meta?.routes?.length"
              class="chat-bubble-tags"
            >
              <el-tag
                v-for="r in msg.meta.routes"
                :key="r"
                size="small"
                effect="dark"
                round
              >
                {{ r }}
              </el-tag>
              <el-tag
                v-if="msg.meta.total_score != null"
                size="small"
                type="success"
                effect="dark"
                round
              >
                {{ msg.meta.total_score }} 分
              </el-tag>
            </div>
          </div>
        </div>

        <div v-if="loading" class="chat-message is-assistant">
          <div class="chat-avatar">
            <el-icon><MagicStick /></el-icon>
          </div>
          <div class="chat-bubble">
            <div class="chat-bubble-content chat-typing">
              正在分析中，首次可能需 10～20 分钟…
            </div>
          </div>
        </div>
      </div>

      <!-- 同伴互评 -->
      <div v-show="activeTab === 'peer'" class="peer-panel">
        <div class="peer-panel-header">
          <div>
            <h2 class="peer-panel-title">同组待互评作业</h2>
            <p class="peer-panel-sub">
              基于用户 ID {{ userId || "（未设置）" }} 加载同组成员提交（不含本人）
            </p>
          </div>
          <el-button
            type="primary"
            :loading="peerLoading"
            :disabled="!canLoadPeer"
            @click="loadPeerAssignments"
          >
            刷新列表
          </el-button>
        </div>

        <div v-loading="peerLoading" class="peer-list">
          <div
            v-for="(item, idx) in peerItems"
            :key="`${item.target_user_id}-${item.assignment_id}-${idx}`"
            class="peer-card"
          >
            <div class="peer-card-main">
              <div class="peer-card-name">{{ item.student_name }}</div>
              <div class="peer-card-meta">
                作业 #{{ item.assignment_id }}
                <span v-if="item.submit_time"> · {{ formatTime(item.submit_time) }}</span>
              </div>
              <a
                v-if="item.file_url"
                class="peer-card-link"
                :href="resolveFileUrl(item.file_url)"
                target="_blank"
                rel="noopener"
              >
                查看提交文件
              </a>
              <span v-else class="peer-card-muted">无附件（纯文本提交）</span>
            </div>
            <el-button type="primary" plain @click="openPeerDialog(item)">
              互评
            </el-button>
          </div>
          <div v-if="!peerLoading && peerItems.length === 0" class="peer-empty">
            暂无待互评作业。请确认已在设置中填写用户 ID，且同组成员已提交作业。
          </div>
        </div>
      </div>

      <!-- 设置面板 -->
      <div v-if="showSettings" class="chat-settings">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-input
              v-model="userId"
              placeholder="用户 ID（数据库 users.id，互评/作业必填）"
              clearable
            />
          </el-col>
          <el-col :span="8">
            <el-input
              v-model="assignmentId"
              placeholder="作业 ID（填写后启用自评提交）"
              clearable
            />
          </el-col>
          <el-col :span="8">
            <el-input
              v-model="studentId"
              placeholder="学生 ID 字符串（可选，长期记忆）"
              clearable
            />
          </el-col>
        </el-row>
        <el-row :gutter="12" class="chat-settings-row2">
          <el-col :span="12">
            <el-input
              v-model="routes"
              placeholder="路由 theory,practice,data,literature（可选）"
              clearable
            />
          </el-col>
          <el-col :span="12">
            <div class="self-score-row">
              <span class="self-score-label">自评分数</span>
              <el-slider v-model="selfScore" :min="0" :max="100" :step="1" show-input />
            </div>
          </el-col>
        </el-row>
        <el-input
          v-model="selfComment"
          type="textarea"
          :rows="2"
          placeholder="自评说明（可选，填写作业 ID 时随提交保存）"
          class="chat-settings-comment"
        />
        <div v-if="useAssignmentSubmit" class="chat-settings-tip">
          已启用<strong>作业+自评</strong>模式：提交时将调用 /assignments/{id}/submit 并保存自评。
        </div>
        <div class="chat-settings-row">
          <el-switch
            v-model="enableDeepResearch"
            :disabled="loading"
            inline-prompt
            active-text="开"
            inactive-text="关"
          />
          <span>深度联网研究（较慢）</span>
        </div>
      </div>

      <!-- 错误 -->
      <div v-if="errorMsg" class="chat-error">
        <pre>{{ errorMsg }}</pre>
      </div>

      <!-- 输入区 -->
      <footer v-show="activeTab === 'chat'" class="chat-composer" :class="{ 'is-dragover': isDragging }">
        <div v-if="isDragging" class="chat-drop-overlay">
          <el-icon :size="28"><UploadFilled /></el-icon>
          <span>松开鼠标即可添加文件</span>
        </div>
        <div v-if="hasFiles" class="chat-file-chips">
          <el-tag
            v-for="f in fileList"
            :key="f.uid"
            closable
            size="small"
            @close="removeFile(f)"
          >
            {{ f.name }}
          </el-tag>
        </div>
        <div class="chat-composer-row">
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            :file-list="fileList"
            multiple
            :accept="acceptTypes"
            :disabled="loading"
            :on-change="onUploadChange"
            :on-remove="onUploadRemove"
          >
            <el-button circle :disabled="loading">
              <el-icon><Paperclip /></el-icon>
            </el-button>
          </el-upload>
          <el-input
            v-model="studentText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            placeholder="输入作答说明，或上传 PDF / Word / 图片…"
            :disabled="loading"
            @keydown.ctrl.enter="handleSubmit"
          />
          <el-button
            type="primary"
            circle
            class="chat-send-btn"
            :loading="loading"
            :disabled="!canSubmit"
            @click="handleSubmit"
          >
            <el-icon v-if="!loading"><Promotion /></el-icon>
          </el-button>
        </div>
        <div class="chat-composer-hint">
          拖入文件到聊天区 · Ctrl + Enter 发送
          <span v-if="useAssignmentSubmit"> · 作业 #{{ assignmentId }} + 自评 {{ selfScore }} 分</span>
        </div>
      </footer>

      <el-dialog
        v-model="peerDialogVisible"
        :title="`互评：${peerForm.studentName}`"
        width="480px"
        destroy-on-close
      >
        <div class="peer-dialog-meta">
          作业 #{{ peerForm.assignmentId }} · 被评用户 #{{ peerForm.targetUserId }}
        </div>
        <div class="peer-dialog-score">
          <span>互评分数</span>
          <el-slider v-model="peerForm.score" :min="0" :max="100" :step="1" show-input />
        </div>
        <el-input
          v-model="peerForm.comment"
          type="textarea"
          :rows="4"
          placeholder="互评评语（可选）"
        />
        <template #footer>
          <el-button @click="peerDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="peerSubmitLoading" @click="handlePeerSubmit">
            提交互评
          </el-button>
        </template>
      </el-dialog>
    </main>
  </div>
</template>
