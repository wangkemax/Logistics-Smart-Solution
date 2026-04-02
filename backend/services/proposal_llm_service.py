"""backend/services/proposal_llm_service.py LLM 调用封装 for Proposal Section Generator"""
from __future__ import annotations

import os
import httpx
from datetime import datetime, timezone
from typing import Optional


class ProposalLLMService:
    """Proposal 专用的 LLM 调用封装"""

    def __init__(self):
        self.api_key = os.getenv("MINIMAX_API_KEY", "")
        self.base_url = "https://api.minimax.chat/v1"
        self.model = "MiniMax-M2.7-32K"
        self.group_id = os.getenv("MINIMAX_GROUP_ID", "")

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
    ) -> tuple[str, int]:
        """
        调用 MiniMax LLM，返回 (response_text, tokens_used)

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            max_tokens: 最大生成 token 数

        Returns:
            (response_text, total_tokens_used)
        """
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY environment variable is not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.group_id:
            headers["GroupId"] = self.group_id

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.base_url}/text/chatcompletion_v2",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"MiniMax API returned status {response.status_code}: {response.text[:500]}"
            )

        result = response.json()

        # 解析响应
        choices = result.get("choices", [])
        if not choices:
            raise RuntimeError(f"No choices in MiniMax response: {result}")

        # 取第一个 choice 的 content
        message = choices[0].get("message", {})
        text = message.get("content", "")

        # token 统计（从 response 的 usage 字段获取）
        usage = result.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)

        return text, total_tokens
