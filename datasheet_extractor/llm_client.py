"""公司 LLM 介接層（目前為 stub）。

TODO(Devin): 在公司電腦上完成以下事項
  1. 依公司 LLM 的 API 格式實作 CompanyLLMClient.complete()
  2. config/default.yaml → llm.enabled: true
  3. 憑證放環境變數，不要寫進 repo（COMPANY_LLM_URL / COMPANY_LLM_TOKEN / COMPANY_LLM_MODEL）
  4. 跑 tests/test_llm_contract.py（以 FakeLLMClient 驗證介面），再拿 golden set 跑 evaluate

介面約定：complete(system: str, user: str) -> str
  - 回傳「純 JSON 字串」（格式見 prompts/table_extract.md）
  - 建議 temperature=0；若 API 支援 JSON mode / response_format 請打開
  - Stage 3 會自己做：JSON 解析、row_id 覆蓋率檢查、缺漏列重送、數值是否存在於原文的檢查
"""
from __future__ import annotations

import os


class LLMClient:
    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class CompanyLLMClient(LLMClient):
    def __init__(self, url: str | None = None, token: str | None = None, model: str | None = None,
                 timeout: float = 120.0):
        self.url = url or os.environ.get("COMPANY_LLM_URL")
        self.token = token or os.environ.get("COMPANY_LLM_TOKEN")
        self.model = model or os.environ.get("COMPANY_LLM_MODEL")
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        # ------------------------------------------------------------------
        # TODO(Devin): 公司 LLM 串接。以下為 OpenAI-compatible chat completions 範本，
        #              若公司 API 格式不同，請改寫 payload 與回應解析。
        #
        # import requests
        # headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        # payload = {
        #     "model": self.model,
        #     "temperature": 0,
        #     # "response_format": {"type": "json_object"},   # 若支援 JSON mode
        #     "messages": [
        #         {"role": "system", "content": system},
        #         {"role": "user", "content": user},
        #     ],
        # }
        # resp = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
        # resp.raise_for_status()
        # return resp.json()["choices"][0]["message"]["content"]
        #
        # 注意事項：
        # - Datasheet 多為 NDA 文件，確認端點是公司內部部署，不是外部雲端
        # - 單張表格太大（> context）時，在 stage3_extract.llm_extract 依 row 分批送
        # - 記錄每次 request/response 到 out/<doc>/03_extract/llm_log/，方便追查遺漏
        # ------------------------------------------------------------------
        raise NotImplementedError("Company LLM not wired yet — see TODO(Devin) in llm_client.py")


class FakeLLMClient(LLMClient):
    """測試用：回傳預先準備好的回應（list，依呼叫順序）。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.responses.pop(0) if self.responses else '{"parameters": [], "ignored_rows": []}'


def get_client(cfg: dict) -> LLMClient | None:
    if not cfg.get("llm", {}).get("enabled"):
        return None
    return CompanyLLMClient()
