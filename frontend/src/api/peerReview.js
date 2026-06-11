import axios from "axios";
import { formatAxiosError } from "./analyze";

const baseURL = import.meta.env.DEV
  ? "/api"
  : import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const client = axios.create({
  baseURL,
  timeout: 60000,
});

/** 获取同组其他成员已提交的作业（待互评列表） */
export async function getPeerReviewAssignments(userId) {
  const { data } = await client.get("/peer-review/assignments", {
    params: { user_id: userId },
  });
  return data;
}

/** 提交同伴互评 */
export async function submitPeerReview(payload) {
  const { data } = await client.post("/peer-review/submit", {
    reviewer_id: payload.reviewerId,
    target_user_id: payload.targetUserId,
    assignment_id: payload.assignmentId,
    score: payload.score,
    comment: payload.comment?.trim() || null,
  });
  return data;
}

export { formatAxiosError };
