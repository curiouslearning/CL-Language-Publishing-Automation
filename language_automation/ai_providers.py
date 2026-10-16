import copy
import json
import os

# -------------------------------------------
# AI language check: configuration and the two AI services (spec 003).
# config.json (tracked, no secrets) picks the service and model; .env (gitignored) holds the API keys.
# Each check makes ONE request; nothing here retries (spec FR-019/FR-020).
# -------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
ENV_PATH = os.path.join(HERE, ".env")
SCHEMA_PATH = os.path.join(HERE, "ai_output_schema.json")

PROVIDERS = ("gemini", "claude")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
ENV_KEYS = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}
# A Claude key created outside a workspace needs the workspace named on every request
WORKSPACE_ENV = "ANTHROPIC_WORKSPACE_ID"
DEFAULTS = {
    "provider": "gemini",
    # temperature / max_output_tokens: None = the model's own default
    "gemini": {"api_key": "", "model": "gemini-flash-latest", "fallback_models": [],
               "temperature": None, "max_output_tokens": None},
    "claude": {"api_key": "", "model": "claude-opus-5-5", "effort": "low", "fallbacks": True,
               # only for an API key that isn't scoped to a workspace: sent as anthropic-workspace-id
               "workspace_id": ""},
}

REVIEW_PROMPT = """You review Feed the Monster early-literacy content for one language.
Input lines: id | type | text [| target=letter] [| rec=recording file name]
Types: L = letter puzzle, LW = letter-in-word puzzle (target letter inside the word), W = word puzzle, F = feedback sentence shown to children.

Report only real problems:
- misspelled_word: a word (W or LW text) that is misspelled or malformed in this language.
- foreign_letter: a letter or character that is not used in this language's writing system.
- bad_sentence: an F sentence that is ungrammatical or not in this language.
- recording_mismatch: rec= is shown only when the recording name differs from what should play (L and LW play the target letter's recording, W plays the word's). Flag it only if rec is clearly a different letter or word, not a transliteration or spelling variant of it.

Letter sounds, syllables and single letters are intentional phonics items: never flag them as misspellings.
Use only ids from the input. Put identical problems in one warning listing all their ids.
suggestion = the corrected text (empty if none). reason = one short sentence. confidence: high = certain, medium = likely, low = unsure.
If you cannot reliably judge this language, set can_judge=false, explain briefly in note, and do not guess.
An empty warnings list is a valid answer."""


class Unavailable(Exception):
    """The AI part of the check can't run or didn't complete; the message says why."""


# -------------------------------------------
# Token usage, in the same shape for both services, so their costs can be compared:
#   input_tokens   everything sent (prompt + item lines; for Claude, cache reads/writes included)
#   output_tokens  everything generated and billed as output (thinking included)
#   thinking_tokens  the part of output_tokens that was thinking (Gemini reports it separately; Claude doesn't)
# -------------------------------------------
def _count(obj, name):
    return int(getattr(obj, name, 0) or 0)


def claude_usage(u):
    if u is None:
        return None
    cache_write, cache_read = _count(u, "cache_creation_input_tokens"), _count(u, "cache_read_input_tokens")
    return {"input_tokens": _count(u, "input_tokens") + cache_write + cache_read,
            "output_tokens": _count(u, "output_tokens"),  # already includes any thinking
            "thinking_tokens": None,
            "cache_read_tokens": cache_read, "cache_write_tokens": cache_write}


def gemini_usage(u):
    if u is None:
        return None
    thinking = _count(u, "thoughts_token_count")
    return {"input_tokens": _count(u, "prompt_token_count"),
            "output_tokens": _count(u, "candidates_token_count") + thinking,  # thinking is billed as output
            "thinking_tokens": thinking,
            "cache_read_tokens": _count(u, "cached_content_token_count"), "cache_write_tokens": 0}


def read_env_file(path=ENV_PATH):
    """KEY=VALUE lines from .env (# comments, optional quotes). No extra package needed."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    return values


def is_hosted():
    """True on the Cloud Run deploy (FTM_HOSTED=1 is set by cloudbuild.yaml)."""
    return os.environ.get("FTM_HOSTED") == "1"


def load_config():
    """(config, reason): reason is None when the chosen provider is usable, else why not."""
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                user = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return cfg, f"config.json could not be read ({e})"
        if "provider" in user:
            cfg["provider"] = user["provider"]
        for name in PROVIDERS:
            for key, value in (user.get(name) or {}).items():
                if key in cfg[name] and key != "api_key":  # keys belong in .env, never in config.json
                    cfg[name][key] = value

    # API keys: real environment variables win over the .env file
    env_file = read_env_file()
    for name, env in ENV_KEYS.items():
        # stripped: a secret saved with a trailing newline would otherwise look like a rejected key
        cfg[name]["api_key"] = (os.environ.get(env) or env_file.get(env, "")).strip()
    cfg["claude"]["workspace_id"] = str(os.environ.get(WORKSPACE_ENV) or env_file.get(WORKSPACE_ENV)
                                        or cfg["claude"]["workspace_id"] or "").strip()

    provider = str(cfg["provider"]).strip().lower()
    cfg["provider"] = provider
    if provider not in PROVIDERS:
        return cfg, f"unknown provider '{provider}' in config.json (use \"gemini\" or \"claude\")"
    if cfg["claude"]["effort"] not in EFFORTS:
        cfg["claude"]["effort"] = DEFAULTS["claude"]["effort"]
    if not str(cfg[provider]["api_key"]).strip():
        if is_hosted():  # on Cloud Run the key comes from Secret Manager, not .env (spec 007)
            return cfg, (f"no API key configured for {provider}: the Cloud Run service has no "
                         f"{ENV_KEYS[provider]} secret attached (README \"Deploy to Cloud Run\")")
        return cfg, f"no API key configured for {provider}: add {ENV_KEYS[provider]}=... to language_automation/.env"
    return cfg, None


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    schema.pop("$comment", None)
    return schema


def make_reviewer(cfg):
    return ClaudeReviewer(cfg["claude"]) if cfg["provider"] == "claude" else GeminiReviewer(cfg["gemini"])


class ClaudeReviewer:
    def __init__(self, cfg):
        try:
            import anthropic
        except ImportError:
            raise Unavailable("install anthropic (pip install -r requirements.txt)")
        self.anthropic = anthropic
        self.cfg = cfg
        # max_retries=0: exactly one request per check
        workspace = cfg.get("workspace_id") or ""
        self.client = anthropic.Anthropic(
            api_key=cfg["api_key"], max_retries=0,
            default_headers={"anthropic-workspace-id": workspace} if workspace else None)
        self.usage = None
        self.model_used = cfg["model"]

    def review(self, language, item_lines):
        a, cfg = self.anthropic, self.cfg
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if cfg["fallbacks"] else {}
        try:
            resp = self.client.beta.messages.create(
                model=cfg["model"],
                max_tokens=16000,
                system=REVIEW_PROMPT,
                messages=[{"role": "user", "content": f"Language entered: {language}\n{item_lines}"}],
                output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": load_schema()}},
                **extra,
            )
        except a.RateLimitError:
            raise Unavailable("Claude rate limit reached")
        except a.AuthenticationError:
            raise Unavailable("Claude API key rejected")
        except a.BadRequestError as e:
            message = str(e.message).lower()
            if "workspace" in message and "header" in message:
                hint = (f" (this key isn't scoped to a workspace: add {WORKSPACE_ENV}=<workspace id> to "
                        "language_automation/.env, or create the key inside a workspace in the Claude Console)")
            elif "fallback" in message:
                hint = ' (try "fallbacks": false under "claude" in config.json)'
            else:
                hint = ""
            raise Unavailable(f"Claude rejected the request: {e.message}{hint}")
        except a.APIStatusError as e:
            if e.status_code in (500, 502, 503, 504, 529):
                raise Unavailable(f"Claude is busy right now (error {e.status_code}). "
                                  "Nothing was retried. Try again in a few minutes")
            raise Unavailable(f"Claude error {e.status_code}: {e.message}")
        except a.APIConnectionError:
            raise Unavailable("Claude unreachable")

        self.usage = claude_usage(resp.usage)
        # With server-side fallbacks another model may have answered; resp.model says which.
        # A dated id of the configured alias (claude-x-YYYYMMDD) is the same model.
        answered = getattr(resp, "model", "") or ""
        if answered and not answered.startswith(cfg["model"]):
            self.model_used = answered
        if resp.stop_reason == "refusal":
            raise Unavailable("Claude declined the request")
        if resp.stop_reason == "max_tokens":
            raise Unavailable("Claude's answer was too long")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise Unavailable("Claude returned no result")
        return json.loads(text)


class GeminiReviewer:
    def __init__(self, cfg):
        try:
            from google import genai
            from google.genai import errors
        except ImportError:
            raise Unavailable("install google-genai (pip install -r requirements.txt)")
        self.errors = errors
        self.cfg = cfg
        self.client = genai.Client(api_key=cfg["api_key"])
        self.usage = None
        self.model_used = cfg["model"]

    def review(self, language, item_lines):
        # The main model, then fallback_models from config.json, each tried once and ONLY while
        # the previous one answered "busy" (5xx: no work done, no tokens used).
        models = [self.cfg["model"]] + [m for m in self.cfg.get("fallback_models") or [] if m]
        config = {
            "system_instruction": REVIEW_PROMPT,
            "response_mime_type": "application/json",
            "response_json_schema": load_schema(),
            # no tools are used; also silences the SDK's AFC warning
            "automatic_function_calling": {"disable": True},
        }
        for key in ("temperature", "max_output_tokens"):
            if self.cfg.get(key) is not None:
                config[key] = self.cfg[key]
        busy = []
        for model in models:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=f"Language entered: {language}\n{item_lines}",
                    config=config,
                )
            except self.errors.APIError as e:
                # Busy (5xx) or not usable by this key (404): nothing was generated, no tokens used,
                # so move on to the next model in fallback_models. Keep Google's own message.
                if e.code in (500, 502, 503, 504, 404):
                    busy.append(f"{model} → {e.code}: {e.message}")
                    continue
                if e.code == 429:
                    raise Unavailable(f"Gemini rate limit reached on {model} (free tier). Try again later or switch provider")
                if e.code in (401, 403) or (e.code == 400 and "api key" in str(e.message).lower()):
                    raise Unavailable("Gemini API key rejected")
                raise Unavailable(f"Gemini error {e.code} on {model}: {e.message}")
            except Exception as e:  # network / DNS / TLS
                raise Unavailable(f"Gemini unreachable ({type(e).__name__})")

            self.model_used = model
            self.usage = gemini_usage(resp.usage_metadata)
            finish = str(getattr((resp.candidates or [None])[0], "finish_reason", "") or "")
            if finish.endswith("MAX_TOKENS"):
                raise Unavailable(f"Gemini's answer was cut off by max_output_tokens={self.cfg.get('max_output_tokens')} "
                                  "(thinking counts toward it on some models). Raise or remove it in config.json")
            if not resp.text:
                raise Unavailable("Gemini returned no result")
            return json.loads(resp.text)

        tried = " | ".join(busy)
        raise Unavailable(f"No Gemini model could answer (no tokens used): {tried}. "
                          "Busy (5xx): try again in a few minutes. Not found (404): that model isn't usable "
                          "with this key - change \"model\"/\"fallback_models\" in config.json "
                          "(names: python ai_language_check.py --list-models)")

    def list_models(self):
        """Models this key can use for text generation (a free lookup: no tokens)."""
        names = []
        for m in self.client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if not actions or "generateContent" in actions:
                names.append(m.name.removeprefix("models/"))
        return sorted(names)
