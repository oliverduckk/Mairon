"""Bounded provenance completion for the existing public-factual producer.

This module supplies no factual answer and consumes no acceptance verdict. A
requested citation is built only from Core's retained admitted page-read state.
The candidate is inspected for omission, never used as evidence of a read.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import re

from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.public_answer_evidence import normalize_source_url
from core.public_source_requirements import (
    _source_identity_request, public_source_requirements,
)


_OUTPUT = re.compile(
    r"(?:^|\b(?:and|also|please)\s+|[,;:]\s*|\b(?:can|could|would|will)\s+(?:you|u)\s+)"
    r"(?:please\s+)?(?:give|show|send|share|provide|include|cite|list)\s+"
    r"(?:(?:me|us)\s+)?(?:(?:the|an?|your|its|their|actual|exact|specific|original|canonical|"
    r"official|primary|loaded|read|supporting)\s+){0,5}"
    r"(?:source(?!\s+code\b)(?:\s+(?:url|link))?|urls?|links?|citations?|references?)\b", re.I,
)
_WANT_OUTPUT = re.compile(
    r"\bI\s+(?:want|need|would\s+like)\s+(?:(?:the|an?|actual|exact|official|primary)\s+){0,3}"
    r"(?:source(?!\s+code\b)(?:\s+(?:url|link))?|url|link|citation)\b", re.I,
)
_NEGATED = re.compile(
    r"\b(?:do\s+not|don['’]t|no\s+need\s+to|without|never)\s+"
    r"(?:give|show|send|share|provide|include|cite|list)\b|"
    r"\b(?:no|without)\s+(?:sources?|urls?|links?|citations?|references?)\b", re.I,
)


@dataclass(frozen=True)
class PublicSourceOutputRequirement:
    required: bool = False
    official: bool = False
    primary: bool = False
    requested_urls: tuple[str, ...] = ()


def source_output_requirement(user_input):
    """Recognize current USER output requests, not mere source-read requests."""
    if not isinstance(user_input, str):
        return PublicSourceOutputRequirement()
    required = False
    for clause in re.split(r"[;.!?]\s+|\n+", user_input):
        clause = clause.strip()
        if (not clause or clause.startswith(('"', "'", "“", "‘"))
                or re.match(r"^(?:if|suppose|imagine|hypothetically)\b", clause, re.I)
                or re.match(r"^(?:I|we|he|she|they|someone)\s+(?:said|asked|wrote|"
                            r"(?:have\s+)?(?:read|loaded|used|included|provided))\b", clause, re.I)
                or _NEGATED.search(clause)):
            continue
        required = required or bool(_OUTPUT.search(clause) or _WANT_OUTPUT.search(clause))
        if re.search(r"\b(?:which|what)\b", clause, re.I):
            required = required or _source_identity_request(clause)
        if re.fullmatch(r"(?:(?:actual|exact|official|primary|source)\s+){0,3}"
                        r"(?:url|link|citation)(?:\s+please)?[?!.]*", clause, re.I):
            required = True
    flags = public_source_requirements(user_input)
    return PublicSourceOutputRequirement(
        required=required, official=flags["official_source_required"],
        primary=flags["primary_source_required"], requested_urls=flags["requested_source_urls"],
    )


def public_source_output_required(user_input):
    return source_output_requirement(user_input).required


def complete_public_source_request(text, *, user_input, authority_context, contract):
    """Attach a requested real read identity or an honest bounded limitation.

    Ordinary factual prose is unchanged. Unsupported URLs already in a draft
    are left for the existing strict producer verifier to reject; this function
    neither repairs them into authority nor substitutes an imagined identity.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    runtime = coerce_answer_contract_runtime(contract)
    if (runtime is None or runtime.intent != "factual_question"
            or runtime.epistemic_mode != "public_source_verified"
            or runtime.authority != "public_web"):
        return text
    requirement = source_output_requirement(user_input)
    if not requirement.required:
        return text
    context = authority_context if isinstance(authority_context, Mapping) else {}
    flags = context.get("requirements")
    flags = flags if isinstance(flags, Mapping) else {}
    official = requirement.official or flags.get("official_source_required") is True
    primary = requirement.primary or flags.get("primary_source_required") is True
    urls = []
    if context.get("version") == 1 and isinstance(context.get("sources"), (list, tuple)):
        for source in context["sources"]:
            if (not isinstance(source, Mapping) or source.get("read_success") is not True
                    or source.get("accepted_as_evidence") is not True):
                continue
            url = normalize_source_url(source.get("read_url"))
            if not url:
                continue
            if official and (source.get("authority_tier") != "primary_official"
                             or source.get("quality_eligible") is not True):
                continue
            if primary and (source.get("authority_tier") not in {"primary_official", "primary_institutional"}
                            or source.get("quality_eligible") is not True):
                continue
            if requirement.requested_urls and url not in requirement.requested_urls:
                continue
            if url not in urls:
                urls.append(url)
    emitted = {
        normalize_source_url(match.group().rstrip(".,;:!?"))
        for match in re.finditer(r"https?://[^\s<>\"'`]+", text, re.I)
    }
    if urls:
        if any(url in emitted for url in urls):
            return text
        # The legacy sentence verifier does not bind every fact to one source.
        # Do not guess which page a multi-source answer exclusively came from.
        label = "Source: " if len(urls) == 1 else "Sources: "
        return text.rstrip() + "\n\n" + label + "; ".join(urls)
    authority = "official " if official else "primary " if primary else ""
    limitation = "I cannot verify a usable loaded " + authority + "source URL from the evidence available."
    if limitation in text:
        return text
    return text.rstrip() + "\n\n" + limitation
