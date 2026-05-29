"""
多模型LLM调度中心
根据任务类型自动选择最优模型，支持故障转移
"""

import json
import os
import re
import time
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from openai import OpenAI
from rich.console import Console

console = Console()

# ── SSL 证书修复：使用 certifi 的 CA bundle ──
try:
    import certifi
    ssl_cert_file = certifi.where()
    os.environ.setdefault('SSL_CERT_FILE', ssl_cert_file)
    os.environ.setdefault('REQUESTS_CA_BUNDLE', ssl_cert_file)
except ImportError:
    # 降级到系统证书
    for p in ['/etc/ssl/cert.pem', '/private/etc/ssl/cert.pem']:
        if os.path.exists(p):
            os.environ.setdefault('SSL_CERT_FILE', p)
            break

# 自动加载 ~/.hermes/.env
_hermes_env = Path.home() / '.hermes' / '.env'
if _hermes_env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_hermes_env, override=False)
    except ImportError:
        pass


@dataclass
class LLMModel:
    """模型配置"""
    name: str
    provider: str
    api_base: str
    api_key: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.3
    timeout: float = 60.0
    # 擅长的任务类型
    strengths: List[str] = None
    # 优先级（数字越大优先级越高）
    priority: int = 0

    def __post_init__(self):
        if self.strengths is None:
            self.strengths = []


@dataclass
class LLMResponse:
    """模型响应"""
    model_name: str
    content: str
    tokens_used: int = 0
    latency_ms: float = 0
    success: bool = True
    error: str = ""


class LLMDepot:
    """多模型调度中心"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.models: Dict[str, LLMModel] = {}
        self.clients: Dict[str, OpenAI] = {}
        self.usage_stats: Dict[str, Dict] = {}  # 使用统计
        self._load_models()

    def _resolve_env(self, value: str) -> str:
        """解析配置中的 ${ENV_VAR} 占位符，未设置则返回空字符串"""
        def _replace(m):
            var_name = m.group(1)
            return os.environ.get(var_name, "")
        return re.sub(r'\$\{(\w+)\}', _replace, value)

    def _load_models(self):
        """从配置加载模型"""
        llm_configs = self.config.get("llm_models", [])

        for cfg in llm_configs:
            model = LLMModel(
                name=cfg["name"],
                provider=cfg.get("provider", "openai_compatible"),
                api_base=self._resolve_env(cfg["api_base"]),
                api_key=self._resolve_env(cfg["api_key"]),
                model=self._resolve_env(cfg["model"]),
                max_tokens=cfg.get("max_tokens", 4096),
                temperature=cfg.get("temperature", 0.3),
                timeout=cfg.get("timeout", 60.0),
                strengths=cfg.get("strengths", []),
                priority=cfg.get("priority", 0),
            )
            self.models[model.name] = model
            self.clients[model.name] = OpenAI(
                base_url=model.api_base,
                api_key=model.api_key,
                timeout=model.timeout,
                max_retries=1,
            )
            self.usage_stats[model.name] = {
                "calls": 0, "successes": 0, "failures": 0,
                "total_tokens": 0, "total_latency_ms": 0,
            }

    def get_model_for_task(self, task_type: str) -> Optional[LLMModel]:
        """根据任务类型选择最优模型"""
        # 优先找专门擅长该任务的模型
        candidates = []
        for model in self.models.values():
            if task_type in model.strengths:
                candidates.append(model)

        if candidates:
            # 按优先级排序
            candidates.sort(key=lambda m: m.priority, reverse=True)
            return candidates[0]

        # 没有专门模型，按优先级选
        all_models = sorted(self.models.values(), key=lambda m: m.priority, reverse=True)
        return all_models[0] if all_models else None

    def call(self, prompt: str, system: str = "",
             task_type: str = "general",
             model_name: str = None,
             max_tokens: int = None,
             temperature: float = None,
             json_mode: bool = False) -> LLMResponse:
        """
        调用LLM

        Args:
            prompt: 用户提示
            system: 系统提示
            task_type: 任务类型 (analysis/news/backtest/evolution/general)
            model_name: 指定模型名称（可选，优先于自动选择）
            max_tokens: 最大token数
            temperature: 温度
            json_mode: 是否要求JSON输出
        """
        # 选择模型
        if model_name and model_name in self.models:
            model = self.models[model_name]
        else:
            model = self.get_model_for_task(task_type)

        if not model:
            return LLMResponse(model_name="none", content="", success=False, error="无可用模型")

        client = self.clients[model.name]
        start_time = time.time()

        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            kwargs = {
                "model": model.model,
                "messages": messages,
                "max_tokens": max_tokens or model.max_tokens,
                "temperature": temperature if temperature is not None else model.temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            latency = (time.time() - start_time) * 1000

            # 更新统计
            self.usage_stats[model.name]["calls"] += 1
            self.usage_stats[model.name]["successes"] += 1
            self.usage_stats[model.name]["total_tokens"] += tokens
            self.usage_stats[model.name]["total_latency_ms"] += latency

            return LLMResponse(
                model_name=model.name,
                content=content,
                tokens_used=tokens,
                latency_ms=latency,
                success=True,
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            self.usage_stats[model.name]["calls"] += 1
            self.usage_stats[model.name]["failures"] += 1
            self.usage_stats[model.name]["total_latency_ms"] += latency

            console.print(f"[yellow]LLM {model.name} 调用失败: {e}[/yellow]")
            return LLMResponse(
                model_name=model.name,
                content="",
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    def call_with_fallback(self, prompt: str, system: str = "",
                           task_type: str = "general",
                           preferred_models: List[str] = None) -> LLMResponse:
        """带故障转移的调用"""
        models_to_try = []

        # 先尝试指定的模型
        if preferred_models:
            for name in preferred_models:
                if name in self.models:
                    models_to_try.append(self.models[name])

        # 再尝试按任务类型选择的模型
        best = self.get_model_for_task(task_type)
        if best and best not in models_to_try:
            models_to_try.append(best)

        # 最后尝试所有模型
        for model in self.models.values():
            if model not in models_to_try:
                models_to_try.append(model)

        last_error = ""
        for model in models_to_try:
            result = self.call(prompt, system, task_type=task_type, model_name=model.name)
            if result.success:
                return result
            last_error = result.error

        return LLMResponse(model_name="none", content="", success=False, error=f"所有模型均失败: {last_error}")

    def get_usage_report(self) -> str:
        """生成使用报告"""
        lines = ["LLM 使用统计:", "-" * 50]
        for name, stats in self.usage_stats.items():
            if stats["calls"] == 0:
                continue
            success_rate = stats["successes"] / stats["calls"] * 100
            avg_latency = stats["total_latency_ms"] / stats["calls"]
            lines.append(
                f"{name}: {stats['calls']}次调用, "
                f"成功率{success_rate:.0f}%, "
                f"平均{avg_latency:.0f}ms, "
                f"共{stats['total_tokens']}token"
            )
        return "\n".join(lines)
