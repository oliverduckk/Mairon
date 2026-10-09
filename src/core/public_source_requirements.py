"""Bounded source obligations from the actual current USER request.

These flags refine shadow acceptance only. They do not choose sources, route a
turn, permit research, or infer source authority from candidate wording. The
current request remains distinct from a reconstructed search query.
"""
import re

from core.public_answer_evidence import normalize_source_url


_SOURCE = re.compile(
    r"\b(?:docs?|documents?|documentation|manuals?|references?|sources?|pages?|"
    r"links?|websites?|articles?|reports?|handbooks?|evidence|urls?)\b", re.I,
)
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.I)
_READ = r"(?:read|load|open|check|consult|verify|inspect|review|look\s+(?:at|up|into))"
_REQUEST_READ = re.compile(
    r"(?:^\s*(?:please\s+)?|\bplease\s+|\b(?:can|could|would|will)\s+(?:you|u)\s+"
    r"|\b(?:want|need|asking)\s+(?:you|u)\s+to\s+|[,;:]\s*)"
    r"(?:actually\s+)?" + _READ + r"\b", re.I,
)
_NEGATED = re.compile(r"\b(?:do\s+not|don['’]t|never|without)\s+" + _READ + r"\b", re.I)
_READ_QUESTION = re.compile(
    r"\b(?:did|have)\s+(?:you|u)\s+(?:actually\s+)?"
    r"(?:read|load(?:ed)?|open(?:ed)?|check(?:ed)?|consult(?:ed)?|inspect(?:ed)?|review(?:ed)?)\b", re.I,
)
_PRIOR_REPORT = re.compile(
    r"^(?:I|we)(?:['’]ve)?\s+(?:(?:have|had|already|previously|just)\s+)*"
    r"(?:read|loaded|opened|checked|consulted|inspected|reviewed|used|saw|seen)\b", re.I,
)
_DECLINED_SOURCE_REQUIREMENT = re.compile(
    r"\b(?:do\s+not|don['’]t|never|no\s+need\s+to)\s+"
    r"(?:need|require|want|use|cite|read|load|open|check|consult|verify|inspect|review)\b", re.I,
)
_IDENTITY = re.compile(
    r"\b(?:(?:actual|exact|specific|original|canonical)\s+(?:source\s+)?"
    r"(?:url|link|page|source)|source\s+(?:url|link)|which\s+(?:url|page|source)(?!\s+code\b)|"
    r"what\s+url|(?:which|what)\s+"
    r"(?:(?:actual|exact|specific|original|canonical|official|primary)\s+){1,3}"
    r"(?:source\s+)?(?:url|link|page|source)(?!\s+code\b)"
    r"|(?:url|link)\s+(?:(?:you|u)\s+)?(?:used|read|loaded))\b", re.I,
)
_IDENTITY_QUESTION = re.compile(
    r"\b(?:which|what)\s+(?:link|source|page)(?!\s+code\b)\s+(?P<relation>[^;.!?\n]{1,200})", re.I,
)
_ATTRIBUTION_TARGET = (
    r"(?:it|this|that|(?:the|your|this|that)\s+"
    r"(?:answer|response|explanation|claim|quote|quotation|citation|text|excerpt|fact|figure|number|information))"
)
_SOURCE_USE_BASE = r"(?:use|read|load|open|check|consult|cite|quote|fetch|pull|retrieve)"
_SOURCE_USE_PAST = r"(?:used|read|loaded|opened|checked|consulted|cited|quoted|fetched|pulled|retrieved)"
_IDENTITY_RELATION = re.compile(
    r"(?:(?:is|was)\s+" + _ATTRIBUTION_TARGET + r"\s+from|"
    r"(?:did|does)\s+" + _ATTRIBUTION_TARGET + r"\s+(?:come|originate)\s+from|"
    r"(?:did|do)\s+(?:you|u)\s+(?:actually\s+)?" + _SOURCE_USE_BASE + r"|"
    r"(?:have|had)\s+(?:you|u)\s+(?:actually\s+)?" + _SOURCE_USE_PAST + r"|"
    r"(?:you|u)\s+(?:actually\s+)?" + _SOURCE_USE_PAST + r"|"
    r"(?:is|was)\s+" + _SOURCE_USE_PAST + r"(?:\s+by\s+(?:you|u))?)"
    r"(?:\s+for\s+(?:the|this|that|your)\s+(?:answer|response|explanation|claim|quote|citation))?", re.I,
)
_NEGATIVE_READ = (
    r"(?:(?:did\s+not|didn['’]t|do\s+not|don['’]t)\s+(?:actually\s+|really\s+)?"
    + _READ + r"|(?:have\s+not|haven['’]t|had\s+not|hadn['’]t)\s+"
    r"(?:actually\s+|really\s+)?(?:read|loaded|opened|checked|consulted|verified|inspected|reviewed|"
    r"looked\s+(?:at|up|into)))"
)
_HONESTY_CONSEQUENT = (
    r"(?:(?:please\s+)?|(?:you|u)\s+(?:should|must|need\s+to)\s+)"
    r"(?:say\s+(?:so|that)|tell\s+me\s+(?:so|that)|admit\s+(?:it|that)|"
    r"acknowledge\s+(?:it|that)|make\s+(?:it\s+)?clear|"
    r"be\s+(?:honest|explicit)(?:\s+about\s+(?:it|that))?)"
)
_HONESTY_CONDITIONAL = re.compile(
    r"if\s+(?:you|u)\s+" + _NEGATIVE_READ +
    r"\s+(?P<target>https?://[^\s,;]+|[^,;.!?\n]{1,160}?)\s*,?\s+" +
    _HONESTY_CONSEQUENT + r"[.!?]*", re.I,
)


def _read_honesty_request(clause):
    """Recognize a bounded request to disclose an absent assistant source read.

    A negative condition is not a prohibition when its consequent explicitly
    requires truthful disclosure. Other hypothetical source use remains outside
    this family. The target must name source material or use a bounded anaphor;
    an arbitrary condition about checking some unrelated state does not qualify.
    """
    marker = re.search(r"(?:^|[,;:]\s*|\b(?:and|but)\s+)if\s+(?:you|u)\b", clause, re.I)
    if not marker:
        return False
    condition = clause[marker.start():].strip(" ,;:")
    condition = re.sub(r"^(?:and|but)\s+", "", condition, flags=re.I)
    match = _HONESTY_CONDITIONAL.fullmatch(condition)
    if not match:
        return False
    target = match.group("target").strip()
    return bool(_SOURCE.search(target) or _URL.search(target)
                or re.fullmatch(r"(?:it|that|this|them|these|those)", target, re.I))


def _source_identity_request(clause):
    """Require attribution for otherwise ambiguous link/source questions.

    A structural link or a source of heat is not automatically a source URL.
    Legacy explicit identity forms remain intact; the new bare interrogative
    family needs a bounded assistant-use or answer-from relationship.
    """
    if _IDENTITY.search(clause):
        return True
    for question in _IDENTITY_QUESTION.finditer(clause):
        relation = re.split(r",\s*(?:and|but)\s+if\b", question.group("relation"),
                            maxsplit=1, flags=re.I)[0].strip()
        if _IDENTITY_RELATION.fullmatch(relation):
            return True
    return False


def public_source_requirements(user_input):
    """Retain affirmative source obligations without treating reports as commands.

    Recognition is limited to general request forms and source identity syntax.
    Source quality and whether a read occurred always come from Core evidence.
    """
    text = user_input if isinstance(user_input, str) else ""
    official = primary = read_required = identity_required = False
    requested_urls = []
    for clause in re.split(r"[;.!?]\s+|\n+", text):
        clause = clause.strip()
        if not clause:
            continue
        # Quoted and reported speech is not a fresh instruction.
        if (clause.startswith(('"', "'", "“", "‘"))
                or re.match(r"^(?:he|she|they|someone)\s+(?:said|wrote|asked)\b", clause, re.I)):
            continue
        honesty_required = _read_honesty_request(clause)
        # Retain only the disclosure obligation of the narrowly recognized
        # conditional. General hypotheticals must not request a real read.
        if (re.match(r"^(?:suppose|imagine|hypothetically)\b", clause, re.I)
                or re.match(r"^if\b", clause, re.I) and not honesty_required):
            continue
        # A user's report about prior reading is context, not a request that
        # every source in the new answer have that report's authority/identity.
        if _PRIOR_REPORT.search(clause) and not _REQUEST_READ.search(clause):
            continue
        urls = []
        for match in _URL.finditer(clause):
            value = match.group().rstrip(".,;:!?")
            while value.endswith(")") and value.count(")") > value.count("("):
                value = value[:-1]
            normalized = normalize_source_url(value)
            if normalized:
                urls.append(normalized)
        has_source = bool(_SOURCE.search(clause) or urls)
        affirmative_read = honesty_required or bool(
            has_source and (_REQUEST_READ.search(clause) or _READ_QUESTION.search(clause))
            and not _NEGATED.search(clause))
        read_required = read_required or affirmative_read
        if has_source and (honesty_required or not _DECLINED_SOURCE_REQUIREMENT.search(clause)):
            if not re.search(r"\b(?:not|no|without)\s+(?:an?\s+)?official\b", clause, re.I):
                official = official or bool(re.search(r"\bofficial\b", clause, re.I))
            if not re.search(r"\b(?:not|no|without)\s+(?:an?\s+)?primary\b", clause, re.I):
                primary = primary or bool(re.search(r"\bprimary\b", clause, re.I))
        clause_identity = bool(has_source and _source_identity_request(clause))
        identity_required = identity_required or clause_identity
        if affirmative_read or clause_identity:
            requested_urls.extend(urls)
    return {
        "source_read_required": read_required,
        "official_source_required": official,
        "primary_source_required": primary,
        "exact_source_required": identity_required or bool(requested_urls),
        "requested_source_urls": tuple(dict.fromkeys(requested_urls)),
    }
