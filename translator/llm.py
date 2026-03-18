"""
LLM translation module.

API keys are stored in .env (one key per provider).
Provider selection, base URL and model name are stored in config.json.
"""
import json
import os
import re
from typing import Dict, List

from dotenv import load_dotenv
from openai import AsyncOpenAI

from utils.paths import CONFIG_FILE, ENV_FILE

# ── Provider registry ─────────────────────────────────────────────────────────
# env_key   → variable name in .env that holds this provider's API key
# base_url  → OpenAI-compatible endpoint
# models    → suggested model names (first = default)
PROVIDERS: Dict[str, Dict] = {
    "Kilo Code": {
        "base_url":     "https://api.kilo.ai/api/gateway",
        "models":       [
            "kilo/auto",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-opus-4-6",
            "moonshot/kimi-k2",
            "zai/glm-5",
            "minimax/m2.1",
        ],
        "env_key":      "KILO_CODE_API_KEY",
        "key_url":      "https://app.kilo.ai",
    },
    "Kimi K2": {
        "base_url":     "https://api.moonshot.ai/v1",
        "models":       ["kimi-k2.5", "kimi-k2-thinking", "kimi-k2-turbo-preview"],
        "env_key":      "KIMI_K2_API_KEY",
        "key_url":      "https://platform.moonshot.ai/",
    },
    "Z.ai": {
        "base_url":     "https://api.z.ai/api/paas/v4/",
        "models":       [
            "glm-4.7-flash",
            "glm-4.7-flashx",
            "glm-4.5-air",
            "glm-4.5-flash",
            "glm-4.7",
            "glm-5",
        ],
        "env_key":      "ZAI_API_KEY",
        "key_url":      "https://z.ai/manage-apikey/apikey-list",
    },
    "Z.ai Coding": {
        "base_url":     "https://api.z.ai/api/coding/paas/v4/",
        "models":       [
            "glm-5",
            "glm-4.7",
            "glm-4.7-flash",
            "glm-4.7-flashx",
            "glm-4.5-air",
            "glm-4.5-flash",
        ],
        "env_key":      "ZAI_API_KEY",
        "key_url":      "https://z.ai/manage-apikey/apikey-list",
    },
    "Opencode Zen": {
        "base_url":     "https://opencode.ai/zen/v1",
        "models":       ["opencode/kimi-k2.5", "opencode/glm-5", "opencode/qwen3-coder-480b"],
        "env_key":      "OPENCODE_ZEN_API_KEY",
        "key_url":      "https://opencode.ai/auth",
    },
    "Custom": {
        "base_url":     "",
        "models":       [],
        "env_key":      "CUSTOM_API_KEY",
        "key_url":      "",
    },
}

# ── Translation system prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = """\
#你的所有思考過程均需要考慮日文及英文標題（如有）#

**# 成人影片繁體中文標題在地化翻譯指令**
---

## **◈ 行動清單**
你的思考過程必須包括以下動作，完成後勾稽：
- [ ] 回顧核心原則
- [ ] 重申及執行文化適配
- [ ] 分解標題內容作深入考慮
- [ ] 處理關鍵術語
- [ ] 轉化日期為8碼純數字，無符號
- [ ] 確認標題沒有任何空格
- [ ] 確認女優名與標題間距1空格
- [ ] 確認多位女優名之間使用「、」分隔（例：女優A、女優B、女優C）
- [ ] 確認女優名與番號間距1空格
- [ ] 確認原文有引號則必須翻譯的時候保留引號
- [ ] 確認符號種類≤5種，無日式殘留符號
- [ ] 確認Google搜尋「譯名+番號」出現有效結果
- [ ] 確認回譯日文後吻合度必須≥80%
- [ ] 確認所有文字必須為繁體中文，不可出現簡體中文
---

## **◈ 核心原則**
1. **語義還原性**
   - 性行為描述維持原文語序，可按需要調整語態（被動↔主動）
   - 禁止用詞隱晦，尊重原文表述方式
   - 尊重主賓語，確保翻譯時中文的語態合乎繁體中文的行文
   - 關鍵情節（場所/道具/性癖）**禁止刪減或模糊化**
   - **禁止增加心理活動或情節**

2. **文化適配驗證**
   │ 層級 │ 檢驗內容 │ 執行細則與參照來源 │
   ├─────┼──────────┼────────────────────────┤
   │ **符號** │ 標題排版與斷句 │
   │       │ - 主標題限用「！」「；」「：」「、」「，」五種符號
   │       │ - 如原文**有引號的部分必須翻譯**，並使用引號（「和」）
   │       │ - 副標題或並列詞強制使用「、」分隔（例：OL、眼鏡）
   │       │ - **禁止不是正式中文標點的符號或日文符號**「☆」「※」「→」「x」「♡」「〜」│
   ├─────┼──────────┼────────────────────────┤
   │ **語感** │ 中文行文流暢度 │
   │       │ - 刪除日文漢字直譯詞（例：豹變→解放／覺醒）
   │       │ - 轉換和製英語為本地用詞（例：イラマ→深喉／口交）
   │       │ - 限制意義不明字（例：絕倫、NTR、超絕、生中出、泥醉、悶絕、肉便器、出張、生姦、相姦、絕頂等於AV中沒有意義的漢字）
   │       │ - 去除「の」、「娘」等日文殘留字元
   │       │ - 所有字都需要與成人影片詞彙有關（例：峽谷→乳溝）│
---

## **◈ 標題建構強制格式**
**基礎結構**
`發行日期(8碼) - 情境敘述[性互動關鍵詞] 女優譯名 番號`

**格式細則**
1. **日期規範**
   - 嚴格使用`YYYYMMDD`，**無任何括號或符號**
   - 日期與標題間隔為「空格+短橫線+空格」（例：`20240926 - 標題`）

2. **元件間隔**
   - 女優譯名前後各留1空格（例：`...屬性！ 彩月七緒 START-154`）
   - **多位女優必須用「、」分隔，禁止用空格分隔女優名**（例：`...標題 女優A、女優B、女優C 番號`）

---

### **◈ 女優譯名生成流程**
1. **既有譯名驗證**
   - 優先參考https://9269av.cc/ 網站的女優名稱
   - 查DMM官方中文站／中文維基百科AV條目
   - 若無資料，採用「日本藝名漢字優先」原則（例：七緒→保留，非「七央」）
   - 女優譯名需通過Google搜尋「譯名+番號」首頁出現≥2筆有效結果

2. **新人生成規則**
   - 無漢字藝名者，依教育部《日語人名譯音表》轉換

---

## **◈ 輸出邏輯**
- **使用拆解法處理任務。首先，仔細分析原文的結構和關鍵元素，寫出原文原子化分析對照列表（日文對中文），並逐步進行翻譯，再進行最後的合併**
- 列出5個不同翻譯方案，每個標題**必須**用 Markdown fenced code block 包裹，格式如下（不可用其他格式替代）：

```
20240926 - 標題內容 女優譯名 番號
```

多位女優範例：
```
20240926 - 標題內容 女優A、女優B、女優C 番號
```

- 標題下面需回覆：「回譯結果」「回譯吻合度」及「翻譯核心方式」，並按「回譯吻合度」高到低排列

## **◈ 總輸出規則（按順序）**
- 原文原子化分析表
- 建議標題一（**必須用``` ```包裹，單獨一行，內容只有標題字串**）、回譯結果、回譯吻合度及翻譯核心方式
- 建議標題二（**必須用``` ```包裹，單獨一行，內容只有標題字串**）、回譯結果、回譯吻合度及翻譯核心方式
- 以此類推
"""


# ── .env helpers ──────────────────────────────────────────────────────────────

def read_env_key(key: str) -> str:
    """Read a single key from .env (without polluting os.environ)."""
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return ""


def write_env_key(key: str, value: str) -> None:
    """Update or append key=value in .env without touching other lines."""
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []

    replaced = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and stripped.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(f"{key}={value}\n")

    ENV_FILE.write_text("".join(new_lines), encoding="utf-8")


# ── config.json helpers ───────────────────────────────────────────────────────

def load_config() -> Dict:
    """Load provider/model/base_url from config.json; inject api_key from .env."""
    cfg: Dict = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Strip any api_key that was stored in the old config.json
    cfg.pop("api_key", None)

    # Guard: if "provider" is not a string (e.g. whole config dict was stored there
    # due to a previous bug), reset it so we don't crash PROVIDERS.get().
    if not isinstance(cfg.get("provider"), str):
        cfg["provider"] = ""

    # Inject secrets from .env
    provider_info = PROVIDERS.get(cfg.get("provider", ""), {})
    env_key = provider_info.get("env_key", "CUSTOM_API_KEY")
    cfg["api_key"] = read_env_key(env_key)

    # Fallback: if provider is blank/mismatched in config.json, scan all known
    # providers and use the first key that's actually present in .env
    if not cfg["api_key"]:
        for _pinfo in PROVIDERS.values():
            _val = read_env_key(_pinfo.get("env_key", ""))
            if _val:
                cfg["api_key"] = _val
                break

    cfg["qbt_password"] = read_env_key("QBT_PASSWORD")

    return cfg


def save_config(
    provider:           str = "",
    base_url:           str = "",
    model:              str = "",
    api_key:            str = "",
    download_folder:    str = "",
    qbt_url:            str = "",
    qbt_username:       str = "",
    qbt_password:       str = "",
    metadata_source:    str = "javdb",
    dl_poll_interval:   int = 30,
    dl_cover_fields:    list = None,
    vtm_exe:            str = "",
    vtm_preset:         str = "",
    losslesscut_exe:      str = "",
    trans_concurrency:     int = 3,
    javdb_proxies:         list = None,
    javdb_concurrency:     int = 1,
    javlibrary_concurrency: int = 1,
    javlibrary_foreground_delay: float = 3.0,
    downloader_cover_w:    int = 240,
    tracker_cover_w:       int = 80,
    tracker_auto_inactive_enabled: bool = True,
    tracker_inactive_months: int = 6,
    organiser_scan_folder: str = "",
    organiser_mover_base:  str = "",
    organiser_cleanup_delete_other_files: bool = True,
    organiser_cleanup_delete_small_videos: bool = False,
    organiser_cleanup_small_video_mb: float = 30.0,
    aura_config:           dict = None,
    rating_tooltips:       dict = None,
    rating_thresholds:     dict = None,
) -> None:
    """
    Save non-secret settings to config.json.
    Save API key and qBT password to .env.
    """
    cfg = {
        "provider":           provider,
        "base_url":           base_url,
        "model":              model,
        "download_folder":    download_folder,
        "qbt_url":            qbt_url,
        "qbt_username":       qbt_username,
        "metadata_source":    metadata_source,
        "dl_poll_interval":   dl_poll_interval,
        "dl_cover_fields":    dl_cover_fields if dl_cover_fields is not None else ["progress_bar", "percentage", "state"],
        "vtm_exe":            vtm_exe,
        "vtm_preset":         vtm_preset,
        "losslesscut_exe":       losslesscut_exe,
        "trans_concurrency":     trans_concurrency,
        "javdb_proxies":         javdb_proxies if javdb_proxies is not None else [],
        "javdb_concurrency":     max(1, int(javdb_concurrency)),
        "javlibrary_concurrency": max(1, int(javlibrary_concurrency)),
        "javlibrary_foreground_delay": max(0.0, float(javlibrary_foreground_delay)),
        "downloader_cover_w":    downloader_cover_w,
        "tracker_cover_w":       tracker_cover_w,
        "tracker_auto_inactive_enabled": bool(tracker_auto_inactive_enabled),
        "tracker_inactive_months": max(1, int(tracker_inactive_months)),
        "organiser_scan_folder": organiser_scan_folder,
        "organiser_mover_base":  organiser_mover_base,
        "organiser_cleanup_delete_other_files": bool(organiser_cleanup_delete_other_files),
        "organiser_cleanup_delete_small_videos": bool(organiser_cleanup_delete_small_videos),
        "organiser_cleanup_small_video_mb": float(organiser_cleanup_small_video_mb),
        "aura_config":           aura_config or {},
        "rating_tooltips":       rating_tooltips or {},
        "rating_thresholds":     rating_thresholds or {},
    }
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    env_key = PROVIDERS.get(provider, {}).get("env_key", "CUSTOM_API_KEY")
    write_env_key(env_key, api_key)
    write_env_key("QBT_PASSWORD", qbt_password)


# ── LLM call ──────────────────────────────────────────────────────────────────

async def translate_title(
    title: str,
    date: str,
    actresses: List[str],
    ref_id: str,
    config: Dict,
) -> str:
    """
    Send JAV metadata to the configured LLM using the localisation prompt.
    Returns the full response string.
    Raises ValueError on missing settings, or OpenAI errors on API failure.
    """
    api_key  = config.get("api_key", "")
    base_url = config.get("base_url", "")
    model    = config.get("model", "")

    if not api_key:
        raise ValueError("API key is empty — open ⚙ Settings and enter your key.")
    if not base_url:
        raise ValueError("API base URL is empty — open ⚙ Settings.")
    if not model:
        raise ValueError("Model name is empty — open ⚙ Settings.")

    actress_str = "、".join(actresses) if actresses else "不明"
    user_msg = (
        f"原文標題：{title}\n"
        f"發行日期：{date}\n"
        f"女優：{actress_str}\n"
        f"番號：{ref_id}"
    )

    # Z.ai GLM models use chain-of-thought thinking by default which returns
    # an empty `content` field.  Disabling thinking gives a normal response.
    is_zai = "z.ai" in base_url.lower()
    extra: dict = {"thinking": {"type": "disabled"}} if is_zai else {}

    async with AsyncOpenAI(api_key=api_key, base_url=base_url) as client:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=4000,
            temperature=0.7,
            extra_body=extra or None,
        )

    msg = response.choices[0].message
    # Fallback: some Z.ai responses put text in reasoning_content when thinking
    # is enabled; extract it via the raw dict if content is empty.
    content = msg.content or ""
    if not content:
        raw = response.model_dump()
        content = (
            raw.get("choices", [{}])[0]
               .get("message", {})
               .get("reasoning_content", "")
            or ""
        )
    return content


# ── Response parsing ──────────────────────────────────────────────────────────

def extract_code_blocks(response: str) -> List[str]:
    """
    Extract title candidates from the LLM response.

    Primary:  fenced code blocks  (``` ... ```)
    Fallback: lines that match the expected title format
              YYYYMMDD - <text> <actress> <ref>
    """
    blocks = [
        m.strip()
        for m in re.findall(r"```[^\n]*\n(.*?)```", response, re.DOTALL)
        if m.strip()
    ]
    if blocks:
        return blocks

    # Fallback — grab any line that starts with an 8-digit date
    date_line = re.compile(r"^\d{8}\s*-\s*.{5,}", re.MULTILINE)
    fallback = [ln.strip() for ln in date_line.findall(response) if ln.strip()]
    if fallback:
        return fallback

    # Last resort — lines inside bold/inline-code markers that contain a ref number
    inline = re.compile(r"`([^`\n]{10,})`")
    return [m.strip() for m in inline.findall(response) if re.search(r"[A-Z]{2,}-\d{3}", m)]
