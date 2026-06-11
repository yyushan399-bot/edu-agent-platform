"""教育智能体入口：读取学生文本，执行 LangGraph 工作流并打印结果。"""

from __future__ import annotations

import json

import llm_config  # noqa: F401
from llm_config import is_dotenv_loaded

from main_graph import app
from state import create_initial_state


def main() -> None:
    if not is_dotenv_loaded():
        print("错误：未检测到 OPENAI_API_KEY，请配置 .env 后重试。")
        return

    student_text = input("请输入学生提交内容：\n").strip()
    if not student_text:
        print("错误：学生文本不能为空。")
        return

    result = app.invoke(create_initial_state(student_text))

    print("\n===== 执行结果 =====\n")
    print(json.dumps(dict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
