#Fuzzy Matching Algorithms (Hybrid)
#Raw name input -> Normalization -> Similarity scores -> Gunpla-specificity -> Concate Scores -> Norm Scores (0, 1)

# Best approach is Damerau-Levenshtein distance with Token Jaccard Similarity due to the nature of listing titles

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()

    # Make common model-number styles comparable.
    text = re.sub(r"[-_/]+", " ", text)

    # Remove remaining punctuation.
    text = re.sub(r"[^\w\s]", " ", text)

    # Collapse repeated whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip()

def levenshtein_distance(left: str, right: str) -> int:
    rows = len(left) + 1
    columns = len(right) + 1

    matrix = [
        [0 for _ in range(columns)]
        for _ in range(rows)
    ]

    # Converting text into an empty string requires deletions.
    for row in range(rows):
        matrix[row][0] = row

    # Converting an empty string into text requires insertions.
    for column in range(columns):
        matrix[0][column] = column

    for row in range(1, rows):
        for column in range(1, columns): #matrix has extr init row and col representing empty strings so matrix pos 1 is string pos 0
            left_character = left[row - 1]
            right_character = right[column - 1]

            replacement_cost = (
                0 if left_character == right_character else 1
            )

            deletion = matrix[row - 1][column] + 1
            insertion = matrix[row][column - 1] + 1
            replacement = (
                matrix[row - 1][column - 1]
                + replacement_cost
            )

            matrix[row][column] = min(
                deletion,
                insertion,
                replacement,
            )

    return matrix[-1][-1]

def damerau_osa_distance(left: str, right: str) -> int: # leven + less penalizing swap based on pos
    rows = len(left) + 1
    columns = len(right) + 1

    matrix = [
        [0 for _ in range(columns)]
        for _ in range(rows)
    ]

    for row in range(rows):
        matrix[row][0] = row

    for column in range(columns):
        matrix[0][column] = column

    for row in range(1, rows):
        for column in range(1, columns):
            left_character = left[row - 1]
            right_character = right[column - 1]

            replacement_cost = (
                0 if left_character == right_character else 1
            )

            deletion = matrix[row - 1][column] + 1
            insertion = matrix[row][column - 1] + 1
            replacement = (
                matrix[row - 1][column - 1]
                + replacement_cost
            )

            best_cost = min(
                deletion,
                insertion,
                replacement,
            )

            if (
                row > 1
                and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                transposition = matrix[row - 2][column - 2] + 1
                best_cost = min(best_cost, transposition)

            matrix[row][column] = best_cost

    return matrix[-1][-1]


def levenshtein_similarity(left: str, right: str) -> float:
    left = normalize(left)
    right = normalize(right)

    if not left and not right:
        return 1.0

    longest_length = max(len(left), len(right))

    if longest_length == 0:
        return 1.0

    distance = levenshtein_distance(left, right)
    return 1.0 - (distance / longest_length)


def damerau_similarity(left: str, right: str) -> float:
    left = normalize(left)
    right = normalize(right)

    if not left and not right:
        return 1.0

    longest_length = max(len(left), len(right))
    distance = damerau_osa_distance(left, right)
    return 1.0 - (distance / longest_length)


def tokenize(text: str) -> set[str]: # js split normalized text using whitespace
    return set(normalize(text).split())

def token_jaccard(left: str, right: str) -> float: # essentially union and intersection operators
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)

    if not left_tokens and not right_tokens:
        return 1.0

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens

    return len(intersection) / len(union)

def token_coverage(canonical: str, listing: str) -> float: # Minimize extra char penalization
    canonical_tokens = tokenize(canonical)
    listing_tokens = tokenize(listing)

    if not canonical_tokens:
        return 1.0 if not listing_tokens else 0.0

    shared_tokens = canonical_tokens & listing_tokens
    return len(shared_tokens) / len(canonical_tokens)

def character_ngrams(text: str, size: int = 3) -> set[str]: # more lax spelling damage scoring (split in 3 char)
    text = normalize(text).replace(" ", "")

    if not text:
        return set()

    if len(text) < size:
        return {text}

    return {
        text[index:index + size]
        for index in range(len(text) - size + 1)
    }

def trigram_dice(left: str, right: str) -> float: # dice coef calculation
    left_grams = character_ngrams(left)
    right_grams = character_ngrams(right)

    if not left_grams and not right_grams:
        return 1.0

    if not left_grams or not right_grams:
        return 0.0

    shared = left_grams & right_grams

    return (
        2 * len(shared)
        / (len(left_grams) + len(right_grams))
    )

def lexical_score(canonical: str, listing: str) -> dict[str, float]: # synthesis scoring function (prelim)
    edit = damerau_similarity(canonical, listing)
    jaccard = token_jaccard(canonical, listing)
    coverage = token_coverage(canonical, listing)
    trigrams = trigram_dice(canonical, listing)

    total = (
        0.35 * edit
        + 0.20 * jaccard
        + 0.25 * coverage
        + 0.20 * trigrams
    )

    return {
        "edit_similarity": edit,
        "token_jaccard": jaccard,
        "canonical_coverage": coverage,
        "trigram_dice": trigrams,
        "total": total,
    }


# gpla specific feature extraction & scoring

GRADE_PATTERNS = {
    "MGEX": (r"\bmgex\b", r"\bmaster grade extreme\b"),
    "MGSD": (r"\bmgsd\b",),
    "PG": (r"\bpg\b", r"\bperfect grade\b"),
    "MG": (r"\bmg\b", r"\bmaster grade\b"),
    "RG": (r"\brg\b", r"\breal grade\b"),
    "HG": (
        r"\bhg(?:uc|ac|ce|fc|bf|ibo|tb|wfm)?\b",
        r"\bhigh grade\b",
    ),
    "SD": (r"\bsd(?:cs|ex|bb)?\b", r"\bsuper deformed\b"),
    "EG": (r"\beg\b", r"\bentry grade\b"),
    "RE100": (r"\bre\s*100\b", r"\breborn one hundred\b"),
    "FM": (r"\bfull mechanics\b",),
}

VARIANT_PATTERNS = {
    "mechanical_clear": (r"\bmechanical\s+(?:smoked\s+)?clear\b",),
    "clear_color": (
        r"\bclear\s+colou?r\b",
        r"\b(?:all|blue|red|smoked|metal)?\s*clear\s+(?:ver|version|edition)\b",
    ),
    "titanium_finish": (r"\btitanium\s+finish\b",),
    "special_coating": (r"\bspecial\s+coating\b",),
    "gold_coating": (r"\bgold\s+coating\b",),
    "metallic_coating": (r"\bmetalli?c\s+coating\b",),
    "extra_finish": (r"\bextra\s+finish\b",),
    "pearl_finish": (r"\bpearl(?:\s+mirror)?\s+(?:coating|finish)\b",),
    "recirculation_color": (r"\brecirculation\s+colou?r\b",),
    "trans_am": (r"\btrans\s+am\b",),
    "deactive_mode": (r"\bdeactive\s+mode\b",),
    "real_type_color": (r"\breal\s+type\s+colou?r\b",),
}

ACCESSORY_PATTERNS = (
    r"\bexpansion\s+(?:set|parts?)\b",
    r"\beffect\s+(?:unit|parts?|set)\b",
    r"\bweapon\s+(?:unit|parts?|set)\b",
    r"\boption(?:al)?\s+parts?\b",
    r"\bparts?\s+set\b",
    r"\bled\s+unit\b",
    r"\bwater(?:\s+slide)?\s+decals?\b",
)


@dataclass(frozen=True)
class GunplaFeatures:
    grades: frozenset[str]
    scales: frozenset[str]
    model_codes: frozenset[str]
    variants: frozenset[str]
    product_type: str

    def as_dict(self) -> dict[str, object]:
        return {
            "grades": sorted(self.grades),
            "scales": sorted(self.scales),
            "model_codes": sorted(self.model_codes),
            "variants": sorted(self.variants),
            "product_type": self.product_type,
        }


def normalize_gunpla_name(text: str) -> str: #normalize text while also resolving a few gpla specific aliases & edge cases

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ν", " nu ").replace("Ν", " nu ")
    text = normalize(text)

    aliases = (
        (r"\bmaster grade extreme\b", "mgex"),
        (r"\bmaster grade\b", "mg"),
        (r"\bperfect grade\b", "pg"),
        (r"\breal grade\b", "rg"),
        (r"\bhigh grade\b", "hg"),
        (r"\bsuper deformed\b", "sd"),
        (r"\bentry grade\b", "eg"),
        (r"\bversion\b", "ver"),
    )

    for pattern, replacement in aliases:
        text = re.sub(pattern, replacement, text)

    return re.sub(r"\s+", " ", text).strip()


def extract_grades(text: str) -> frozenset[str]:
    normalized = normalize_gunpla_name(text)
    grades = {
        grade
        for grade, patterns in GRADE_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    }
    return frozenset(grades)


def extract_scales(text: str) -> frozenset[str]:
    normalized = normalize(text)
    scales = {
        f"1/{denominator}"
        for denominator in re.findall(r"\b1\s+(48|60|100|144)\b", normalized)
    }
    return frozenset(scales)


def extract_model_codes(text: str) -> frozenset[str]:
    """Extract hyphenated identifiers such as RX-78-2 and ZGMF-X10A."""
    prepared = unicodedata.normalize("NFKC", text).upper()
    prepared = re.sub(r"[‐‑‒–—−]", "-", prepared)
    candidates = re.findall(
        r"(?<![A-Z0-9])([A-Z0-9]{1,10}(?:-[A-Z0-9]{1,10})+)(?![A-Z0-9])",
        prepared,
    )

    model_codes = set()
    for candidate in candidates:
        if not any(character.isalpha() for character in candidate):
            continue
        if not any(character.isdigit() for character in candidate):
            continue

        # Removing punctuation makes RX-78-2 and RX78-2 comparable.
        model_codes.add(re.sub(r"[^A-Z0-9]", "", candidate))

    return frozenset(model_codes)


def extract_variants(text: str) -> frozenset[str]:
    normalized = normalize_gunpla_name(text)
    variants = {
        variant
        for variant, patterns in VARIANT_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    }
    return frozenset(variants)


def classify_product_type(text: str) -> str:
    normalized = normalize_gunpla_name(text)
    if any(re.search(pattern, normalized) for pattern in ACCESSORY_PATTERNS):
        return "accessory"
    return "kit"


def extract_gunpla_features(text: str) -> GunplaFeatures:
    return GunplaFeatures(
        grades=extract_grades(text),
        scales=extract_scales(text),
        model_codes=extract_model_codes(text),
        variants=extract_variants(text),
        product_type=classify_product_type(text),
    )


def gunpla_match_score(canonical: str, listing: str) -> dict[str, object]: # combine fuzzy similarities with gpla constraints
    canonical_normalized = normalize_gunpla_name(canonical)
    listing_normalized = normalize_gunpla_name(listing)
    lexical = lexical_score(canonical_normalized, listing_normalized)

    canonical_features = extract_gunpla_features(canonical)
    listing_features = extract_gunpla_features(listing)

    adjustment = 0.0
    rejected = False
    reasons: list[str] = []

    if canonical_features.grades and listing_features.grades:
        shared_grades = canonical_features.grades & listing_features.grades
        if shared_grades:
            adjustment += 0.04
            reasons.append(f"grade match: {', '.join(sorted(shared_grades))}")
        else:
            rejected = True
            reasons.append("rejected: conflicting grades")

    if canonical_features.scales and listing_features.scales:
        shared_scales = canonical_features.scales & listing_features.scales
        if shared_scales:
            adjustment += 0.04
            reasons.append(f"scale match: {', '.join(sorted(shared_scales))}")
        else:
            rejected = True
            reasons.append("rejected: conflicting scales")

    if canonical_features.model_codes and listing_features.model_codes:
        shared_codes = canonical_features.model_codes & listing_features.model_codes
        if shared_codes:
            adjustment += 0.12
            reasons.append(f"model-code match: {', '.join(sorted(shared_codes))}")
        else:
            adjustment -= 0.30
            reasons.append("penalty: conflicting model codes")

    if canonical_features.variants and listing_features.variants:
        shared_variants = canonical_features.variants & listing_features.variants
        if shared_variants:
            adjustment += 0.05
            reasons.append(f"variant match: {', '.join(sorted(shared_variants))}")
        else:
            adjustment -= 0.22
            reasons.append("penalty: conflicting variants")
    elif canonical_features.variants != listing_features.variants:
        adjustment -= 0.06
        reasons.append("penalty: variant appears on only one name")

    if canonical_features.product_type != listing_features.product_type:
        rejected = True
        reasons.append("rejected: kit/accessory conflict")

    final_score = 0.0 if rejected else max(
        0.0,
        min(1.0, lexical["total"] + adjustment),
    )

    return {
        "canonical": canonical,
        "listing": listing,
        "lexical": lexical,
        "canonical_features": canonical_features.as_dict(),
        "listing_features": listing_features.as_dict(),
        "domain_adjustment": adjustment,
        "rejected": rejected,
        "reasons": reasons,
        "final_score": final_score,
    }

#Test Zone :)

assert levenshtein_distance("gundam", "gundma") == 2
assert damerau_osa_distance("gundam", "gundma") == 1
