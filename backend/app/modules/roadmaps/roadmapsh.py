"""Links to roadmap.sh, plus "learn more" from the user's own local clone of its content.

Licence (github.com/nilbuild/developer-roadmap): personal use only; sharing links is allowed;
publishing the content in any form is not. So:
- Links to https://roadmap.sh/<roadmap> are always offered (allowed everywhere).
- Topic text and resource links are read at request time from a local clone whose path is
  set in ROADMAP_SH_CONTENT_DIR, and returned only to the signed-in user. They are never
  stored in the database, written to this repository, logged, or sent to an AI provider.
  Tests use synthetic files only.

The clone has one markdown file per topic (`roadmaps/<slug>/content/<topic>@<id>.md`: a
heading, an explanation, then "- [@kind@Title](url)" resource links) but no topic order, so a
roadmap day is matched to the topic whose name best fits the day's tasks.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Roadmap slugs on roadmap.sh, used for links when no local clone is configured. Names only.
KNOWN_SLUGS = frozenset(
    [
        "ai-agents",
        "ai-data-scientist",
        "ai-engineer",
        "android",
        "angular",
        "api-design",
        "aspnet-core",
        "aws",
        "backend",
        "blockchain",
        "c",
        "cloud-computing",
        "computer-science",
        "cpp",
        "css",
        "cyber-security",
        "data-analyst",
        "data-engineer",
        "datastructures-and-algorithms",
        "design-system",
        "devops",
        "devsecops",
        "django",
        "docker",
        "elasticsearch",
        "engineering-manager",
        "flutter",
        "frontend",
        "full-stack",
        "game-developer",
        "git-github",
        "golang",
        "graphql",
        "html",
        "ios",
        "java",
        "javascript",
        "kotlin",
        "kubernetes",
        "laravel",
        "linux",
        "machine-learning",
        "mlops",
        "mongodb",
        "nextjs",
        "nodejs",
        "php",
        "postgresql-dba",
        "product-manager",
        "prompt-engineering",
        "python",
        "qa",
        "react",
        "react-native",
        "redis",
        "ruby",
        "ruby-on-rails",
        "rust",
        "scala",
        "shell-bash",
        "software-architect",
        "software-design-architecture",
        "spring-boot",
        "sql",
        "swift-ui",
        "system-design",
        "technical-writer",
        "terraform",
        "typescript",
        "ux-design",
        "vue",
        "wordpress",
    ]
)

ALIASES = {
    "dsa": "datastructures-and-algorithms",
    "data structures": "datastructures-and-algorithms",
    "data structures and algorithms": "datastructures-and-algorithms",
    "algorithms": "datastructures-and-algorithms",
    "js": "javascript",
    "ts": "typescript",
    "node": "nodejs",
    "node js": "nodejs",
    "go": "golang",
    "next js": "nextjs",
    "postgres": "postgresql-dba",
    "postgresql": "postgresql-dba",
    "k8s": "kubernetes",
    "ml": "machine-learning",
    "c++": "cpp",
    "c#": "aspnet-core",
    "dotnet": "aspnet-core",
    "git": "git-github",
    "bash": "shell-bash",
    "shell": "shell-bash",
    "spring": "spring-boot",
    "vue js": "vue",
    "swift": "swift-ui",
    "rails": "ruby-on-rails",
    "llm": "ai-engineer",
    "ai": "ai-engineer",
}

NAMES = {
    "datastructures-and-algorithms": "Data Structures & Algorithms",
    "nodejs": "Node.js",
    "nextjs": "Next.js",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "postgresql-dba": "PostgreSQL",
    "aspnet-core": "ASP.NET Core",
    "cpp": "C++",
    "git-github": "Git and GitHub",
    "devops": "DevOps",
    "graphql": "GraphQL",
    "mongodb": "MongoDB",
    "ios": "iOS",
    "qa": "QA",
    "ux-design": "UX Design",
    "swift-ui": "SwiftUI",
}

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "using",
        "use",
        "your",
        "how",
        "what",
        "why",
        "when",
        "is",
        "are",
        "vs",
        "build",
        "learn",
        "understand",
        "practise",
        "practice",
        "check",
        "yourself",
        "basics",
        "basic",
        "intro",
        "introduction",
        "small",
        "simple",
        "project",
        "review",
        "day",
        "exercise",
        "concept",
        "concepts",
        "write",
        "create",
        "explain",
    ]
)
RESOURCE_KINDS = ("official", "opensource", "article", "video", "roadmap")
RESOURCE_LINE = re.compile(r"^- \[@(\w+)@(.+?)\]\((https?://[^)\s]+)\)\s*$")
MIN_SCORE = 0.6
MAX_RESOURCES = 5
MAX_SUMMARY = 700


@dataclass(frozen=True, slots=True)
class Resource:
    kind: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class Topic:
    title: str
    summary: str
    resources: tuple[Resource, ...]
    tokens: frozenset[str]
    phrase: str = ""


@dataclass(frozen=True, slots=True)
class Reference:
    roadmap_slug: str | None
    roadmap_name: str | None
    roadmap_url: str | None
    topic: Topic | None
    local_content: bool


def _normalise(text: str) -> str:
    text = text.lower().replace("&", " and ").replace(".", " ")
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text).split())


def _tokens(text: str) -> frozenset[str]:
    out: set[str] = set()
    for word in _normalise(text).split():
        if word in STOPWORDS or len(word) < 2:
            continue
        out.add(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return frozenset(out)


# Words that only label a topic ("useEffect Hook", "Two Pointer Technique"); a day that names
# the concept itself should still match. Kept when they are the whole title ("Hooks").
GENERIC = frozenset({"hook", "technique", "pattern", "method", "api", "library", "concept"})


def _topic_tokens(title: str) -> frozenset[str]:
    tokens = _tokens(title)
    return (tokens - GENERIC) or tokens


def _available_slugs(content_dir: str) -> frozenset[str]:
    if content_dir:
        base = Path(content_dir) / "roadmaps"
        if base.is_dir():
            return frozenset(p.name for p in base.iterdir() if (p / "content").is_dir())
    return KNOWN_SLUGS


def roadmap_slug(subject: str, content_dir: str = "") -> str | None:
    """The roadmap.sh roadmap for a subject ("React" -> "react", "DSA" -> data structures)."""
    slugs = _available_slugs(content_dir)
    key = _normalise(subject)
    for candidate in (ALIASES.get(key), key.replace(" ", "-"), key.replace(" ", "")):
        if candidate and candidate in slugs:
            return candidate
    # "React hooks", "Python for data" -> the first word naming a roadmap.
    for word in key.split():
        candidate = ALIASES.get(word, word)
        if candidate in slugs:
            return candidate
    return None


def roadmap_name(slug: str) -> str:
    return NAMES.get(slug) or slug.replace("-", " ").title()


def parse_topic(text: str) -> Topic | None:
    lines = text.splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
    if not title:
        return None
    summary: list[str] = []
    resources: list[Resource] = []
    started = False
    for line in lines:
        if line.startswith("# "):
            started = True
            continue
        if not started:
            continue
        match = RESOURCE_LINE.match(line.strip())
        if match:
            kind, name, url = match.groups()
            if kind in RESOURCE_KINDS:
                resources.append(Resource(kind=kind, title=name.strip(), url=url))
        elif line.lower().startswith("visit the following resources"):
            continue
        elif line.strip() and not line.startswith(("-", "#", "![", "<")):
            summary.append(line.strip())
    text_summary = " ".join(summary)
    if len(text_summary) > MAX_SUMMARY:
        text_summary = text_summary[: MAX_SUMMARY - 1].rsplit(" ", 1)[0] + "…"
    resources.sort(key=lambda r: RESOURCE_KINDS.index(r.kind))
    return Topic(
        title=title,
        summary=text_summary,
        resources=tuple(resources[:MAX_RESOURCES]),
        tokens=_topic_tokens(title),
        phrase=_normalise(title),
    )


@lru_cache(maxsize=32)
def _load_topics(content_dir: str, slug: str, stamp: float) -> tuple[Topic, ...]:
    """Topics of one roadmap; `stamp` (the folder's mtime) refreshes the cache after a pull."""
    base = (Path(content_dir) / "roadmaps").resolve()
    folder = (base / slug / "content").resolve()
    if not folder.is_relative_to(base) or not folder.is_dir():
        return ()
    topics: list[Topic] = []
    for path in sorted(folder.glob("*.md")):
        try:
            topic = parse_topic(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if topic is not None and topic.tokens:
            topics.append(topic)
    return tuple(topics)


def topics_for(content_dir: str, slug: str) -> tuple[Topic, ...]:
    folder = Path(content_dir) / "roadmaps" / slug / "content"
    try:
        stamp = folder.stat().st_mtime
    except OSError:
        return ()
    return _load_topics(content_dir, slug, stamp)


def best_topic(topics: tuple[Topic, ...], texts: list[str]) -> Topic | None:
    """The topic whose name is best covered by the day's text (first task first)."""
    for text in (texts[:1], texts):  # the "Understand: <concept>" task, then the whole day
        joined = " ".join(text)
        words, phrase = _tokens(joined), f" {_normalise(joined)} "
        if not words:
            continue
        best: tuple[float, int, int, Topic] | None = None
        for topic in topics:
            hit = len(topic.tokens & words)
            if not hit:
                continue
            score = hit / len(topic.tokens)
            if topic.phrase and f" {topic.phrase} " in phrase:
                score += 1  # the exact name ("big o notation" beats "Big-Ω Notation")
            key = (score, hit, len(topic.title), topic)
            if score >= MIN_SCORE and (best is None or key[:3] > best[:3]):
                best = key
        if best is not None:
            return best[3]
    return None


def reference(subject: str, day_texts: list[str], content_dir: str) -> Reference:
    local = bool(content_dir) and (Path(content_dir) / "roadmaps").is_dir()
    slug = roadmap_slug(subject, content_dir if local else "")
    if slug is None:
        return Reference(None, None, None, None, local_content=local)
    topic = best_topic(topics_for(content_dir, slug), day_texts) if local else None
    return Reference(
        roadmap_slug=slug,
        roadmap_name=roadmap_name(slug),
        roadmap_url=f"https://roadmap.sh/{slug}",
        topic=topic,
        local_content=local,
    )
